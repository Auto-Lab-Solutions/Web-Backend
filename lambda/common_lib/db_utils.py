import boto3
import os
from botocore.exceptions import ClientError
from boto3.dynamodb.types import TypeDeserializer

# Dynamodb client and deserializer
dynamodb = boto3.client('dynamodb')
deserializer = TypeDeserializer()

# Environment variables
STAFF_TABLE = os.environ['STAFF_TABLE']


# ------------------  Staff Table Functions ------------------

def get_staff_record(email):
    try:
        result = dynamodb.query(
            TableName=STAFF_TABLE,
            KeyConditionExpression='userEmail = :email',
            ExpressionAttributeValues={':email': {'S': email}}
        )
        if result.get('Count', 0) > 0:
            return {k: deserializer.deserialize(v) for k, v in result['Items'][0].items()}
        return None
    except ClientError as e:
        print(f"Error querying staff record: {e.response['Error']['Message']}")
        return None

# -------------------------------------------------------------