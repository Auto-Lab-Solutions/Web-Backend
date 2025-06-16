import json
import boto3
import os
from botocore.exceptions import ClientError

dynamodb = boto3.client('dynamodb')

def lambda_handler(event, context):
    connection_id = event.get('connectionId')
    domain = event.get('domain')
    stage = event.get('stage')
    request_body = event.get('body', {})
    user_email = request_body.get('userEmail', '')

    if not user_email:
        print("userEmail is required.")
        return {}
    
    admin_record = get_admin_by_email(user_email)
    if not admin_record:
        print(f"No admin found for userEmail: {user_email}")
        return {}
    
    admin_user_id = admin_record['userId']['S']
    delete_old_connections(admin_user_id)

    if not get_connection_by_id(connection_id):
        print(f"Connection not found for connectionId: {connection_id}")
        return {}

    user_data = {
        'userId': admin_user_id,
        'admin': 'true'
    }

    update_expression, expression_values = build_update_expression(user_data)
    if update_expression:
        dynamodb.update_item(
            TableName=os.environ["CONNECTIONS_TABLE"],
            Key={"connectionId": {"S": connection_id}},
            UpdateExpression=update_expression,
            ExpressionAttributeValues=expression_values
        )
        print(f"Connection updated for connectionId: {connection_id} with userId: {admin_user_id}")
    else:
        print("No user data provided to update.")

    apigateway = boto3.client(
        'apigatewaymanagementapi', 
        endpoint_url = "https://" + domain + "/" + stage
    )

    try:
        apigateway.post_to_connection(
            Data=json.dumps({"type": "connection", "subtype": "init", "success": True, "userId": admin_user_id}),
            ConnectionId=connection_id
        )
    except ClientError as e:
        print(f"Error sending connection init to {connection_id}: {e}")
        return {}

    print(f"Connection established for connectionId: {connection_id} with userId: {admin_user_id}")
    return {}


def get_admin_by_email(email):
    try:
        result = dynamodb.query(
            TableName=os.environ['ADMINS_TABLE'],
            KeyConditionExpression='userEmail = :userEmail',
            ExpressionAttributeValues={':userEmail': {'S': email}}
        )
        return result['Items'][0] if result.get('Count', 0) > 0 else None
    except ClientError as e:
        print(f"Error querying admin by email {email}: {e}")
        return None

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

def build_update_expression(data):
    update_parts = []
    expression_values = {}
    for key, value in data.items():
        if value:
            update_parts.append(f"{key} = :{key}")
            if key == 'admin':
                expression_values[f":{key}"] = {"BOOL": value == 'true'}
            else:
                expression_values[f":{key}"] = {"S": value}
    if update_parts:
        return "SET " + ", ".join(update_parts), expression_values
    return None, None

