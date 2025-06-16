import json
import boto3
import os
from botocore.exceptions import ClientError
from boto3.dynamodb.types import TypeDeserializer

dynamodb = boto3.client('dynamodb')
deserializer = TypeDeserializer()

def lambda_handler(event, context):
    connections = get_all_active_connections()
    return success_response({
        "connections": connections
    })


def get_all_active_connections():
    try:
        response = dynamodb.scan(
            TableName=os.environ["CONNECTIONS_TABLE"],
        )
        connections = response.get('Items', [])
        return [deserialize_dynamodb_item(item) for item in filter_initialized_connections(connections)]
    except ClientError as e:
        print(f"Error retrieving active connections: {e}")
        return []

def deserialize_dynamodb_item(item):
    return {key: deserializer.deserialize(value) for key, value in item.items()}

def filter_initialized_connections(connections):
    return [conn for conn in connections if 'userId' in conn and conn['userId']['S']]

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
