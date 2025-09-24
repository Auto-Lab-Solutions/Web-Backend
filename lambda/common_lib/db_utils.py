import boto3, os, time
from decimal import Decimal
from datetime import datetime
from zoneinfo import ZoneInfo
from botocore.exceptions import ClientError
from boto3.dynamodb.types import TypeDeserializer
import validation_utils as valid

# Dynamodb client and deserializer
dynamodb = boto3.client('dynamodb')
deserializer = TypeDeserializer()

# Environment variables
STAFF_TABLE = os.environ.get('STAFF_TABLE')
USERS_TABLE = os.environ.get('USERS_TABLE')
CONNECTIONS_TABLE = os.environ.get('CONNECTIONS_TABLE')
MESSAGES_TABLE = os.environ.get('MESSAGES_TABLE')
UNAVAILABLE_SLOTS_TABLE = os.environ.get('UNAVAILABLE_SLOTS_TABLE')
APPOINTMENTS_TABLE = os.environ.get('APPOINTMENTS_TABLE')
SERVICE_PRICES_TABLE = os.environ.get('SERVICE_PRICES_TABLE')
ORDERS_TABLE = os.environ.get('ORDERS_TABLE')
ITEM_PRICES_TABLE = os.environ.get('ITEM_PRICES_TABLE')
INQUIRIES_TABLE = os.environ.get('INQUIRIES_TABLE')
PAYMENTS_TABLE = os.environ.get('PAYMENTS_TABLE')
INVOICES_TABLE = os.environ.get('INVOICES_TABLE')

# ------------------  Staff Table Functions ------------------

def get_staff_record(email, raise_on_error=False):
    """
    Get staff record by email with comprehensive error handling
    
    Args:
        email: Staff email to lookup
        raise_on_error: If True, raises exceptions for critical errors. If False (default), 
                       maintains backward compatibility by returning None for all errors.
        
    Returns:
        dict: Staff record or None if not found
        
    Raises:
        Exception: For database connection or other critical errors (only if raise_on_error=True)
    """
    if not email:
        print("get_staff_record: email parameter is required")
        return None
    
    if not STAFF_TABLE:
        print("get_staff_record: STAFF_TABLE environment variable not set")
        if raise_on_error:
            raise Exception("Database configuration error: STAFF_TABLE not configured")
        return None
    
    try:
        print(f"get_staff_record: Querying STAFF_TABLE '{STAFF_TABLE}' for email: {email}")
        
        result = dynamodb.query(
            TableName=STAFF_TABLE,
            KeyConditionExpression='userEmail = :email',
            ExpressionAttributeValues={':email': {'S': email}}
        )
        
        print(f"get_staff_record: Query result count: {result.get('Count', 0)}")
        
        if result.get('Count', 0) > 0:
            staff_record = deserialize_item(result['Items'][0])
            print(f"get_staff_record: Found staff record: {staff_record}")
            return staff_record
            
        print(f"get_staff_record: No staff record found for email: {email}")
        return None
        
    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_message = e.response['Error']['Message']
        print(f"get_staff_record: DynamoDB ClientError - Code: {error_code}, Message: {error_message}")
        
        # For certain errors, raise exception only if raise_on_error=True
        if raise_on_error and error_code in ['ResourceNotFoundException', 'AccessDeniedException']:
            raise Exception(f"Database access error: {error_message}")
        
        print(f"get_staff_record: Returning None due to ClientError")
        return None
        
    except Exception as e:
        print(f"get_staff_record: Unexpected error: {str(e)}")
        print(f"get_staff_record: Error type: {type(e).__name__}")
        import traceback
        traceback.print_exc()
        
        if raise_on_error:
            raise Exception(f"Database operation failed: {str(e)}")
        
        print("get_staff_record: Returning None due to unexpected error (backward compatibility)")
        return None

def get_all_mechanic_records():
    try:
        result = dynamodb.scan(
            TableName=STAFF_TABLE,
            FilterExpression='contains(roles, :role)',
            ExpressionAttributeValues={':role': {'S': 'MECHANIC'}}
        )
        return [deserialize_item(item) for item in result.get('Items', [])]
    except ClientError as e:
        print(f"Error scanning mechanic records: {e.response['Error']['Message']}")
        return []

def get_all_staff_records():
    try:
        result = dynamodb.scan(TableName=STAFF_TABLE)
        return [deserialize_item(item) for item in result.get('Items', [])]
    except ClientError as e:
        print(f"Error scanning staff records: {e.response['Error']['Message']}")
        return []

def get_staff_record_by_user_id(user_id):
    """Get staff record by user ID"""
    try:
        result = dynamodb.query(
            TableName=STAFF_TABLE,
            IndexName='userId-index',
            KeyConditionExpression='userId = :uid',
            ExpressionAttributeValues={':uid': {'S': user_id}}
        )
        if result.get('Count', 0) > 0:
            return deserialize_item(result['Items'][0])
        return None
    except ClientError as e:
        print(f"Error querying staff record by user ID: {e.response['Error']['Message']}")
        return None

def update_staff_roles(user_email, new_roles):
    """Update staff member roles"""
    try:
        # Convert roles list to DynamoDB format
        roles_list = [{'S': role} for role in new_roles]
        
        dynamodb.update_item(
            TableName=STAFF_TABLE,
            Key={'userEmail': {'S': user_email}},
            UpdateExpression='SET #roles = :roles',
            ExpressionAttributeNames={
                '#roles': 'roles'
            },
            ExpressionAttributeValues={
                ':roles': {'L': roles_list}
            }
        )
        print(f"Staff roles updated successfully for {user_email}: {new_roles}")
        return True
    except ClientError as e:
        print(f"Error updating staff roles for {user_email}: {e}")
        return False

# ------------------  User Table Functions ------------------

def get_user_record(user_id):
    try:
        result = dynamodb.get_item(
            TableName=USERS_TABLE,
            Key={'userId': {'S': user_id}}
        )
        if 'Item' in result:
            return deserialize_item(result['Item'])
        return None
    except ClientError as e:
        print(f"Error getting user record for userId {user_id}: {e}")
        return None

def build_user_record(user_id, user_record, user_email=None, user_name=None, user_device=None, user_location=None, user_phone=None, assigned_to=None):
    user_email = user_record.get('userEmail') if user_record and user_record.get('userEmail') else user_email if user_email else ''
    user_name = user_record.get('userName') if user_record and user_record.get('userName') else user_name if user_name else ''
    user_device = user_device if user_device else user_record.get('userDevice') if user_record and user_record.get('userDevice') else ''
    user_location = user_location if user_location else user_record.get('userLocation') if user_record and user_record.get('userLocation') else ''
    user_phone = user_record.get('contactNumber') if user_record and user_record.get('contactNumber') else user_phone if user_phone else ''
    new_user_record = {
        'userId': {'S': user_id}
    }
    optional_fields = {
        'assignedTo': assigned_to,
        'userEmail': user_email,
        'userName': user_name,
        'userDevice': user_device,
        'userLocation': user_location,
        'contactNumber': user_phone
    }
    for key, value in optional_fields.items():
        if value:
            new_user_record[key] = {'S': value}
    
    return new_user_record

def create_or_update_user_record(user_data):
    try:
        dynamodb.put_item(
            TableName=USERS_TABLE,
            Item=user_data
        )
        return True
    except ClientError as e:
        print(f"Error creating or updating user record: {e}")
        return False

def update_user_disconnected_time(user_id):
    try:
        dynamodb.update_item(
            TableName=USERS_TABLE,
            Key={'userId': {'S': user_id}},
            UpdateExpression='SET lastSeen = :lastSeen',
            ExpressionAttributeValues={':lastSeen': {'N': str(int(datetime.now(ZoneInfo('Australia/Perth')).timestamp()))}}
        )
        print(f"User {user_id} lastSeen updated successfully.")
        return True
    except ClientError as e:
        print(f"Error updating lastSeen for user {user_id}: {e}")
        return False

def update_user_record(user_id, update_data):
    """
    Update specific fields in a user record
    
    Args:
        user_id (str): The user ID to update
        update_data (dict): Dictionary containing fields to update
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        if not update_data:
            return True
        
        # Build update expression and attribute values
        update_expressions = []
        expression_attribute_values = {}
        
        for field, value in update_data.items():
            if field in ['userEmail', 'userName', 'userDevice', 'userLocation', 'contactNumber']:
                update_expressions.append(f"{field} = :{field}")
                expression_attribute_values[f":{field}"] = {'S': str(value)}
        
        if not update_expressions:
            return True
        
        update_expression = 'SET ' + ', '.join(update_expressions)
        
        dynamodb.update_item(
            TableName=USERS_TABLE,
            Key={'userId': {'S': user_id}},
            UpdateExpression=update_expression,
            ExpressionAttributeValues=expression_attribute_values
        )
        
        print(f"User {user_id} record updated with fields: {list(update_data.keys())}")
        return True
        
    except ClientError as e:
        print(f"Error updating user record {user_id}: {e}")
        return False

def assign_client_to_staff_user(client_id, staff_user_id):
    try:
        dynamodb.update_item(
            TableName=USERS_TABLE,
            Key={'userId': {'S': client_id}},
            UpdateExpression='SET assignedTo = :staffUserId',
            ExpressionAttributeValues={':staffUserId': {'S': staff_user_id}}
        )
        print(f"User {client_id} record updated with assignedTo: {staff_user_id}")
        return True
    except ClientError as e:
        print(f"Failed to assign user: {str(e)}")

def get_all_users():
    try:
        result = dynamodb.scan(TableName=USERS_TABLE)
        return [deserialize_item(item) for item in result.get('Items', [])]
    except ClientError as e:
        print(f"Error scanning user records: {e.response['Error']['Message']}")
        return []

def get_user_by_id(user_id):
    """Get user by ID - alias for get_user_record for consistency"""
    return get_user_record(user_id)

def get_user(user_id):
    """Get user by ID - alias for get_user_record for invoice generation"""
    return get_user_record(user_id)

# ------------------  Connection Table Functions ------------------

def get_connection(connection_id):
    try:
        result = dynamodb.query(
            TableName=CONNECTIONS_TABLE,
            KeyConditionExpression='connectionId = :connectionId',
            ExpressionAttributeValues={':connectionId': {'S': connection_id}}
        )
        if result.get('Count', 0) > 0:
            return deserialize_item(result['Items'][0])
        return None
    except ClientError as e:
        print(f"Error querying connectionId {connection_id}: {e}")
        return None

def get_connection_by_user_id(user_id):
    try:
        result = dynamodb.query(
            TableName=CONNECTIONS_TABLE,
            IndexName='userId-index',
            KeyConditionExpression='userId = :uid',
            ExpressionAttributeValues={':uid': {'S': user_id}}
        )
        if result.get('Count', 0) > 0:
            return deserialize_item(result['Items'][0])
        return None
    except ClientError as e:
        print(f"Error querying userId {user_id}: {e}")
        return None

def get_all_staff_connections():
    try:
        result = dynamodb.scan(
            TableName=CONNECTIONS_TABLE,
            FilterExpression='staff = :staff',
            ExpressionAttributeValues={':staff': {'BOOL': True}}
        )
        return [deserialize_item(item) for item in result.get('Items', [])]
    except ClientError as e:
        print(f"Error querying all staff connections: {e}")
        return []

def get_assigned_or_all_staff_connections(assigned_to=None):
    try:
        if assigned_to:
            result = dynamodb.query(
                TableName=CONNECTIONS_TABLE,
                IndexName='userId-index',
                KeyConditionExpression='userId = :uid',
                ExpressionAttributeValues={':uid': {'S': assigned_to}}
            )
        else:
            result = dynamodb.scan(
                TableName=CONNECTIONS_TABLE,
                FilterExpression='staff = :staff',
                ExpressionAttributeValues={':staff': {'BOOL': True}}
            )
        return [deserialize_item(item) for item in result.get('Items', [])]
    except ClientError as e:
        print(f"Error querying assigned or all staff connections: {e}")
        return []

def get_all_staff_connections_except_user(user_id):
    try:
        result = dynamodb.scan(
            TableName=CONNECTIONS_TABLE,
            FilterExpression='staff = :staff AND userId <> :userId',
            ExpressionAttributeValues={
                ':staff': {'BOOL': True},
                ':userId': {'S': user_id}
            }
        )
        return [deserialize_item(item) for item in result.get('Items', [])]
    except ClientError as e:
        print(f"Error querying all staff connections except user {user_id}: {e}")
        return []

def get_all_active_connections():
    try:
        response = dynamodb.scan(
            TableName=CONNECTIONS_TABLE,
            FilterExpression='attribute_exists(userId)'
        )
        connections = response.get('Items', [])
        return [deserialize_item(item) for item in connections]
    except ClientError as e:
        print(f"Error retrieving active connections: {e}")
        return []


def create_connection(connection_id):
    try:
        dynamodb.put_item(
            TableName=CONNECTIONS_TABLE,
            Item={
                'connectionId': {'S': connection_id},
                'createdAt': {'N': str(int(datetime.now(ZoneInfo('Australia/Perth')).timestamp()))}
            }
        )
        print(f"Connection {connection_id} created successfully.")
        return True
    except ClientError as e:
        print(f"Error creating connection {connection_id}: {e}")

def delete_connection(connection_id):
    try:
        dynamodb.delete_item(
            TableName=CONNECTIONS_TABLE,
            Key={'connectionId': {'S': connection_id}}
        )
        print(f"Connection {connection_id} deleted successfully.")
    except ClientError as e:
        print(f"Error deleting connection {connection_id}: {e}")

def delete_old_connections(user_id):
    try:
        result = dynamodb.query(
            TableName=CONNECTIONS_TABLE,
            IndexName='userId-index',
            KeyConditionExpression='userId = :uid',
            ExpressionAttributeValues={':uid': {'S': user_id}}
        )
        for item in result.get('Items', []):
            conn_id = item['connectionId']['S']
            dynamodb.delete_item(
                TableName=CONNECTIONS_TABLE,
                Key={'connectionId': {'S': conn_id}}
            )
            print(f"Deleted old connection: {conn_id} for userId: {user_id}")
    except ClientError as e:
        print(f"Error deleting old connections: {e}")

def delete_all_uninitialized_connections():
    try:
        result = dynamodb.scan(
            TableName=CONNECTIONS_TABLE,
            FilterExpression='attribute_not_exists(userId)'
        )
        for item in result.get('Items', []):
            conn_id = item['connectionId']['S']
            dynamodb.delete_item(
                TableName=CONNECTIONS_TABLE,
                Key={'connectionId': {'S': conn_id}}
            )
            print(f"Deleted uninitialized connection: {conn_id}")
    except ClientError as e:
        print(f"Error deleting uninitialized connections: {e}")

def build_update_expression_for_connection(data):
    update_parts = []
    expression_values = {}
    for key, value in data.items():
        if value:
            update_parts.append(f"{key} = :{key}")
            if key == 'staff':
                expression_values[f":{key}"] = {"BOOL": value == 'true'}
            else:
                expression_values[f":{key}"] = {"S": value}
    if update_parts:
        return "SET " + ", ".join(update_parts), expression_values
    return None, None

def update_connection(connection_id, user_data):
    update_expression, expression_values = build_update_expression_for_connection(user_data)
    if update_expression:
        try:
            dynamodb.update_item(
                TableName=CONNECTIONS_TABLE,
                Key={'connectionId': {'S': connection_id}},
                UpdateExpression=update_expression,
                ExpressionAttributeValues=expression_values
            )
            print(f"Connection {connection_id} updated successfully.")
            return True
        except ClientError as e:
            print(f"Error updating connection {connection_id}: {e}")
            return False
    else:
        print("No valid data to update.")
        return False

# ------------------  Message Table Functions ------------------

def get_message(message_id):
    try:
        result = dynamodb.query(
            TableName=os.environ['MESSAGES_TABLE'],
            KeyConditionExpression='messageId = :messageId',
            ExpressionAttributeValues={':messageId': {'S': message_id}}
        )
        if result.get('Count', 0) > 0:
            return deserialize_item(result['Items'][0])
        return None
    except ClientError as e:
        print(f"Error getting message with ID {message_id}: {e}")
        return None

def get_messages_by_index(index_name, key_name, key_value):
    try:
        response = dynamodb.query(
            TableName=MESSAGES_TABLE,
            IndexName=index_name,
            KeyConditionExpression=f'{key_name} = :value',
            ExpressionAttributeValues={':value': {'S': key_value}}
        )
        return [deserialize_item(item) for item in response.get('Items', [])]
    except ClientError as e:
        print(f"Error querying messages by {key_name}: {e}")
        return []

def build_message_data(message_id, message, sender_id, receiver_id):
    return {
        'messageId': {'S': message_id},
        'message': {'S': message},
        'senderId': {'S': sender_id},
        'receiverId': {'S': receiver_id},
        'sent': {'BOOL': True},
        'received': {'BOOL': False},
        'viewed': {'BOOL': False},
        'createdAt': {'N': str(int(datetime.now(ZoneInfo('Australia/Perth')).timestamp()))}
    }

def create_message(message_data):
    try:
        dynamodb.put_item(
            TableName=MESSAGES_TABLE,
            Item=message_data
        )
        print(f"Message stored with ID: {message_data['messageId']['S']}")
        return True
    except ClientError as e:
        print(f"Error storing message: {e}")


def update_message_status(message_id, status):
    try:
        update_expr = {
            'MESSAGE_RECEIVED': ('SET received = :val', {':val': {'BOOL': True}}),
            'MESSAGE_VIEWED': ('SET viewed = :val', {':val': {'BOOL': True}})
        }
        expr, values = update_expr[status]
        dynamodb.update_item(
            TableName=MESSAGES_TABLE,
            Key={'messageId': {'S': message_id}},
            UpdateExpression=expr,
            ExpressionAttributeValues=values
        )
        print(f"Message {message_id} marked as {status}.")
        return True
    except ClientError as e:
        print(f"Error updating message {message_id}: {str(e)}")


def update_message_content(message_id, new_message):
    try:
        dynamodb.update_item(
            TableName=MESSAGES_TABLE,
            Key={'messageId': {'S': message_id}},
            UpdateExpression='SET message = :newMessage',
            ExpressionAttributeValues={':newMessage': {'S': new_message}}
        )
        print(f"Message {message_id} updated successfully.")
        return True
    except ClientError as e:
        print(f"Error updating message {message_id}: {e}")

def delete_message(message_id):
    try:
        dynamodb.delete_item(
            TableName=MESSAGES_TABLE,
            Key={'messageId': {'S': message_id}}
        )
        print(f"Message {message_id} deleted successfully.")
        return True
    except ClientError as e:
        print(f"Error deleting message {message_id}: {e}")
        return False

# ------------------  Unavailable Slots Table Functions ------------------

def get_unavailable_slots(date):
    """Get unavailable slots for a specific date"""
    try:
        result = dynamodb.get_item(
            TableName=UNAVAILABLE_SLOTS_TABLE,
            Key={'date': {'S': date}}
        )
        if 'Item' in result:
            return deserialize_item_json_safe(result['Item'])
        return None
    except ClientError as e:
        print(f"Error getting unavailable slots for date {date}: {e}")
        return None

def update_unavailable_slots(date, time_slots, staff_user_id=None):
    """Update unavailable slots for a specific date"""
    try:
        # Build time slots list for DynamoDB
        time_slots_list = []
        for slot in time_slots:
            if isinstance(slot, str) and '-' in slot:
                # Handle "HH:MM-HH:MM" format
                start_time, end_time = slot.split('-')
                time_slots_list.append({
                    'M': {
                        'startTime': {'S': start_time},
                        'endTime': {'S': end_time}
                    }
                })
            elif isinstance(slot, dict) and 'startTime' in slot and 'endTime' in slot:
                # Handle object format
                time_slots_list.append({
                    'M': {
                        'startTime': {'S': slot['startTime']},
                        'endTime': {'S': slot['endTime']}
                    }
                })
            else:
                print(f"Warning: Invalid time slot format: {slot}")
        
        # Build the item to store
        item = {
            'date': {'S': date},
            'timeSlots': {'L': time_slots_list},
            'updatedAt': {'N': str(int(datetime.now(ZoneInfo('Australia/Perth')).timestamp()))}
        }
        
        # Add staff user ID if provided
        if staff_user_id:
            item['updatedBy'] = {'S': staff_user_id}
        
        dynamodb.put_item(
            TableName=UNAVAILABLE_SLOTS_TABLE,
            Item=item
        )
        print(f"Unavailable slots updated for date {date}")
        return True
    except ClientError as e:
        print(f"Error updating unavailable slots for date {date}: {e}")
        return False

def update_unavailable_slots_range(start_date, end_date, time_slots):
    """Update unavailable slots for a date range"""
    from datetime import datetime, timedelta
    
    try:
        # Parse dates
        start_dt = datetime.strptime(start_date, '%Y-%m-%d').replace(tzinfo=ZoneInfo("Australia/Perth"))
        end_dt = datetime.strptime(end_date, '%Y-%m-%d').replace(tzinfo=ZoneInfo("Australia/Perth"))
        
        if end_dt < start_dt:
            print(f"Error: End date {end_date} is before start date {start_date}")
            return False
        
        # Build time slots list for DynamoDB
        time_slots_list = []
        for slot in time_slots:
            time_slots_list.append({
                'M': {
                    'startTime': {'S': slot['startTime']},
                    'endTime': {'S': slot['endTime']}
                }
            })
        
        # Update slots for each date in the range
        current_date = start_dt
        success_count = 0
        total_dates = (end_dt - start_dt).days + 1
        
        while current_date <= end_dt:
            date_str = current_date.strftime('%Y-%m-%d')
            try:
                dynamodb.put_item(
                    TableName=UNAVAILABLE_SLOTS_TABLE,
                    Item={
                        'date': {'S': date_str},
                        'timeSlots': {'L': time_slots_list},
                        'updatedAt': {'N': str(int(datetime.now(ZoneInfo('Australia/Perth')).timestamp()))}
                    }
                )
                success_count += 1
                print(f"Unavailable slots updated for date {date_str}")
            except ClientError as e:
                print(f"Error updating unavailable slots for date {date_str}: {e}")
            
            current_date += timedelta(days=1)
        
        print(f"Updated unavailable slots for {success_count}/{total_dates} dates in range {start_date} to {end_date}")
        return success_count == total_dates
        
    except ValueError as e:
        print(f"Error parsing dates: {e}")
        return False
    except ClientError as e:
        print(f"Error updating unavailable slots for date range: {e}")
        return False

def get_unavailable_slots_range(start_date, end_date):
    """Get unavailable slots for a date range"""
    from datetime import datetime, timedelta
    
    try:
        # Parse dates
        start_dt = datetime.strptime(start_date, '%Y-%m-%d').replace(tzinfo=ZoneInfo("Australia/Perth"))
        end_dt = datetime.strptime(end_date, '%Y-%m-%d').replace(tzinfo=ZoneInfo("Australia/Perth"))
        
        if end_dt < start_dt:
            print(f"Error: End date {end_date} is before start date {start_date}")
            return {}
        
        result = {}
        current_date = start_dt
        
        while current_date <= end_dt:
            date_str = current_date.strftime('%Y-%m-%d')
            try:
                unavailable_slots = get_unavailable_slots(date_str)
                result[date_str] = unavailable_slots.get('timeSlots', []) if unavailable_slots else []
            except Exception as e:
                print(f"Error getting unavailable slots for date {date_str}: {e}")
                result[date_str] = []
            
            current_date += timedelta(days=1)
        
        return result
        
    except ValueError as e:
        print(f"Error parsing dates: {e}")
        return {}

# ------------------  Appointments Table Functions ------------------

def create_appointment(appointment_data):
    """Create a new appointment"""
    try:
        dynamodb.put_item(
            TableName=APPOINTMENTS_TABLE,
            Item=appointment_data
        )
        print(f"Appointment {appointment_data['appointmentId']['S']} created successfully")
        return True
    except ClientError as e:
        print(f"Error creating appointment: {e}")
        return False

def get_appointment(appointment_id):
    """Get an appointment by ID"""
    try:
        result = dynamodb.get_item(
            TableName=APPOINTMENTS_TABLE,
            Key={'appointmentId': {'S': appointment_id}}
        )
        if 'Item' in result:
            return deserialize_item_json_safe(result['Item'])
        return None
    except ClientError as e:
        print(f"Error getting appointment {appointment_id}: {e}")
        return None

def update_appointment(appointment_id, update_data):
    """Update an existing appointment"""
    try:
        update_expression, expression_values, expression_names = build_update_expression_for_appointment(update_data)
        if update_expression:
            update_params = {
                'TableName': APPOINTMENTS_TABLE,
                'Key': {'appointmentId': {'S': appointment_id}},
                'UpdateExpression': update_expression,
                'ExpressionAttributeValues': expression_values
            }
            
            # Add expression attribute names if they exist
            if expression_names:
                update_params['ExpressionAttributeNames'] = expression_names
            
            dynamodb.update_item(**update_params)
            print(f"Appointment {appointment_id} updated successfully")
            return True
        else:
            print("No valid update data provided")
            return False
    except ClientError as e:
        print(f"Error updating appointment {appointment_id}: {e}")
        return False

def get_all_appointments():
    """Get all appointments"""
    try:
        result = dynamodb.scan(TableName=APPOINTMENTS_TABLE)
        return [deserialize_item_json_safe(item) for item in result.get('Items', [])]
    except ClientError as e:
        print(f"Error scanning all appointments: {e}")
        return []

def get_appointments_by_created_user(user_id):
    """Get appointments created by a specific user"""
    try:
        result = dynamodb.query(
            TableName=APPOINTMENTS_TABLE,
            IndexName='createdUserId-index',
            KeyConditionExpression='createdUserId = :userId',
            ExpressionAttributeValues={':userId': {'S': user_id}}
        )
        return [deserialize_item_json_safe(item) for item in result.get('Items', [])]
    except ClientError as e:
        print(f"Error getting appointments for created user {user_id}: {e}")
        return []

def get_appointments_by_assigned_mechanic(mechanic_id):
    """Get appointments assigned to a specific mechanic"""
    try:
        result = dynamodb.query(
            TableName=APPOINTMENTS_TABLE,
            IndexName='assignedMechanicId-index',
            KeyConditionExpression='assignedMechanicId = :mechanicId',
            ExpressionAttributeValues={':mechanicId': {'S': mechanic_id}}
        )
        return [deserialize_item_json_safe(item) for item in result.get('Items', [])]
    except ClientError as e:
        print(f"Error getting appointments for assigned mechanic {mechanic_id}: {e}")
        return []

def get_appointments_by_scheduled_date(scheduled_date):
    """Get appointments scheduled for a specific date"""
    try:
        result = dynamodb.query(
            TableName=APPOINTMENTS_TABLE,
            IndexName='scheduledDate-index',
            KeyConditionExpression='scheduledDate = :date',
            ExpressionAttributeValues={':date': {'S': scheduled_date}}
        )
        return [deserialize_item_json_safe(item) for item in result.get('Items', [])]
    except ClientError as e:
        print(f"Error getting appointments for scheduled date {scheduled_date}: {e}")
        return []
    
def get_appointments_by_status(status):
    """Get appointments by status"""
    try:
        result = dynamodb.query(
            TableName=APPOINTMENTS_TABLE,
            IndexName='status-index',
            KeyConditionExpression='#status = :status',
            ExpressionAttributeNames={'#status': 'status'},
            ExpressionAttributeValues={':status': {'S': status}}
        )
        return [deserialize_item_json_safe(item) for item in result.get('Items', [])]
    except ClientError as e:
        print(f"Error getting appointments for status {status}: {e}")
        return []

def build_update_expression_for_appointment(data):
    """Build update expression for appointment updates"""
    update_parts = []
    remove_parts = []
    expression_values = {}
    expression_names = {}
    
    # DynamoDB reserved keywords that need expression attribute names
    reserved_keywords = {
        'status', 'name', 'type', 'value', 'size', 'order', 'date', 
        'time', 'user', 'group', 'role', 'data', 'count', 'index', 'items'
    }
    
    for key, value in data.items():
        if value is not None:
            # Handle secondary index fields with empty values
            if key in ['assignedMechanicId', 'scheduledDate'] and (value == '' or value == {}):
                # Remove the attribute if it's empty to avoid secondary index issues
                remove_parts.append(key)
            elif key == 'scheduledTimeSlot' and (not value or value == {}):
                # Remove scheduledTimeSlot if it's empty
                remove_parts.append(key)
            else:
                # Use expression attribute names for reserved keywords
                if key.lower() in reserved_keywords:
                    attr_name = f'#{key}'
                    expression_names[attr_name] = key
                    update_parts.append(f'{attr_name} = :{key}')
                else:
                    update_parts.append(f'{key} = :{key}')
                
                # Handle different data types for DynamoDB
                if isinstance(value, str):
                    expression_values[f':{key}'] = {'S': value}
                elif isinstance(value, int):
                    expression_values[f':{key}'] = {'N': str(value)}
                elif isinstance(value, float):
                    expression_values[f':{key}'] = {'N': str(value)}
                elif isinstance(value, Decimal):
                    expression_values[f':{key}'] = {'N': str(value)}
                elif isinstance(value, bool):
                    expression_values[f':{key}'] = {'BOOL': value}
                elif isinstance(value, dict):
                    # Check if it's already in DynamoDB format
                    if is_dynamodb_format(value):
                        expression_values[f':{key}'] = value
                    else:
                        expression_values[f':{key}'] = convert_to_dynamodb_format(value)
                elif isinstance(value, list):
                    # Check if it's already in DynamoDB format
                    if value and is_dynamodb_format(value[0]) if value else False:
                        expression_values[f':{key}'] = {'L': value}
                    else:
                        expression_values[f':{key}'] = convert_to_dynamodb_format(value)
    
    update_expression_parts = []
    if update_parts:
        update_expression_parts.append('SET ' + ', '.join(update_parts))
    if remove_parts:
        update_expression_parts.append('REMOVE ' + ', '.join(remove_parts))
    
    if update_expression_parts:
        update_expression = ' '.join(update_expression_parts)
        return update_expression, expression_values, expression_names
    return None, None, None

def build_appointment_data(appointment_id, service_id, plan_id, is_buyer, buyer_data, car_data, seller_data, notes, selected_slots, created_user_id, price):
    """Build appointment data in DynamoDB format"""
    current_time = int(datetime.now(ZoneInfo('Australia/Perth')).timestamp())
    current_date = datetime.now(ZoneInfo('Australia/Perth')).strftime('%Y-%m-%d')
    
    # Convert selected slots to DynamoDB format
    slots_list = []
    for slot in selected_slots:
        slots_list.append({
            'M': {
                'date': {'S': slot['date']},
                'start': {'S': slot['start']},
                'end': {'S': slot['end']},
                'priority': {'N': str(slot['priority'])}
            }
        })
    
    appointment_data = {
        'appointmentId': {'S': appointment_id},
        'serviceId': {'N': str(service_id)},
        'planId': {'N': str(plan_id)},
        'isBuyer': {'BOOL': is_buyer},
        'buyerName': {'S': buyer_data.get('name', '')},
        'buyerEmail': {'S': buyer_data.get('email', '')},
        'buyerPhone': {'S': buyer_data.get('phoneNumber', '')},
        'carMake': {'S': car_data.get('make', '')},
        'carModel': {'S': car_data.get('model', '')},
        'carYear': {'S': str(car_data.get('year', ''))},
        'carLocation': {'S': car_data.get('location', '')},
        'sellerName': {'S': seller_data.get('name', '')},
        'sellerEmail': {'S': seller_data.get('email', '')},
        'sellerPhone': {'S': seller_data.get('phoneNumber', '')},
        'notes': {'S': notes},
        'selectedSlots': {'L': slots_list},
        'createdUserId': {'S': created_user_id},
        'status': {'S': 'PENDING'},
        'price': {'N': str(price)},
        'paymentStatus': {'S': 'pending'},
        'postNotes': {'S': ''},
        'reports': {'L': []},
        'createdAt': {'N': str(current_time)},
        'createdDate': {'S': current_date},
        'updatedAt': {'N': str(current_time)}
    }
    
    return appointment_data

def get_daily_unpaid_appointments_count(user_id, today):
    """Get count of unpaid appointments for a user on a specific day"""
    try:
        today_str = today.strftime('%Y-%m-%d') if hasattr(today, 'strftime') else str(today)
        result = dynamodb.query(
            TableName=APPOINTMENTS_TABLE,
            IndexName='createdUserId-index',
            KeyConditionExpression='createdUserId = :uid',
            FilterExpression='createdDate = :date AND paymentStatus <> :paid',
            ExpressionAttributeValues={
                ':uid': {'S': user_id},
                ':date': {'S': today_str},
                ':paid': {'S': 'paid'}
            }
        )
        return result.get('Count', 0)
    except ClientError as e:
        print(f"Error getting daily unpaid appointments count for user {user_id}: {e}")
        return 0


# ------------------  Service Pricing Table Functions ------------------

def get_service_plan_names(service_id, plan_id):
    """Get service plan names by service_id and plan_id"""
    try:
        result = dynamodb.get_item(
            TableName=SERVICE_PRICES_TABLE,
            Key={
                'serviceId': {'N': str(service_id)},
                'planId': {'N': str(plan_id)}
            }
        )
        if 'Item' in result:
            item = deserialize_item(result['Item'])
            return item.get('serviceName'), item.get('planName')
        return None
    except ClientError as e:
        print(f"Error getting service plan name for service {service_id} and plan {plan_id}: {e}")
        return None

def get_service_pricing(service_id, plan_id):
    """Get service pricing by service_id and plan_id, return only the price field"""
    try:
        result = dynamodb.get_item(
            TableName=SERVICE_PRICES_TABLE,
            Key={
                'serviceId': {'N': str(service_id)},
                'planId': {'N': str(plan_id)}
            }
        )
        if 'Item' in result:
            item = deserialize_item(result['Item'])
            return item.get('price')
        return None
    except ClientError as e:
        print(f"Error getting service pricing for service {service_id} and plan {plan_id}: {e}")
        return None

def get_all_service_prices():
    """Get all service pricing records"""
    try:
        result = dynamodb.scan(TableName=SERVICE_PRICES_TABLE)
        return [deserialize_item(item) for item in result.get('Items', [])]
    except ClientError as e:
        print(f"Error scanning service pricing records: {e}")
        return []

# ------------------  Orders Table Functions ------------------

def create_order(order_data):
    """Create a new order"""
    try:
        dynamodb.put_item(
            TableName=ORDERS_TABLE,
            Item=order_data
        )
        print(f"Order {order_data['orderId']['S']} created successfully")
        return True
    except ClientError as e:
        print(f"Error creating order: {e}")
        return False

def get_order(order_id):
    """Get an order by ID"""
    try:
        result = dynamodb.get_item(
            TableName=ORDERS_TABLE,
            Key={'orderId': {'S': order_id}}
        )
        if 'Item' in result:
            return deserialize_item(result['Item'])
        return None
    except ClientError as e:
        print(f"Error getting order {order_id}: {e}")
        return None

def update_order(order_id, update_data):
    """Update an existing order"""
    try:
        update_expression, expression_values, expression_names = build_update_expression_for_order(update_data)
        if update_expression:
            update_params = {
                'TableName': ORDERS_TABLE,
                'Key': {'orderId': {'S': order_id}},
                'UpdateExpression': update_expression,
                'ExpressionAttributeValues': expression_values
            }
            
            # Add expression attribute names if they exist
            if expression_names:
                update_params['ExpressionAttributeNames'] = expression_names
            
            dynamodb.update_item(**update_params)
            print(f"Order {order_id} updated successfully")
            return True
        else:
            print("No valid update data provided")
            return False
    except ClientError as e:
        print(f"Error updating order {order_id}: {e}")
        return False

def get_all_orders():
    """Get all orders"""
    try:
        result = dynamodb.scan(TableName=ORDERS_TABLE)
        return [deserialize_item(item) for item in result.get('Items', [])]
    except ClientError as e:
        print(f"Error scanning all orders: {e}")
        return []

def get_orders_by_created_user(user_id):
    """Get orders created by a specific user"""
    try:
        result = dynamodb.query(
            TableName=ORDERS_TABLE,
            IndexName='createdUserId-index',
            KeyConditionExpression='createdUserId = :userId',
            ExpressionAttributeValues={':userId': {'S': user_id}}
        )
        return [deserialize_item(item) for item in result.get('Items', [])]
    except ClientError as e:
        print(f"Error getting orders for created user {user_id}: {e}")
        return []

def get_orders_by_assigned_mechanic(mechanic_id):
    """Get orders assigned to a specific mechanic"""
    try:
        result = dynamodb.query(
            TableName=ORDERS_TABLE,
            IndexName='assignedMechanicId-index',
            KeyConditionExpression='assignedMechanicId = :mechanicId',
            ExpressionAttributeValues={':mechanicId': {'S': mechanic_id}}
        )
        return [deserialize_item(item) for item in result.get('Items', [])]
    except ClientError as e:
        print(f"Error getting orders for assigned mechanic {mechanic_id}: {e}")
        return []

def get_daily_unpaid_orders_count(user_id, today):
    """Get count of unpaid orders for a user on a specific day"""
    try:
        today_str = today.strftime('%Y-%m-%d') if hasattr(today, 'strftime') else str(today)
        result = dynamodb.query(
            TableName=ORDERS_TABLE,
            IndexName='createdUserId-index',
            KeyConditionExpression='createdUserId = :uid',
            FilterExpression='createdDate = :date AND paymentStatus <> :paid',
            ExpressionAttributeValues={
                ':uid': {'S': user_id},
                ':date': {'S': today_str},
                ':paid': {'S': 'paid'}
            }
        )
        return result.get('Count', 0)
    except ClientError as e:
        print(f"Error getting daily unpaid orders count for user {user_id}: {e}")
        return 0

def build_update_expression_for_order(data):
    """Build update expression for order updates"""
    update_parts = []
    remove_parts = []
    expression_values = {}
    expression_names = {}
    
    # DynamoDB reserved keywords that need expression attribute names
    reserved_keywords = {
        'status', 'name', 'type', 'value', 'size', 'order', 'date', 
        'time', 'user', 'group', 'role', 'data', 'count', 'index', 'items'
    }
    
    for key, value in data.items():
        if value is not None:
            # Handle secondary index fields with empty values
            if key == 'assignedMechanicId' and value == '':
                # Remove the attribute if it's empty to avoid secondary index issues
                remove_parts.append(key)
            else:
                # Use expression attribute names for reserved keywords
                if key.lower() in reserved_keywords:
                    attr_name = f'#{key}'
                    expression_names[attr_name] = key
                    update_parts.append(f'{attr_name} = :{key}')
                else:
                    update_parts.append(f'{key} = :{key}')
                
                # Handle different data types for DynamoDB
                if isinstance(value, str):
                    expression_values[f':{key}'] = {'S': value}
                elif isinstance(value, int):
                    expression_values[f':{key}'] = {'N': str(value)}
                elif isinstance(value, float):
                    expression_values[f':{key}'] = {'N': str(value)}
                elif isinstance(value, Decimal):
                    expression_values[f':{key}'] = {'N': str(value)}
                elif isinstance(value, bool):
                    expression_values[f':{key}'] = {'BOOL': value}
                elif isinstance(value, dict):
                    # Check if it's already in DynamoDB format
                    if is_dynamodb_format(value):
                        expression_values[f':{key}'] = value
                    else:
                        expression_values[f':{key}'] = convert_to_dynamodb_format(value)
                elif isinstance(value, list):
                    # Check if it's already in DynamoDB format
                    if value and is_dynamodb_format(value[0]) if value else False:
                        expression_values[f':{key}'] = {'L': value}
                    else:
                        expression_values[f':{key}'] = convert_to_dynamodb_format(value)
    
    update_expression_parts = []
    if update_parts:
        update_expression_parts.append('SET ' + ', '.join(update_parts))
    if remove_parts:
        update_expression_parts.append('REMOVE ' + ', '.join(remove_parts))
    
    if update_expression_parts:
        update_expression = ' '.join(update_expression_parts)
        return update_expression, expression_values, expression_names
    return None, None, None

def build_order_data(order_id, items, customer_data, car_data, notes, delivery_location, created_user_id, total_price):
    """Build order data in DynamoDB format with support for multiple items"""
    current_time = int(datetime.now(ZoneInfo('Australia/Perth')).timestamp())
    current_date = datetime.now(ZoneInfo('Australia/Perth')).strftime('%Y-%m-%d')
    
    # Convert items list to DynamoDB format
    items_list = []
    for item in items:
        item_data = {
            'M': {
                'categoryId': {'N': str(item['categoryId'])},
                'itemId': {'N': str(item['itemId'])},
                'quantity': {'N': str(item['quantity'])},
                'unitPrice': {'N': str(item['unitPrice'])},
                'totalPrice': {'N': str(item['totalPrice'])}
            }
        }
        items_list.append(item_data)
    
    order_data = {
        'orderId': {'S': order_id},
        'items': {'L': items_list},
        'customerName': {'S': customer_data.get('name', '')},
        'customerEmail': {'S': customer_data.get('email', '')},
        'customerPhone': {'S': customer_data.get('phoneNumber', '')},
        'carMake': {'S': car_data.get('make', '')},
        'carModel': {'S': car_data.get('model', '')},
        'carYear': {'S': str(car_data.get('year', ''))},
        'notes': {'S': notes},
        'deliveryLocation': {'S': delivery_location},
        'createdUserId': {'S': created_user_id},
        'status': {'S': 'PENDING'},
        'totalPrice': {'N': str(total_price)},
        'paymentStatus': {'S': 'pending'},
        'postNotes': {'S': ''},
        'createdAt': {'N': str(current_time)},
        'createdDate': {'S': current_date},
        'updatedAt': {'N': str(current_time)}
    }
    
    return order_data


# ------------------  Item Prices Table Functions ------------------

def get_category_item_names(category_id, item_id):
    """Get category item names by category_id and item_id"""
    try:
        result = dynamodb.get_item(
            TableName=ITEM_PRICES_TABLE,
            Key={
                'categoryId': {'N': str(category_id)},
                'itemId': {'N': str(item_id)}
            }
        )
        if 'Item' in result:
            item = deserialize_item(result['Item'])
            return item.get('categoryName'), item.get('itemName')
        return None
    except ClientError as e:
        print(f"Error getting item name for category {category_id} and item {item_id}: {e}")
        return None

def get_item_pricing(category_id, item_id):
    """Get item pricing by category_id and item_id, return only the price field"""
    try:
        result = dynamodb.get_item(
            TableName=ITEM_PRICES_TABLE,
            Key={
                'categoryId': {'N': str(category_id)},
                'itemId': {'N': str(item_id)}
            }
        )
        if 'Item' in result:
            item = deserialize_item(result['Item'])
            return item.get('price')
        return None
    except ClientError as e:
        print(f"Error getting item pricing for category {category_id} and item {item_id}: {e}")
        return None

def get_all_item_prices():
    """Get all item pricing records"""
    try:
        result = dynamodb.scan(TableName=ITEM_PRICES_TABLE)
        return [deserialize_item(item) for item in result.get('Items', [])]
    except ClientError as e:
        print(f"Error scanning item pricing records: {e}")
        return []

# ------------------  Inquiries Table Functions ------------------

def create_inquiry(inquiry_data):
    """Create a new inquiry"""
    try:
        dynamodb.put_item(
            TableName=INQUIRIES_TABLE,
            Item=inquiry_data
        )
        print(f"Inquiry {inquiry_data['inquiryId']['S']} created successfully")
        return True
    except ClientError as e:
        print(f"Error creating inquiry: {e}")
        return False

def get_inquiry(inquiry_id):
    """Get an inquiry by ID"""
    try:
        result = dynamodb.get_item(
            TableName=INQUIRIES_TABLE,
            Key={'inquiryId': {'S': inquiry_id}}
        )
        if 'Item' in result:
            return deserialize_item(result['Item'])
        return None
    except ClientError as e:
        print(f"Error getting inquiry {inquiry_id}: {e}")
        return None

def get_all_inquiries():
    """Get all inquiries"""
    try:
        result = dynamodb.scan(TableName=INQUIRIES_TABLE)
        return [deserialize_item(item) for item in result.get('Items', [])]
    except ClientError as e:
        print(f"Error scanning all inquiries: {e}")
        return []

def build_inquiry_data(inquiry_id, first_name, last_name, email, message, user_id):
    """Build inquiry data in DynamoDB format"""
    current_time = int(datetime.now(ZoneInfo('Australia/Perth')).timestamp())
    current_date = datetime.now(ZoneInfo('Australia/Perth')).strftime('%Y-%m-%d')
    
    inquiry_data = {
        'inquiryId': {'S': inquiry_id},
        'firstName': {'S': first_name},
        'lastName': {'S': last_name},
        'email': {'S': email},
        'message': {'S': message},
        'userId': {'S': user_id},
        'createdAt': {'N': str(current_time)},
        'createdDate': {'S': current_date}
    }
    
    return inquiry_data

# ------------------  Payment Table Functions ------------------

def create_payment(payment_data):
    """Create a new payment record"""
    try:
        # Convert payment data to DynamoDB format
        item = {
            'paymentIntentId': {'S': payment_data['paymentIntentId']},
            'referenceNumber': {'S': payment_data['referenceNumber']},
            'type': {'S': payment_data['type']},
            'userId': {'S': payment_data['userId']},
            'amount': {'N': str(payment_data['amount'])},
            'currency': {'S': payment_data['currency']},
            'status': {'S': payment_data['status']},
            'createdAt': {'N': str(payment_data['createdAt'])},
            'updatedAt': {'N': str(payment_data['updatedAt'])}
        }
        
        # Add optional fields
        if 'stripePaymentMethodId' in payment_data:
            item['stripePaymentMethodId'] = {'S': payment_data['stripePaymentMethodId']}
        if 'receiptUrl' in payment_data:
            item['receiptUrl'] = {'S': payment_data['receiptUrl']}
        if 'metadata' in payment_data:
            item['metadata'] = {'S': payment_data['metadata']}
        
        dynamodb.put_item(
            TableName=PAYMENTS_TABLE,
            Item=item
        )
        print(f"Payment {payment_data['paymentIntentId']} created successfully")
        return True
    except ClientError as e:
        print(f"Error creating payment: {e}")
        return False

def get_payment_by_intent_id(payment_intent_id):
    """Get a payment record by payment intent ID"""
    try:
        result = dynamodb.get_item(
            TableName=PAYMENTS_TABLE,
            Key={'paymentIntentId': {'S': payment_intent_id}}
        )
        if 'Item' in result:
            return deserialize_item_json_safe(result['Item'])
        return None
    except ClientError as e:
        print(f"Error getting payment by intent ID {payment_intent_id}: {e}")
        return None

def update_payment_by_intent_id(payment_intent_id, update_data):
    """Update a payment record by payment intent ID"""
    try:
        update_expression, expression_values, expression_names = build_update_expression_for_payment(update_data)
        if update_expression:
            update_params = {
                'TableName': PAYMENTS_TABLE,
                'Key': {'paymentIntentId': {'S': payment_intent_id}},
                'UpdateExpression': update_expression,
                'ExpressionAttributeValues': expression_values
            }
            
            # Add expression attribute names if they exist
            if expression_names:
                update_params['ExpressionAttributeNames'] = expression_names
            
            dynamodb.update_item(**update_params)
            print(f"Payment {payment_intent_id} updated successfully")
            return True
        else:
            print("No valid update data provided")
            return False
    except ClientError as e:
        print(f"Error updating payment {payment_intent_id}: {e}")
        return False

def get_payments_by_user(user_id):
    """Get all payments for a specific user"""
    try:
        result = dynamodb.query(
            TableName=PAYMENTS_TABLE,
            IndexName='userId-index',
            KeyConditionExpression='userId = :uid',
            ExpressionAttributeValues={':uid': {'S': user_id}}
        )
        return [deserialize_item_json_safe(item) for item in result.get('Items', [])]
    except ClientError as e:
        print(f"Error getting payments by user {user_id}: {e}")
        return []

def build_update_expression_for_payment(update_data):
    """Build update expression for payment table"""
    update_expression = "SET "
    expression_values = {}
    expression_names = {}
    updates = []

    for key, value in update_data.items():
        if value is not None:
            attr_name = f"#{key}"
            attr_value = f":{key}"
            updates.append(f"{attr_name} = {attr_value}")
            expression_names[attr_name] = key
            
            # Handle different data types
            if isinstance(value, str):
                expression_values[attr_value] = {'S': value}
            elif isinstance(value, (int, float)):
                expression_values[attr_value] = {'N': str(value)}
            elif isinstance(value, bool):
                expression_values[attr_value] = {'BOOL': value}
            else:
                expression_values[attr_value] = {'S': str(value)}

    if updates:
        update_expression += ", ".join(updates)
        return update_expression, expression_values, expression_names
    else:
        return None, None, None

# ------------------ Invoice Table Functions ------------------

def get_all_invoices():
    """Get all invoices from the database"""
    try:
        invoices = []
        
        # Start with an initial scan
        scan_kwargs = {
            'TableName': INVOICES_TABLE
        }
        
        response = dynamodb.scan(**scan_kwargs)
        invoices.extend([deserialize_item_json_safe(item) for item in response.get('Items', [])])
        
        # Continue scanning if there are more items
        while 'LastEvaluatedKey' in response:
            scan_kwargs['ExclusiveStartKey'] = response['LastEvaluatedKey']
            response = dynamodb.scan(**scan_kwargs)
            invoices.extend([deserialize_item_json_safe(item) for item in response.get('Items', [])])
        
        return invoices
    except ClientError as e:
        print(f"Error getting all invoices: {e}")
        return []

def get_active_invoices():
    """Get all active invoices (excluding cancelled ones) from the database"""
    try:
        invoices = []
        
        # Start with an initial scan with filter expression
        scan_kwargs = {
            'TableName': INVOICES_TABLE,
            'FilterExpression': 'attribute_not_exists(#status) OR #status <> :cancelled_status',
            'ExpressionAttributeNames': {
                '#status': 'status'
            },
            'ExpressionAttributeValues': {
                ':cancelled_status': {'S': 'cancelled'}
            }
        }
        
        response = dynamodb.scan(**scan_kwargs)
        invoices.extend([deserialize_item_json_safe(item) for item in response.get('Items', [])])
        
        # Continue scanning if there are more items
        while 'LastEvaluatedKey' in response:
            scan_kwargs['ExclusiveStartKey'] = response['LastEvaluatedKey']
            response = dynamodb.scan(**scan_kwargs)
            invoices.extend([deserialize_item_json_safe(item) for item in response.get('Items', [])])
        
        return invoices
    except ClientError as e:
        print(f"Error getting active invoices: {e}")
        return []

def get_invoices_by_date_range(start_date, end_date, limit=100):
    """
    Get active invoices within a date range using effectiveDate for analytics processing
    
    This function filters invoices based on the effectiveDate field from analyticsData.operation_data
    instead of createdAt, ensuring all date-related analytics operations use consistent date logic.
    
    IMPORTANT: This function EXCLUDES cancelled invoices. For admin purposes where all invoices 
    (including cancelled ones) are needed, use get_all_invoices_by_date_range() instead.
    
    Args:
        start_date: Start timestamp
        end_date: End timestamp  
        limit: Maximum number of results to return
        
    Returns:
        list: Filtered active invoices sorted by effectiveDate (most recent first)
    """
    try:
        # Get all invoices first, then filter by effectiveDate from analyticsData
        # This is necessary because effectiveDate is stored in a nested JSON field
        result = dynamodb.scan(
            TableName=INVOICES_TABLE,
            Limit=limit * 2  # Get more to account for filtering
        )
        
        all_invoices = [deserialize_item_json_safe(item) for item in result.get('Items', [])]
        
        # Convert start_date and end_date timestamps to DD/MM/YYYY format for comparison
        start_date_formatted = datetime.fromtimestamp(start_date, ZoneInfo('Australia/Perth')).strftime('%d/%m/%Y')
        end_date_formatted = datetime.fromtimestamp(end_date, ZoneInfo('Australia/Perth')).strftime('%d/%m/%Y')
        
        # Filter invoices by effectiveDate from analyticsData and exclude cancelled ones
        filtered_invoices = []
        for invoice in all_invoices:
            # Skip cancelled invoices
            if invoice.get('status') == 'cancelled':
                continue
                
            analytics_data = invoice.get('analyticsData', {})
            operation_data = analytics_data.get('operation_data', {})
            effective_date = operation_data.get('effectiveDate', '')
            
            if effective_date:
                try:
                    # Validate and normalize effectiveDate to DD/MM/YYYY format
                    normalized_effective_date = valid.DataValidator.validate_and_convert_date_to_analytics_format(
                        effective_date, 'effectiveDate'
                    )
                    
                    # Convert dates to comparable datetime objects
                    effective_date_obj = datetime.strptime(normalized_effective_date, '%d/%m/%Y').replace(tzinfo=ZoneInfo("Australia/Perth"))
                    start_date_obj = datetime.strptime(start_date_formatted, '%d/%m/%Y').replace(tzinfo=ZoneInfo("Australia/Perth"))
                    end_date_obj = datetime.strptime(end_date_formatted, '%d/%m/%Y').replace(tzinfo=ZoneInfo("Australia/Perth"))
                    
                    if start_date_obj <= effective_date_obj <= end_date_obj:
                        filtered_invoices.append(invoice)
                except (ValueError, valid.ValidationError) as e:
                    # If effectiveDate format is invalid, log warning and skip this invoice
                    print(f"Warning: Invalid effectiveDate format '{effective_date}' in invoice {invoice.get('invoiceId', 'unknown')}: {e}")
                    continue
            else:
                # If no effectiveDate, fall back to createdAt for backward compatibility
                created_at = invoice.get('createdAt', 0)
                if start_date <= created_at <= end_date:
                    filtered_invoices.append(invoice)
        
        # Sort by effectiveDate (most recent first) and limit results
        def get_sort_key(invoice):
            analytics_data = invoice.get('analyticsData', {})
            operation_data = analytics_data.get('operation_data', {})
            effective_date = operation_data.get('effectiveDate', '')
            
            if effective_date:
                try:
                    return datetime.strptime(effective_date, '%d/%m/%Y').replace(tzinfo=ZoneInfo("Australia/Perth"))
                except ValueError:
                    # Fall back to createdAt if effectiveDate is invalid
                    return datetime.fromtimestamp(invoice.get('createdAt', 0), ZoneInfo('Australia/Perth'))
            else:
                # Fall back to createdAt if no effectiveDate
                return datetime.fromtimestamp(invoice.get('createdAt', 0), ZoneInfo('Australia/Perth'))
        
        filtered_invoices.sort(key=get_sort_key, reverse=True)
        
        return filtered_invoices[:limit]
        
    except ClientError as e:
        print(f"Error querying invoices by date range: {e}")
        return []

def get_all_invoices_by_date_range(start_date, end_date, limit=100):
    """
    Get ALL invoices (including cancelled ones) within a date range for admin purposes
    
    This function filters invoices based on the effectiveDate field from analyticsData.operation_data
    instead of createdAt, ensuring all date-related operations use consistent date logic.
    Unlike get_invoices_by_date_range, this function includes cancelled invoices.
    
    Args:
        start_date: Start timestamp
        end_date: End timestamp  
        limit: Maximum number of results to return
        
    Returns:
        list: Filtered invoices including cancelled ones sorted by effectiveDate (most recent first)
    """
    try:
        # Get all invoices first, then filter by effectiveDate from analyticsData
        # This is necessary because effectiveDate is stored in a nested JSON field
        result = dynamodb.scan(
            TableName=INVOICES_TABLE,
            Limit=limit * 2  # Get more to account for filtering
        )
        
        all_invoices = [deserialize_item_json_safe(item) for item in result.get('Items', [])]
        
        # Convert start_date and end_date timestamps to DD/MM/YYYY format for comparison
        start_date_formatted = datetime.fromtimestamp(start_date, ZoneInfo('Australia/Perth')).strftime('%d/%m/%Y')
        end_date_formatted = datetime.fromtimestamp(end_date, ZoneInfo('Australia/Perth')).strftime('%d/%m/%Y')
        
        # Filter invoices by effectiveDate from analyticsData (including cancelled ones)
        filtered_invoices = []
        for invoice in all_invoices:
            # NOTE: Unlike get_invoices_by_date_range, we DO NOT skip cancelled invoices here
            
            analytics_data = invoice.get('analyticsData', {})
            operation_data = analytics_data.get('operation_data', {})
            effective_date = operation_data.get('effectiveDate', '')
            
            if effective_date:
                try:
                    # Validate and normalize effectiveDate to DD/MM/YYYY format
                    normalized_effective_date = valid.DataValidator.validate_and_convert_date_to_analytics_format(
                        effective_date, 'effectiveDate'
                    )
                    
                    # Convert dates to comparable datetime objects
                    effective_date_obj = datetime.strptime(normalized_effective_date, '%d/%m/%Y').replace(tzinfo=ZoneInfo("Australia/Perth"))
                    start_date_obj = datetime.strptime(start_date_formatted, '%d/%m/%Y').replace(tzinfo=ZoneInfo("Australia/Perth"))
                    end_date_obj = datetime.strptime(end_date_formatted, '%d/%m/%Y').replace(tzinfo=ZoneInfo("Australia/Perth"))
                    
                    if start_date_obj <= effective_date_obj <= end_date_obj:
                        filtered_invoices.append(invoice)
                except (ValueError, valid.ValidationError) as e:
                    # If effectiveDate format is invalid, log warning and skip this invoice
                    print(f"Warning: Invalid effectiveDate format '{effective_date}' in invoice {invoice.get('invoiceId', 'unknown')}: {e}")
                    continue
            else:
                # If no effectiveDate, fall back to createdAt for backward compatibility
                created_at = invoice.get('createdAt', 0)
                if start_date <= created_at <= end_date:
                    filtered_invoices.append(invoice)
        
        # Sort by effectiveDate (most recent first) and limit results
        def get_sort_key(invoice):
            analytics_data = invoice.get('analyticsData', {})
            operation_data = analytics_data.get('operation_data', {})
            effective_date = operation_data.get('effectiveDate', '')
            
            if effective_date:
                try:
                    return datetime.strptime(effective_date, '%d/%m/%Y').replace(tzinfo=ZoneInfo("Australia/Perth"))
                except ValueError:
                    # Fall back to createdAt if effectiveDate is invalid
                    return datetime.fromtimestamp(invoice.get('createdAt', 0), ZoneInfo('Australia/Perth'))
            else:
                # Fall back to createdAt if no effectiveDate
                return datetime.fromtimestamp(invoice.get('createdAt', 0), ZoneInfo('Australia/Perth'))
        
        filtered_invoices.sort(key=get_sort_key, reverse=True)
        
        return filtered_invoices[:limit]
        
    except ClientError as e:
        print(f"Error querying all invoices by date range: {e}")
        return []

def create_invoice_record(invoice_data):
    """Create a new invoice record in the database"""
    try:
        # Prepare item data with required fields
        item = {
            'invoiceId': {'S': invoice_data['invoiceId']},
            'paymentIntentId': {'S': invoice_data['paymentIntentId']},
            'referenceNumber': {'S': invoice_data['referenceNumber']},
            'referenceType': {'S': invoice_data['referenceType']},
            's3Key': {'S': invoice_data['s3Key']},
            'fileUrl': {'S': invoice_data['fileUrl']},
            'fileSize': {'N': str(invoice_data['fileSize'])},
            'format': {'S': invoice_data.get('format', 'html')},
            'createdAt': {'N': str(invoice_data['createdAt'])},
            'status': {'S': invoice_data.get('status', 'generated')}
        }
        
        if 'metadata' in invoice_data:
            if isinstance(invoice_data['metadata'], dict):
                # Convert dict to DynamoDB Map format if needed
                if invoice_data['metadata']:  # Only add if not empty
                    item['metadata'] = convert_to_dynamodb_format(invoice_data['metadata'])
            else:
                item['metadata'] = {'M': {}}
        
        # Add analytics data if present
        if 'analyticsData' in invoice_data and invoice_data['analyticsData']:
            item['analyticsData'] = convert_to_dynamodb_format(invoice_data['analyticsData'])
        
        dynamodb.put_item(
            TableName=INVOICES_TABLE,
            Item=item
        )
        print(f"Invoice {invoice_data['invoiceId']} created successfully")
        return True
    except ClientError as e:
        print(f"Error creating invoice: {e}")
        return False

def get_invoice_by_reference(reference_number, reference_type):
    """Get invoice by reference number and type - returns the latest one if multiple exist"""
    try:
        # Use a scan to find invoice by reference number and type
        response = dynamodb.scan(
            TableName=INVOICES_TABLE,
            FilterExpression='referenceNumber = :ref AND referenceType = :type',
            ExpressionAttributeValues={
                ':ref': {'S': reference_number},
                ':type': {'S': reference_type}
            }
        )
        items = response.get('Items', [])
        if items:
            # If multiple invoices exist, return the latest one (highest createdAt)
            if len(items) > 1:
                # Sort by createdAt in descending order and take the first (latest)
                items.sort(key=lambda x: int(x.get('createdAt', {}).get('N', '0')), reverse=True)
                print(f"Found {len(items)} invoices for {reference_type} {reference_number}, returning the latest one")
            return deserialize_item_json_safe(items[0])
        return None
    except ClientError as e:
        print(f"Error getting invoice by reference {reference_number}: {e}")
        return None

def has_active_invoices(reference_number, reference_type):
    """Check if there are any active (non-cancelled) invoices for a reference"""
    try:
        invoices = get_invoices_by_reference(reference_number, reference_type)
        if not invoices:
            return False
        
        # Check if any invoice is not cancelled
        for invoice in invoices:
            if invoice.get('status') != 'cancelled':
                return True
        
        return False
    except Exception as e:
        print(f"Error checking for active invoices for {reference_type} {reference_number}: {e}")
        return False

def get_active_invoice_by_reference(reference_number, reference_type):
    """Get the latest active (non-cancelled) invoice by reference number and type"""
    try:
        invoices = get_invoices_by_reference(reference_number, reference_type)
        if not invoices:
            return None
        
        # Filter out cancelled invoices and get the latest active one
        active_invoices = [inv for inv in invoices if inv.get('status') != 'cancelled']
        if not active_invoices:
            return None
            
        # If multiple active invoices exist, return the latest one (highest createdAt)
        if len(active_invoices) > 1:
            active_invoices.sort(key=lambda x: x.get('createdAt', 0), reverse=True)
            print(f"Found {len(active_invoices)} active invoices for {reference_type} {reference_number}, returning the latest one")
        
        return active_invoices[0]
    except Exception as e:
        print(f"Error getting active invoice by reference {reference_number} ({reference_type}): {e}")
        return None

def update_invoice_analytics_data(invoice_id, analytics_data):
    """Update analytics data for an existing invoice"""
    try:
        dynamodb.update_item(
            TableName=INVOICES_TABLE,
            Key={'invoiceId': {'S': invoice_id}},
            UpdateExpression='SET analyticsData = :analytics_data',
            ExpressionAttributeValues={
                ':analytics_data': convert_to_dynamodb_format(analytics_data)
            }
        )
        print(f"Invoice {invoice_id} analytics data updated successfully")
        return True
    except ClientError as e:
        print(f"Error updating invoice analytics data for {invoice_id}: {e}")
        return False

def get_invoices_by_reference(reference_number, reference_type):
    """Get all invoices by reference number and type"""
    try:
        # Use a scan to find all invoices by reference number and type
        response = dynamodb.scan(
            TableName=INVOICES_TABLE,
            FilterExpression='referenceNumber = :ref AND referenceType = :type',
            ExpressionAttributeValues={
                ':ref': {'S': reference_number},
                ':type': {'S': reference_type}
            }
        )
        items = response.get('Items', [])
        if items:
            # Sort by createdAt in descending order (latest first)
            items.sort(key=lambda x: int(x.get('createdAt', {}).get('N', '0')), reverse=True)
            return [deserialize_item_json_safe(item) for item in items]
        return []
    except ClientError as e:
        print(f"Error getting invoices by reference {reference_number}: {e}")
        return []

def get_invoice_by_id(invoice_id):
    """Get an invoice by invoice ID"""
    try:
        response = dynamodb.get_item(
            TableName=INVOICES_TABLE,
            Key={'invoiceId': {'S': invoice_id}}
        )
        
        if 'Item' in response:
            return deserialize_item_json_safe(response['Item'])
        return None
    except ClientError as e:
        print(f"Error getting invoice by ID {invoice_id}: {e}")
        return None

def cancel_invoice(invoice_id):
    """Cancel an invoice by updating its status to 'cancelled' instead of deleting"""
    try:
        # Update invoice status to 'cancelled' and sync metadata paymentStatus
        dynamodb.update_item(
            TableName=INVOICES_TABLE,
            Key={'invoiceId': {'S': invoice_id}},
            UpdateExpression='SET #status = :status, cancelledAt = :cancelled_at, #metadata.#paymentStatus = :payment_status',
            ExpressionAttributeNames={
                '#status': 'status',
                '#metadata': 'metadata',
                '#paymentStatus': 'paymentStatus'
            },
            ExpressionAttributeValues={
                ':status': {'S': 'cancelled'},
                ':cancelled_at': {'N': str(int(datetime.now(ZoneInfo('Australia/Perth')).timestamp()))},
                ':payment_status': {'S': 'cancelled'}
            }
        )
        print(f"Invoice {invoice_id} status updated to cancelled successfully")
        return True
    except ClientError as e:
        print(f"Error cancelling invoice {invoice_id}: {e}")
        return False

def is_invoice_cancelled(invoice):
    """Check if an invoice is cancelled"""
    return invoice.get('status') == 'cancelled' if invoice else False

def get_invoice_status(invoice_id):
    """Get the status of an invoice"""
    invoice = get_invoice_by_id(invoice_id)
    return invoice.get('status', 'unknown') if invoice else None

def reactivate_invoice(invoice_id):
    """Reactivate a cancelled invoice by updating its status back to 'generated'"""
    try:
        # Update invoice status back to 'generated' and sync metadata paymentStatus
        dynamodb.update_item(
            TableName=INVOICES_TABLE,
            Key={'invoiceId': {'S': invoice_id}},
            UpdateExpression='SET #status = :status, #metadata.#paymentStatus = :payment_status REMOVE cancelledAt',
            ExpressionAttributeNames={
                '#status': 'status',
                '#metadata': 'metadata',
                '#paymentStatus': 'paymentStatus'
            },
            ExpressionAttributeValues={
                ':status': {'S': 'generated'},
                ':payment_status': {'S': 'completed'}
            }
        )
        print(f"Invoice {invoice_id} reactivated successfully")
        return True
    except ClientError as e:
        print(f"Error reactivating invoice {invoice_id}: {e}")
        return False


# ------------------  Backup/Restore Utility Functions ------------------

def scan_all_items(table_name):
    """Scan all items from a DynamoDB table"""
    try:
        items = []
        response = dynamodb.scan(TableName=table_name)
        items.extend(response.get('Items', []))
        
        while 'LastEvaluatedKey' in response:
            response = dynamodb.scan(
                TableName=table_name,
                ExclusiveStartKey=response['LastEvaluatedKey']
            )
            items.extend(response.get('Items', []))
        
        print(f"Scanned {len(items)} items from {table_name}")
        return items
    except ClientError as e:
        print(f"Error scanning table {table_name}: {e}")
        raise

def get_table_key_schema(table_name):
    """Get the key schema for a DynamoDB table"""
    try:
        response = dynamodb.describe_table(TableName=table_name)
        return response['Table']['KeySchema']
    except ClientError as e:
        print(f"Error getting key schema for {table_name}: {e}")
        raise

def scan_table_keys_only(table_name, key_names):
    """Scan table and return only the key attributes"""
    try:
        items = []
        projection_expression = ', '.join(key_names)
        
        response = dynamodb.scan(
            TableName=table_name,
            ProjectionExpression=projection_expression
        )
        items.extend(response.get('Items', []))
        
        while 'LastEvaluatedKey' in response:
            response = dynamodb.scan(
                TableName=table_name,
                ProjectionExpression=projection_expression,
                ExclusiveStartKey=response['LastEvaluatedKey']
            )
            items.extend(response.get('Items', []))
        
        return items
    except ClientError as e:
        print(f"Error scanning keys from {table_name}: {e}")
        raise

def delete_item(table_name, key):
    """Delete an item from DynamoDB table"""
    try:
        dynamodb.delete_item(TableName=table_name, Key=key)
        return True
    except ClientError as e:
        print(f"Error deleting item from {table_name}: {e}")
        raise

def batch_write_items(table_name, items):
    """Write items to DynamoDB table in batch"""
    try:
        request_items = {
            table_name: [
                {'PutRequest': {'Item': item}} for item in items
            ]
        }
        
        response = dynamodb.batch_write_item(RequestItems=request_items)
        
        # Handle unprocessed items
        unprocessed = response.get('UnprocessedItems', {})
        while unprocessed:
            response = dynamodb.batch_write_item(RequestItems=unprocessed)
            unprocessed = response.get('UnprocessedItems', {})
        
        return True
    except ClientError as e:
        print(f"Error batch writing items to {table_name}: {e}")
        raise

# -------------------------------------------------------------

def deserialize_item(item):
    return {k: deserializer.deserialize(v) for k, v in item.items()} if item else None

def deserialize_item_json_safe(item):
    """Deserialize DynamoDB item and convert Decimal objects to JSON-safe types"""
    if not item:
        return None
    
    deserialized = {k: deserializer.deserialize(v) for k, v in item.items()}
    
    # Convert Decimal objects to int or float for JSON serialization
    def convert_decimals(obj):
        if isinstance(obj, Decimal):
            # Convert to int if it's a whole number, otherwise float
            if obj % 1 == 0:
                return int(obj)
            else:
                return float(obj)
        elif isinstance(obj, dict):
            return {k: convert_decimals(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [convert_decimals(item) for item in obj]
        else:
            return obj
    
    return convert_decimals(deserialized)

def convert_to_dynamodb_format(obj):
    """Convert Python objects to DynamoDB format"""
    if isinstance(obj, str):
        return {'S': obj}
    elif isinstance(obj, bool):  # Check bool before int/float since bool is a subclass of int
        return {'BOOL': obj}
    elif isinstance(obj, int):
        return {'N': str(obj)}
    elif isinstance(obj, float):
        return {'N': str(obj)}
    elif isinstance(obj, dict):
        return {'M': {k: convert_to_dynamodb_format(v) for k, v in obj.items()}}
    elif isinstance(obj, list):
        return {'L': [convert_to_dynamodb_format(item) for item in obj]}
    else:
        return {'S': str(obj)}

def is_dynamodb_format(obj):
    """Check if an object is already in DynamoDB format"""
    if not isinstance(obj, dict):
        return False
    
    # Check if it has DynamoDB type descriptors
    dynamodb_types = {'S', 'N', 'B', 'SS', 'NS', 'BS', 'M', 'L', 'NULL', 'BOOL'}
    
    # If it's a single type descriptor (like {'S': 'value'})
    if len(obj) == 1 and list(obj.keys())[0] in dynamodb_types:
        return True
    
    # If it's a map, check if all values are DynamoDB format
    if 'M' in obj and isinstance(obj['M'], dict):
        return True
    
    # If it's a list, check if it has the L type
    if 'L' in obj and isinstance(obj['L'], list):
        return True
    
    return False
