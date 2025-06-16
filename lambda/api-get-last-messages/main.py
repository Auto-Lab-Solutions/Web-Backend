import json
import boto3
import os
from botocore.exceptions import ClientError
from boto3.dynamodb.types import TypeDeserializer

dynamodb = boto3.client('dynamodb')
deserializer = TypeDeserializer()

def lambda_handler(event, context):
    query_params = event.get('queryStringParameters') or {}
    user_id = query_params.get('userId')

    if not user_id:
        return error_response("userId is required.")
    
    admin_record = get_admin_record_by_id(user_id)
    if not admin_record:
        return error_response("Cannot retrieve latest messages for a non-admin user.")
    
    latest_messages = sorted(get_latest_messages_by_user(user_id), key=lambda x: int(x['createdAt']), reverse=True)
    return success_response({"messages": latest_messages})


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

def get_latest_messages_by_user(user_id):
    all_messages = []
    try:
        sender_messages = query_messages_by_user(user_id, index_name='senderId-index', key_name='senderId')
        receiver_messages = query_messages_by_user(user_id, index_name='receiverId-index', key_name='receiverId')
        admin_unassigned_messages = query_messages_by_user('ALL', index_name='receiverId-index', key_name='receiverId')
        all_messages = sender_messages + receiver_messages + admin_unassigned_messages
    except ClientError as e:
        print(f"Error scanning table {os.environ['MESSAGES_TABLE']}: {str(e)}")
        return []
    deserialized_messages = [deserialize_dynamodb_item(item) for item in all_messages]
    return extract_latest_messages_by_conversation(user_id, deserialized_messages)

def query_messages_by_user(client_id, index_name, key_name):
    try:
        response = dynamodb.query(
            TableName=os.environ['MESSAGES_TABLE'],
            IndexName=index_name,
            KeyConditionExpression=f'{key_name} = :uid',
            ExpressionAttributeValues={':uid': {'S': client_id}}
        )
        return response.get('Items', [])
    except ClientError as e:
        print(f"Error querying {key_name}-index for userId {client_id}: {str(e)}")
        return []

def extract_latest_messages_by_conversation(user_id, messages):
    latest_by_user = {}

    for message in messages:
        sender_id = message['senderId']
        receiver_id = message['receiverId']
        created_at = int(message['createdAt'])

        other_user = receiver_id if sender_id == user_id else sender_id

        if (other_user not in latest_by_user or
                created_at > int(latest_by_user[other_user]['createdAt'])):
            latest_by_user[other_user] = message

    return list(latest_by_user.values())

def deserialize_dynamodb_item(item):
    return {key: deserializer.deserialize(value) for key, value in item.items()}

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

def success_response(data):
    return {
        "statusCode": 200,
        "headers": { 
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*"
        },
        "body": json.dumps({
            "success": True,
            **data
        })
    }
