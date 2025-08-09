import boto3, os, time
from decimal import Decimal
from datetime import datetime
from botocore.exceptions import ClientError
from boto3.dynamodb.types import TypeDeserializer

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

def get_staff_record(email):
    try:
        result = dynamodb.query(
            TableName=STAFF_TABLE,
            KeyConditionExpression='userEmail = :email',
            ExpressionAttributeValues={':email': {'S': email}}
        )
        if result.get('Count', 0) > 0:
            return deserialize_item(result['Items'][0])
        return None
    except ClientError as e:
        print(f"Error querying staff record: {e.response['Error']['Message']}")
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

def build_user_record(user_id, user_record, user_email=None, user_name=None, user_device=None, user_location=None, assigned_to=None):
    user_email = user_email if user_email else user_record.get('userEmail', '') if user_record else ''
    user_name = user_name if user_name else user_record.get('userName', '') if user_record else ''
    user_device = user_device if user_device else user_record.get('userDevice', '') if user_record else ''
    user_location = user_location if user_location else user_record.get('userLocation', '') if user_record else ''
    new_user_record = {
        'userId': {'S': user_id}
    }
    optional_fields = {
        'assignedTo': assigned_to,
        'userEmail': user_email,
        'userName': user_name,
        'userDevice': user_device,
        'userLocation': user_location
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

def update_user_disconnected_time(user_id):
    try:
        dynamodb.update_item(
            TableName=USERS_TABLE,
            Key={'userId': {'S': user_id}},
            UpdateExpression='SET lastSeen = :lastSeen',
            ExpressionAttributeValues={':lastSeen': {'N': str(int(time.time()))}}
        )
        print(f"User {user_id} lastSeen updated successfully.")
        return True
    except ClientError as e:
        print(f"Error updating lastSeen for user {user_id}: {e}")
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
                'createdAt': {'N': str(int(time.time()))}
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
    else:
        print("No valid data to update.")

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
        'createdAt': {'N': str(int(time.time()))}
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

def update_unavailable_slots(date, time_slots):
    """Update unavailable slots for a specific date"""
    try:
        # Build time slots list for DynamoDB
        time_slots_list = []
        for slot in time_slots:
            time_slots_list.append({
                'M': {
                    'startTime': {'S': slot['startTime']},
                    'endTime': {'S': slot['endTime']}
                }
            })
        
        dynamodb.put_item(
            TableName=UNAVAILABLE_SLOTS_TABLE,
            Item={
                'date': {'S': date},
                'timeSlots': {'L': time_slots_list},
                'updatedAt': {'N': str(int(time.time()))}
            }
        )
        print(f"Unavailable slots updated for date {date}")
        return True
    except ClientError as e:
        print(f"Error updating unavailable slots for date {date}: {e}")
        return False


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

def build_update_expression_for_appointment(data):
    """Build update expression for appointment updates"""
    update_parts = []
    remove_parts = []
    expression_values = {}
    expression_names = {}
    
    # DynamoDB reserved keywords that need expression attribute names
    reserved_keywords = {
        'status', 'name', 'type', 'value', 'size', 'order', 'date', 
        'time', 'user', 'group', 'role', 'data', 'count', 'index'
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
    current_time = int(time.time())
    current_date = datetime.now().strftime('%Y-%m-%d')
    
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
        'time', 'user', 'group', 'role', 'data', 'count', 'index'
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
    current_time = int(time.time())
    current_date = datetime.now().strftime('%Y-%m-%d')
    
    # Convert items list to DynamoDB format
    items_list = []
    for item in items:
        item_data = {
            'M': {
                'categoryId': {'N': str(item['categoryId'])},
                'itemId': {'N': str(item['itemId'])},
                'quantity': {'N': str(item['quantity'])},
                'price': {'N': str(item['price'])},
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
    current_time = int(time.time())
    current_date = datetime.now().strftime('%Y-%m-%d')
    
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

def create_invoice_record(invoice_data):
    """Create a new invoice record in the database"""
    try:
        # Prepare item data with required fields
        item = {
            'invoiceId': {'S': invoice_data['invoiceId']},
            's3Key': {'S': invoice_data['s3Key']},
            'fileUrl': {'S': invoice_data['fileUrl']},
            'fileSize': {'N': str(invoice_data['fileSize'])},
            'format': {'S': invoice_data.get('format', 'html')},
            'createdAt': {'N': str(invoice_data['createdAt'])},
            'status': {'S': invoice_data.get('status', 'generated')}
        }
        
        # Add optional fields if present
        if 'paymentIntentId' in invoice_data and invoice_data['paymentIntentId']:
            item['paymentIntentId'] = {'S': invoice_data['paymentIntentId']}
        
        if 'userId' in invoice_data and invoice_data['userId']:
            item['userId'] = {'S': invoice_data['userId']}
            
        if 'referenceNumber' in invoice_data and invoice_data['referenceNumber']:
            item['referenceNumber'] = {'S': invoice_data['referenceNumber']}
            
        if 'referenceType' in invoice_data and invoice_data['referenceType']:
            item['referenceType'] = {'S': invoice_data['referenceType']}
        
        if 'metadata' in invoice_data:
            if isinstance(invoice_data['metadata'], dict):
                # Convert dict to DynamoDB Map format if needed
                if invoice_data['metadata']:  # Only add if not empty
                    item['metadata'] = convert_to_dynamodb_format(invoice_data['metadata'])
            else:
                item['metadata'] = {'M': {}}
        
        dynamodb.put_item(
            TableName=INVOICES_TABLE,
            Item=item
        )
        print(f"Invoice {invoice_data['invoiceId']} created successfully")
        return True
    except ClientError as e:
        print(f"Error creating invoice: {e}")
        return False

def get_invoice_by_id(invoice_id):
    """Get an invoice record by invoice ID"""
    try:
        result = dynamodb.get_item(
            TableName=INVOICES_TABLE,
            Key={'invoiceId': {'S': invoice_id}}
        )
        if 'Item' in result:
            return deserialize_item_json_safe(result['Item'])
        return None
    except ClientError as e:
        print(f"Error getting invoice by ID {invoice_id}: {e}")
        return None

def get_invoice_by_payment_intent(payment_intent_id):
    """Get an invoice record by payment intent ID"""
    try:
        result = dynamodb.query(
            TableName=INVOICES_TABLE,
            IndexName='paymentIntentId-index',
            KeyConditionExpression='paymentIntentId = :pid',
            ExpressionAttributeValues={':pid': {'S': payment_intent_id}}
        )
        if result.get('Count', 0) > 0:
            return deserialize_item_json_safe(result['Items'][0])
        return None
    except ClientError as e:
        print(f"Error getting invoice by payment intent ID {payment_intent_id}: {e}")
        return None

def get_invoice_by_reference_number(reference_number):
    """Get an invoice record by reference number"""
    try:
        # Try using GSI first (more efficient)
        try:
            result = dynamodb.query(
                TableName=INVOICES_TABLE,
                IndexName='referenceNumber-index',
                KeyConditionExpression='referenceNumber = :ref',
                ExpressionAttributeValues={':ref': {'S': reference_number}},
                Limit=1
            )
            if result.get('Count', 0) > 0:
                return deserialize_item_json_safe(result['Items'][0])
        except ClientError as gsi_error:
            # Fallback to scan if GSI doesn't exist yet
            print(f"GSI not available, falling back to scan: {gsi_error}")
            result = dynamodb.scan(
                TableName=INVOICES_TABLE,
                FilterExpression='referenceNumber = :ref',
                ExpressionAttributeValues={':ref': {'S': reference_number}},
                Limit=1
            )
            if result.get('Count', 0) > 0:
                return deserialize_item_json_safe(result['Items'][0])
        
        return None
    except ClientError as e:
        print(f"Error getting invoice by reference number {reference_number}: {e}")
        return None

def get_invoices_by_user(user_id, limit=50):
    """Get all invoices for a specific user"""
    try:
        result = dynamodb.query(
            TableName=INVOICES_TABLE,
            IndexName='userId-index',
            KeyConditionExpression='userId = :uid',
            ExpressionAttributeValues={':uid': {'S': user_id}},
            ScanIndexForward=False,  # Order by createdAt descending
            Limit=limit
        )
        return [deserialize_item_json_safe(item) for item in result.get('Items', [])]
    except ClientError as e:
        print(f"Error getting invoices by user {user_id}: {e}")
        return []

def update_invoice_status(invoice_id, status, additional_data=None):
    """Update invoice status and optionally add additional data"""
    try:
        update_expression = "SET #status = :status, updatedAt = :updated_at"
        expression_values = {
            ':status': {'S': status},
            ':updated_at': {'N': str(int(time.time()))}
        }
        expression_names = {
            '#status': 'status'
        }
        
        # Add additional data if provided
        if additional_data:
            for key, value in additional_data.items():
                if value is not None:
                    attr_name = f"#{key}"
                    attr_value = f":{key}"
                    update_expression += f", {attr_name} = {attr_value}"
                    expression_names[attr_name] = key
                    
                    # Handle different data types
                    if isinstance(value, str):
                        expression_values[attr_value] = {'S': value}
                    elif isinstance(value, (int, float, Decimal)):
                        expression_values[attr_value] = {'N': str(value)}
                    elif isinstance(value, bool):
                        expression_values[attr_value] = {'BOOL': value}
                    else:
                        expression_values[attr_value] = {'S': str(value)}
        
        dynamodb.update_item(
            TableName=INVOICES_TABLE,
            Key={'invoiceId': {'S': invoice_id}},
            UpdateExpression=update_expression,
            ExpressionAttributeValues=expression_values,
            ExpressionAttributeNames=expression_names
        )
        print(f"Invoice {invoice_id} status updated to {status}")
        return True
    except ClientError as e:
        print(f"Error updating invoice status {invoice_id}: {e}")
        return False

def list_invoices_by_date_range(start_date, end_date, limit=100):
    """List invoices within a date range (timestamps)"""
    try:
        result = dynamodb.scan(
            TableName=INVOICES_TABLE,
            FilterExpression='createdAt BETWEEN :start_date AND :end_date',
            ExpressionAttributeValues={
                ':start_date': {'N': str(start_date)},
                ':end_date': {'N': str(end_date)}
            },
            Limit=limit
        )
        return [deserialize_item_json_safe(item) for item in result.get('Items', [])]
    except ClientError as e:
        print(f"Error listing invoices by date range: {e}")
        return []

def delete_invoice_record(invoice_id):
    """Delete an invoice record (use with caution)"""
    try:
        dynamodb.delete_item(
            TableName=INVOICES_TABLE,
            Key={'invoiceId': {'S': invoice_id}}
        )
        print(f"Invoice {invoice_id} deleted successfully")
        return True
    except ClientError as e:
        print(f"Error deleting invoice {invoice_id}: {e}")
        return False
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
    elif isinstance(obj, int):
        return {'N': str(obj)}
    elif obj is True or obj is False:
        return {'BOOL': obj}
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
