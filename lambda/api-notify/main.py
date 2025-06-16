import json
import boto3
import os
from botocore.exceptions import ClientError

valid_statuses = [
    'TYPING',
    'MESSAGE_RECEIVED',
    'MESSAGE_VIEWED',
    'MESSAGE_DELETED',
    'MESSAGE_EDITED'
]

dynamodb = boto3.client('dynamodb')
apigatewaymanagementapi = boto3.client(
    'apigatewaymanagementapi',
    endpoint_url=os.environ['WEBSOCKET_ENDPOINT_URL']
)

def lambda_handler(event, context):
    request_body = json.loads(event.get('body'))
    user_id = request_body.get('userId')
    client_id = request_body.get('clientId')
    status = request_body.get('status')
    message_id = request_body.get('messageId')
    new_message = request_body.get('newMessage')

    if not status or not user_id:
        return error_response("status and userId are required.")

    if status not in valid_statuses:
        return error_response(f"Invalid status: {status}")

    action_sender_conn = query_connection_by_user_id(user_id)
    if not action_sender_conn:
        return error_response(f"No connection found for userId: {user_id}")
    action_sender_record = get_user_record(user_id)

    receiver_ids = []
    if status == 'TYPING':
        if not action_sender_conn['admin']['BOOL']:
            if 'assignedTo' in action_sender_record:
                receiver_ids.append(action_sender_record['assignedTo']['S'])
            else:
                receiver_ids = [conn['userId']['S'] for conn in get_all_admin_connections()]
        else:
            if not client_id:
                return error_response("clientId is required for TYPING status sending by admin.")
            receiver_ids.append(client_id)

        notification = {
            "type": "notification",
            "subtype": "status",
            "success": True,
            "status": status,
            "senderId": user_id
        }

        for receiver_id in receiver_ids:
            msg_receiver_conn_id = query_connection_id_by_user_id(receiver_id)
            if not msg_receiver_conn_id:
                print(f"No connection found for receiverId: {receiver_id}. Skipping notification.")
                continue
            send_notification(msg_receiver_conn_id, notification)

        return success_response("Notification sent successfully.")

    if not message_id:
        return error_response("messageId is required for this status.")

    message_item = get_message_by_id(message_id)
    if not message_item:
        return error_response(f"message not found for messageId: {message_id}")

    notification = {
        "type": "notification",
        "subtype": "status",
        "success": True,
        "messageId": message_id,
        "status": status
    }

    msg_receiver_id = message_item.get('receiverId', {}).get('S')
    msg_sender_id = message_item.get('senderId', {}).get('S')

    if status in ['MESSAGE_RECEIVED', 'MESSAGE_VIEWED']:
        if msg_receiver_id == 'ALL':
            return success_response("Cannot send notifications for admin unassigned messages. Skipping.", False)
        if msg_receiver_id != user_id:
            return error_response("You are not authorized to send RECEIVED/READ notifications for this message.")
        
        msg_sender_conn_id = query_connection_id_by_user_id(msg_sender_id)
        skip = not msg_sender_conn_id

        if not skip:
            send_notification(msg_sender_conn_id, notification)

        try:
            update_expr = {
                'MESSAGE_RECEIVED': ('SET received = :val', {':val': {'BOOL': True}}),
                'MESSAGE_VIEWED': ('SET viewed = :val', {':val': {'BOOL': True}})
            }
            expr, values = update_expr[status]
            dynamodb.update_item(
                TableName=os.environ['MESSAGES_TABLE'],
                Key={'messageId': {'S': message_id}},
                UpdateExpression=expr,
                ExpressionAttributeValues=values
            )
            print(f"Message {message_id} marked as {status}.")
        except ClientError as e:
            print(f"Error updating message {message_id}: {str(e)}")

        return success_response(
            f"No connection found for senderId: {msg_sender_id}. Skipping notification." if skip
            else f"Notification sent successfully for {status}.",
            not skip
        )

    elif status in ['MESSAGE_DELETED', 'MESSAGE_EDITED']:
        msg_receiver_conn_ids = []
        skip = False

        if msg_sender_id != user_id:
            return error_response("You are not authorized to send DELETED/EDITED notifications for this message.")
        
        if msg_receiver_id == 'ALL':
            msg_receiver_conn_ids = [conn['connectionId']['S'] for conn in get_all_admin_connections()]
        else:
            msg_receiver_conn_id = query_connection_id_by_user_id(msg_receiver_id)
            if msg_receiver_conn_id:
                msg_receiver_conn_ids.append(msg_receiver_conn_id)
            skip = not msg_receiver_conn_id

        if status == 'MESSAGE_EDITED':
            if not new_message:
                return error_response("newMessage is required for MESSAGE_EDITED status.")
            notification['newMessage'] = new_message
            try:
                dynamodb.update_item(
                    TableName=os.environ['MESSAGES_TABLE'],
                    Key={'messageId': {'S': message_id}},
                    UpdateExpression='SET message = :newMessage',
                    ExpressionAttributeValues={':newMessage': {'S': new_message}}
                )
                print(f"Message {message_id} edited for senderId: {msg_sender_id}")
            except ClientError as e:
                print(f"Error editing message {message_id}: {str(e)}")
        
        elif status == 'MESSAGE_DELETED':
            try:
                dynamodb.delete_item(
                    TableName=os.environ['MESSAGES_TABLE'],
                    Key={'messageId': {'S': message_id}}
                )
                print(f"Message {message_id} deleted for senderId: {msg_sender_id}")
            except ClientError as e:
                print(f"Error deleting message {message_id}: {str(e)}")
        
        if not skip:
            for msg_receiver_conn_id in msg_receiver_conn_ids:
                send_notification(msg_receiver_conn_id, notification)

        return success_response(
            f"No connection found for receiverId: {msg_receiver_id}. Skipping notification." if skip
            else f"Notification sent successfully for {status}.",
            not skip
        )

    return error_response(f"Unsupported status: {status}")


def query_connection_by_user_id(user_id):
    try:
        params = {
            'TableName': os.environ['CONNECTIONS_TABLE'],
            'IndexName': 'userId-index',
            'KeyConditionExpression': 'userId = :uid',
            'ExpressionAttributeValues': {':uid': {'S': user_id}}
        }
        result = dynamodb.query(**params)
        return result['Items'][0] if result['Count'] > 0 else None
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
    
def query_connection_id_by_user_id(user_id):
    conn_record = query_connection_by_user_id(user_id)
    return conn_record['connectionId']['S'] if conn_record else None
    
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

def send_notification(connection_id, notification):
    try:
        apigatewaymanagementapi.post_to_connection(
            Data=json.dumps(notification),
            ConnectionId=connection_id
        )
        print(f"Notification sent to connectionId: {connection_id}")
        return True
    except ClientError as e:
        print(f"Error sending notification to {connection_id}: {str(e)}")
        return False

def get_message_by_id(message_id):
    try:
        result = dynamodb.query(
            TableName=os.environ['MESSAGES_TABLE'],
            KeyConditionExpression='messageId = :messageId',
            ExpressionAttributeValues={':messageId': {'S': message_id}}
        )
        return result['Items'][0] if result['Count'] > 0 else None
    except ClientError as e:
        print(f"Error retrieving message {message_id}: {str(e)}")
        return None

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
