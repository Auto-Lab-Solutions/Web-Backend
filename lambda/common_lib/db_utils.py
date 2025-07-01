import boto3, os, time
from botocore.exceptions import ClientError
from boto3.dynamodb.types import TypeDeserializer

# Dynamodb client and deserializer
dynamodb = boto3.client('dynamodb')
deserializer = TypeDeserializer()

# Environment variables
USERS_TABLE = os.environ.get('USERS_TABLE')
STAFF_TABLE = os.environ.get('STAFF_TABLE')
CONNECTIONS_TABLE = os.environ.get('CONNECTIONS_TABLE')

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

# ------------------  Utility Functions ------------------

def deserialize_item(item):
    return {k: deserializer.deserialize(v) for k, v in item.items()} if item else None

# -------------------------------------------------------------