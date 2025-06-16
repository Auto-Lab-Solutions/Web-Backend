import json
import boto3
import os
import time

dynamodb = boto3.client('dynamodb')

def lambda_handler(event, context):
    connectionId = event['requestContext']['connectionId']

    dynamodb.put_item(
        TableName=os.environ['CONNECTIONS_TABLE'],
        Item={'connectionId': {'S': connectionId}, 'createdAt': {'N': str(int(time.time()))}}
    )

    return {}
