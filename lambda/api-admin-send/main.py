import json
import boto3
import os
import time
from botocore.exceptions import ClientError

dynamodb = boto3.client('dynamodb')

apigateway = boto3.client(
    'apigatewaymanagementapi',
    endpoint_url=os.environ['WEBSOCKET_ENDPOINT_URL']
)

def lambda_handler(event, context):
    request_body = json.loads(event.get('body'))
    admin_id = request_body.get('senderId')
    client_id = request_body.get('receiverId')
    message_id = request_body.get('messageId')
    message = request_body.get('message')

    if not admin_id or not client_id or not message_id or not message:
        return error_response("senderId, receiverId, messageId, and message are required.")

    admin_record = get_admin_record_by_id(admin_id)
    if not admin_record:
        return error_response(f"No admin found for adminId: {admin_id}.")
    
    client_user_record = get_user_record(client_id)
    if not client_user_record:
        return error_response(f"User has not initialized the connection with userId: {client_id}.")
    elif 'assignedTo' not in client_user_record:
        return error_response(f"User with receiverId: {client_id} is not assigned to any admin.")
    elif client_user_record['assignedTo']['S'] != admin_id:
        return error_response(f"User with receiverId: {client_id} is assigned to a different admin: {client_user_record['assignedTo']['S']}.")
    
    notification_data = {
        "type": "message",
        "subtype": "send",
        "success": True,
        "messageId": message_id,
        "message": message,
        "senderId": admin_id
    }
    client_conn = query_connection_by_user_id(client_id)
    if client_conn:
        send_notification(client_conn['connectionId']['S'], notification_data)
        print(f"Message sent to receiverId: {client_id} with messageId: {message_id}")

    message_data = {
        'messageId': {'S': message_id},
        'message': {'S': message},
        'senderId': {'S': admin_id},
        'receiverId': {'S': client_id},
        'sent': {'BOOL': True},
        'received': {'BOOL': False},
        'viewed': {'BOOL': False},
        'createdAt': {'S': str(int(time.time()))}
    }
    dynamodb.put_item(
        TableName=os.environ['MESSAGES_TABLE'],
        Item=message_data
    )
    print(f"Message stored with ID: {message_id}")
    return success_response(f"Message sent to receiverId: {client_id} with messageId: {message_id}.")


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
        print(f"Error querying connection for userId {user_id}: {str(e)}")
        return None
    
def get_admin_record_by_id(user_id):
    try:
        response = dynamodb.query(
            TableName=os.environ['ADMINS_TABLE'],
            IndexName='userId-index',
            KeyConditionExpression=f'userId = :uid',
            ExpressionAttributeValues={':uid': {'S': user_id}}
        )
        return response['Items'][0] if response.get('Count', 0) > 0 else None
    except ClientError as e:
        print(f"Error querying admin by userId {user_id}: {str(e)}")
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
    
def send_notification(connection_id, data):
    try:
        apigateway.post_to_connection(
            Data=json.dumps(data),
            ConnectionId=connection_id
        )
    except ClientError as e:
        print(f"Error sending notification to {connection_id}: {str(e)}")
    
def error_response(message):
    print(message)
    return {
        "statusCode": 400,
        "headers": { 
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*"
        },
        "headers": { "Content-Type": "application/json" },
        "body": json.dumps({
            "success": False,
            "message": message
        })
    }

def success_response(message, success=True):
    print(message)
    return {
        "statusCode": 200,
        "headers": { 
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*"
        },
        "body": json.dumps({
            "success": success,
            "message": message
        })
    }
