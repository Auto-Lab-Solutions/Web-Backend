import json
import boto3
import os
import uuid
from botocore.exceptions import ClientError

dynamodb = boto3.client('dynamodb')

def lambda_handler(event, context):
    connection_id = event.get('connectionId')
    domain = event.get('domain')
    stage = event.get('stage')
    request_body = event.get('body', {})
    
    user_id = request_body.get('userId', '')
    user_email = request_body.get('userEmail', '')
    user_name = request_body.get('userName', '')
    user_device = request_body.get('userDevice', '')
    user_location = request_body.get('userLocation', '')

    assigned_to = ''
    user_record = None

    apigateway = boto3.client(
        'apigatewaymanagementapi', 
        endpoint_url = "https://" + domain + "/" + stage
    )

    if user_id:
        delete_old_connections(user_id)
        user_record = get_user_record(user_id)
        if user_record:
            if 'assignedTo' in user_record:
                assigned_to = user_record['assignedTo']['S']
        else:
            print(f"No user record found for userId: {user_id}")
            try:
                apigateway.post_to_connection(
                    Data=json.dumps({ "type": "connection", "subtype": "init", "success": False, "cause": "INVALID_USER_ID" }),
                    ConnectionId=connection_id
                )
            except ClientError as e:
                print(f"Error sending connection init failure to {connection_id}: {e}")
            return {}

    existing_connection = get_connection_by_id(connection_id)
    if not existing_connection:
        print(f"Connection not found for connectionId: {connection_id}")
        return {}

    user_id = user_id or str(uuid.uuid4())
    
    connection_data = {
        'userId': user_id,
        'admin': 'false'
    }
    update_expr, expr_values = build_update_expression(connection_data)
    if update_expr:
        dynamodb.update_item(
            TableName=os.environ["CONNECTIONS_TABLE"],
            Key={"connectionId": {"S": connection_id}},
            UpdateExpression=update_expr,
            ExpressionAttributeValues=expr_values
        )
        print(f"Connection updated for connectionId: {connection_id} with userId: {user_id}")
    else:
        print("No connection data provided to update.")
    
    user_email = user_email if user_email else user_record['userEmail']['S'] if user_record and 'userEmail' in user_record else ''
    user_name = user_name if user_name else user_record['userName']['S'] if user_record and 'userName' in user_record else ''
    user_device = user_device if user_device else user_record['userDevice']['S'] if user_record and 'userDevice' in user_record else ''
    user_location = user_location if user_location else user_record['userLocation']['S'] if user_record and 'userLocation' in user_record else ''
    new_user_record = {
        'userId': {'S': user_id},
        'admin': {'BOOL': False}
    }
    if assigned_to: new_user_record['assignedTo'] = {'S': assigned_to}
    if user_email: new_user_record['userEmail'] = {'S': user_email}
    if user_name: new_user_record['userName'] = {'S': user_name}
    if user_device: new_user_record['userDevice'] = {'S': user_device}
    if user_location: new_user_record['userLocation'] = {'S': user_location}
    try:
        dynamodb.put_item(
            TableName=os.environ['USERS_TABLE'],
            Item=new_user_record
        )
        print(f"User record created for userId: {user_id}")
    except ClientError as e:
        print(f"Error creating user record for userId {user_id}: {e}")
        return {}


    message_body = {
        "type": "notification",
        "subtype": "user-connected",
        "userId": user_id,
        "assignedTo": assigned_to,
        "userEmail": user_email,
        "userName": user_name,
        "userDevice": user_device,
        "userLocation": user_location
    }
    receivers = [query_connection_by_user_id(assigned_to)] if assigned_to else get_all_admin_connections()
    if receivers:
        for admin_conn in receivers:
            admin_conn_id = admin_conn['connectionId']['S']
            try:
                apigateway.post_to_connection(
                    Data=json.dumps(message_body),
                    ConnectionId=admin_conn_id
                )
            except ClientError as e:
                print(f"Error sending notification to {admin_conn_id}: {e}")
            print(f"Notification sent to admin connectionId: {admin_conn_id} for userId: {user_id}")
    
    try:
        apigateway.post_to_connection(
            Data=json.dumps({ "type": "connection", "subtype": "init", "success": True, "userId": user_id }),
            ConnectionId=connection_id
        )
    except ClientError as e:
        print(f"Error sending connection init to {connection_id}: {e}")
        return {}

    print(f"Connection established for connectionId: {connection_id} with userId: {user_id}")
    return {}



def delete_old_connections(user_id):
    try:
        result = dynamodb.query(
            TableName=os.environ['CONNECTIONS_TABLE'],
            IndexName='userId-index',
            KeyConditionExpression='userId = :uid',
            ExpressionAttributeValues={':uid': {'S': user_id}}
        )
        for item in result.get('Items', []):
            conn_id = item['connectionId']['S']
            dynamodb.delete_item(
                TableName=os.environ['CONNECTIONS_TABLE'],
                Key={'connectionId': {'S': conn_id}}
            )
            print(f"Deleted old connection: {conn_id} for userId: {user_id}")
    except ClientError as e:
        print(f"Error deleting old connections: {e}")

def get_connection_by_id(connection_id):
    try:
        result = dynamodb.query(
            TableName=os.environ['CONNECTIONS_TABLE'],
            KeyConditionExpression='connectionId = :connectionId',
            ExpressionAttributeValues={':connectionId': {'S': connection_id}}
        )
        return result['Items'][0] if result.get('Count', 0) > 0 else None
    except ClientError as e:
        print(f"Error querying connectionId {connection_id}: {e}")
        return None
    
def get_user_record(userId):
    try:
        result = dynamodb.query(
            TableName=os.environ['USERS_TABLE'],
            KeyConditionExpression='userId = :userId',
            ExpressionAttributeValues={':userId': {'S': userId}}
        )
        return result['Items'][0] if result.get('Count', 0) > 0 else None
    except ClientError as e:
        print(f"Error querying user record for userId {userId}: {e}")
        return None

def query_connection_by_user_id(user_id):
    try:
        result = dynamodb.query(
            TableName=os.environ['CONNECTIONS_TABLE'],
            IndexName='userId-index',
            KeyConditionExpression='userId = :uid',
            ExpressionAttributeValues={':uid': {'S': user_id}}
        )
        return result['Items'][0] if result.get('Count', 0) > 0 else None
    except ClientError as e:
        print(f"Error querying userId {user_id}: {e}")
        return None

def get_all_admin_connections():
    try:
        result = dynamodb.scan(
            TableName=os.environ['CONNECTIONS_TABLE'],
            FilterExpression='admin = :admin',
            ExpressionAttributeValues={':admin': {'BOOL': True}}
        )
        return result.get('Items', [])
    except ClientError as e:
        print(f"Error scanning for admin connections: {e}")
        return []

def build_update_expression(user_data):
    update_parts = []
    expr_values = {}
    for key, value in user_data.items():
        if value:
            update_parts.append(f"{key} = :{key}")
            expr_values[f":{key}"] = {"BOOL": value == 'true'} if key == 'admin' else {"S": value}
    return ("SET " + ", ".join(update_parts), expr_values) if update_parts else (None, None)

