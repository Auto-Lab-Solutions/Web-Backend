import json
import boto3
import os
from botocore.exceptions import ClientError
from boto3.dynamodb.types import TypeDeserializer

dynamodb = boto3.client('dynamodb')
deserializer = TypeDeserializer()

def lambda_handler(event, context):
    query_params = event.get('queryStringParameters') or {}
    client_id = query_params.get('clientId')

    if not client_id:
        return error_response("userId is required.")
    
    if get_admin_record_by_id(client_id):
        return error_response("Cannot retrieve messages for an admin user.")

    sender_messages = query_messages_by_user(client_id, index_name='senderId-index', key_name='senderId')
    receiver_messages = query_messages_by_user(client_id, index_name='receiverId-index', key_name='receiverId')

    all_messages = sender_messages + receiver_messages
    sorted_messages = sorted(all_messages, key=lambda x: int(x['createdAt']['S']), reverse=False)
    sorted_messages = [deserialize_dynamodb_item(msg) for msg in sorted_messages]

    print(f"Retrieved {len(sorted_messages)} messages for clientId: {client_id}")
    return success_response({
        "messages": sorted_messages
    })

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

def query_messages_by_user(user_id, index_name, key_name):
    try:
        response = dynamodb.query(
            TableName=os.environ['MESSAGES_TABLE'],
            IndexName=index_name,
            KeyConditionExpression=f'{key_name} = :uid',
            ExpressionAttributeValues={':uid': {'S': user_id}}
        )
        return response.get('Items', [])
    except ClientError as e:
        print(f"Error querying {key_name}-index for userId {user_id}: {str(e)}")
        return []
    
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
