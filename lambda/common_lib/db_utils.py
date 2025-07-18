import boto3, os, time
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
            return deserialize_item(result['Item'])
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
            return deserialize_item(result['Item'])
        return None
    except ClientError as e:
        print(f"Error getting appointment {appointment_id}: {e}")
        return None

def update_appointment(appointment_id, update_data):
    """Update an existing appointment"""
    try:
        update_expression, expression_values = build_update_expression_for_appointment(update_data)
        if update_expression:
            dynamodb.update_item(
                TableName=APPOINTMENTS_TABLE,
                Key={'appointmentId': {'S': appointment_id}},
                UpdateExpression=update_expression,
                ExpressionAttributeValues=expression_values
            )
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
        return [deserialize_item(item) for item in result.get('Items', [])]
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
        return [deserialize_item(item) for item in result.get('Items', [])]
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
        return [deserialize_item(item) for item in result.get('Items', [])]
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
        return [deserialize_item(item) for item in result.get('Items', [])]
    except ClientError as e:
        print(f"Error getting appointments for scheduled date {scheduled_date}: {e}")
        return []

def build_update_expression_for_appointment(data):
    """Build update expression for appointment updates"""
    update_parts = []
    expression_values = {}
    
    for key, value in data.items():
        if value is not None:
            update_parts.append(f'{key} = :{key}')
            # Handle different data types for DynamoDB
            if isinstance(value, str):
                expression_values[f':{key}'] = {'S': value}
            elif isinstance(value, int):
                expression_values[f':{key}'] = {'N': str(value)}
            elif isinstance(value, bool):
                expression_values[f':{key}'] = {'BOOL': value}
            elif isinstance(value, dict):
                expression_values[f':{key}'] = {'M': convert_to_dynamodb_format(value)}
            elif isinstance(value, list):
                expression_values[f':{key}'] = {'L': [convert_to_dynamodb_format(item) for item in value]}
    
    if update_parts:
        update_expression = 'SET ' + ', '.join(update_parts)
        return update_expression, expression_values
    return None, None

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
        'paymentCompleted': {'BOOL': False},
        'assignedMechanicId': {'S': ''},
        'scheduledTimeSlot': {'M': {}},
        'scheduledDate': {'S': ''},
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
            FilterExpression='createdDate = :date AND paymentCompleted = :paid',
            ExpressionAttributeValues={
                ':uid': {'S': user_id},
                ':date': {'S': today_str},
                ':paid': {'BOOL': False}
            }
        )
        return result.get('Count', 0)
    except ClientError as e:
        print(f"Error getting daily unpaid appointments count for user {user_id}: {e}")
        return 0


# ------------------  Service Pricing Table Functions ------------------

def get_service_pricing(service_id, plan_id):
    """Get service pricing by service_id and plan_id"""
    try:
        result = dynamodb.get_item(
            TableName=SERVICE_PRICES_TABLE,
            Key={
                'serviceId': {'N': str(service_id)},
                'planId': {'N': str(plan_id)}
            }
        )
        if 'Item' in result:
            return deserialize_item(result['Item'])
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
        update_expression, expression_values = build_update_expression_for_order(update_data)
        if update_expression:
            dynamodb.update_item(
                TableName=ORDERS_TABLE,
                Key={'orderId': {'S': order_id}},
                UpdateExpression=update_expression,
                ExpressionAttributeValues=expression_values
            )
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
            FilterExpression='createdDate = :date AND paymentCompleted = :paid',
            ExpressionAttributeValues={
                ':uid': {'S': user_id},
                ':date': {'S': today_str},
                ':paid': {'BOOL': False}
            }
        )
        return result.get('Count', 0)
    except ClientError as e:
        print(f"Error getting daily unpaid orders count for user {user_id}: {e}")
        return 0

def build_update_expression_for_order(data):
    """Build update expression for order updates"""
    update_parts = []
    expression_values = {}
    
    for key, value in data.items():
        if value is not None:
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
                expression_values[f':{key}'] = {'M': convert_to_dynamodb_format(value)}
            elif isinstance(value, list):
                expression_values[f':{key}'] = {'L': [convert_to_dynamodb_format(item) for item in value]}
    
    if update_parts:
        update_expression = 'SET ' + ', '.join(update_parts)
        return update_expression, expression_values
    return None, None

def build_order_data(order_id, category_id, item_id, quantity, customer_data, car_data, notes, created_user_id, price):
    """Build order data in DynamoDB format"""
    current_time = int(time.time())
    current_date = datetime.now().strftime('%Y-%m-%d')
    
    order_data = {
        'orderId': {'S': order_id},
        'categoryId': {'N': str(category_id)},
        'itemId': {'N': str(item_id)},
        'quantity': {'N': str(quantity)},
        'customerName': {'S': customer_data.get('name', '')},
        'customerEmail': {'S': customer_data.get('email', '')},
        'customerPhone': {'S': customer_data.get('phoneNumber', '')},
        'customerAddress': {'S': customer_data.get('address', '')},
        'carMake': {'S': car_data.get('make', '')},
        'carModel': {'S': car_data.get('model', '')},
        'carYear': {'S': str(car_data.get('year', ''))},
        'carLocation': {'S': car_data.get('location', '')},
        'notes': {'S': notes},
        'createdUserId': {'S': created_user_id},
        'status': {'S': 'PENDING'},
        'price': {'N': str(price)},
        'totalPrice': {'N': str(price * quantity)},
        'paymentCompleted': {'BOOL': False},
        'assignedMechanicId': {'S': ''},
        'scheduledDate': {'S': ''},
        'postNotes': {'S': ''},
        'createdAt': {'N': str(current_time)},
        'createdDate': {'S': current_date},
        'updatedAt': {'N': str(current_time)}
    }
    
    return order_data


# ------------------  Item Prices Table Functions ------------------

def get_item_pricing(category_id, item_id):
    """Get item pricing by category_id and item_id"""
    try:
        result = dynamodb.get_item(
            TableName=ITEM_PRICES_TABLE,
            Key={
                'categoryId': {'N': str(category_id)},
                'itemId': {'N': str(item_id)}
            }
        )
        if 'Item' in result:
            return deserialize_item(result['Item'])
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

# ------------------  Utility Functions ------------------

def deserialize_item(item):
    return {k: deserializer.deserialize(v) for k, v in item.items()} if item else None

def convert_to_dynamodb_format(obj):
    """Convert Python objects to DynamoDB format"""
    if isinstance(obj, str):
        return {'S': obj}
    elif isinstance(obj, int):
        return {'N': str(obj)}
    elif isinstance(obj, bool):
        return {'BOOL': obj}
    elif isinstance(obj, dict):
        return {'M': {k: convert_to_dynamodb_format(v) for k, v in obj.items()}}
    elif isinstance(obj, list):
        return {'L': [convert_to_dynamodb_format(item) for item in obj]}
    else:
        return {'S': str(obj)}

# -------------------------------------------------------------
