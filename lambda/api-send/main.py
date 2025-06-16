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
    client_id = request_body.get('userId')
    message_id = request_body.get('messageId')
    message = request_body.get('message')
    
    if not client_id or not message_id or not message:
        return error_response("userId, messageId, and message are required.")
    
    client_user_record = get_user_record(client_id)
    if not client_user_record:
        return error_response(f"User has not intialized the connection with userId: {client_id}.")
    
    receiverConnections = []
    if 'assignedTo' in client_user_record:
        admin_id = client_user_record['assignedTo']['S']
        assigned_admin_conn = query_connection_by_user_id(admin_id)
        if assigned_admin_conn:
            receiverConnections.append(assigned_admin_conn)
        else:
            print(f"No connection found for assigned adminId: {admin_id}")
    else:
        receiverConnections = get_all_admin_connections()

    message_data = {
        'messageId': {'S': message_id},
        'message': {'S': message},
        'senderId': {'S': client_id},
        'receiverId': {'S': client_user_record['assignedTo']['S'] if 'assignedTo' in client_user_record else 'ALL'},
        'sent': {'BOOL': True},
        'received': {'BOOL': False},
        'viewed': {'BOOL': False},
        'createdAt': {'S': str(int(time.time()))},
    }

    notification_data = {
        "type": "message",
        "subtype": "send",
        "success": True,
        "messageId": message_id,
        "message": message,
        "senderId": client_id
    }

    for receiverConnection in receiverConnections:
        send_notification(receiverConnection['connectionId']['S'], notification_data)
        print(f"Message sent to receiverId: {receiverConnection['userId']['S']} with messageId: {message_id}")

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
    
def get_all_admin_connections():
    try:
        result = dynamodb.scan(
            TableName=os.environ['CONNECTIONS_TABLE'],
            FilterExpression='admin = :admin',
            ExpressionAttributeValues={':admin': {'BOOL': True}}
        )
        return result.get('Items', [])
    except ClientError as e:
        print(f"Error querying admin connections: {str(e)}")
        return []

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
