import boto3, os, time
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

def get_all_staff_records():
    try:
        result = dynamodb.scan(TableName=STAFF_TABLE)
        return [deserialize_item(item) for item in result.get('Items', [])]
    except ClientError as e:
        print(f"Error scanning staff records: {e.response['Error']['Message']}")
        return []

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
            FilterExpression='attribute_exists(userId)',
            ExpressionAttributeValues={':userId': {'S': ''}}  # This is just a placeholder to ensure the filter works
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

# ------------------  Utility Functions ------------------

def deserialize_item(item):
    return {k: deserializer.deserialize(v) for k, v in item.items()} if item else None

# -------------------------------------------------------------
