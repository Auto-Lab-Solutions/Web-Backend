import json
import boto3
import os

dynamodb = boto3.client('dynamodb')


def lambda_handler(event, context):
    connection_id = event['requestContext']['connectionId']
    domain = event["requestContext"]["domainName"]
    stage = event["requestContext"]["stage"]

    connection_item = get_connection_by_id(connection_id)
    if not connection_item:
        print(f"Connection not found for connectionId: {connection_id}")
        return {"statusCode": 400}

    delete_connection(connection_id)

    user_id = get_string_attr(connection_item, 'userId')
    if not user_id:
        print(f"Connection closed for connectionId: {connection_id} with no userId.")
        return {}
    
    apigateway = boto3.client(
        'apigatewaymanagementapi', 
        endpoint_url = "https://" + domain + "/" + stage
    )

    message_body = {
        "type": "notification",
        "subtype": "user-disconnected",
        "success": True,
        "userId": user_id
    }

    assigned_to = get_string_attr(connection_item, 'assignedTo')
    admin_connections = get_admin_connections(assigned_to)
    for item in admin_connections:
        admin_conn_id = item['connectionId']['S']
        apigateway.post_to_connection(
            Data=json.dumps(message_body),
            ConnectionId=admin_conn_id
        )
        print(f"Notification sent to admin connectionId: {admin_conn_id} for userId: {user_id}")

    print(f"Connection closed for connectionId: {connection_id} with userId: {user_id}")
    return {}



def get_connection_by_id(connection_id):
    result = dynamodb.query(
        TableName=os.environ['CONNECTIONS_TABLE'],
        KeyConditionExpression='connectionId = :cid',
        ExpressionAttributeValues={':cid': {'S': connection_id}}
    )
    return result['Items'][0] if result.get('Count', 0) > 0 else None

def delete_connection(connection_id):
    dynamodb.delete_item(
        TableName=os.environ['CONNECTIONS_TABLE'],
        Key={'connectionId': {'S': connection_id}}
    )

def get_string_attr(item, key):
    """Safely get a string attribute from a DynamoDB item."""
    return item.get(key, {}).get('S')

def get_admin_connections(assigned_to):
    if assigned_to:
        result = dynamodb.query(
            TableName=os.environ['CONNECTIONS_TABLE'],
            IndexName='userId-index',
            KeyConditionExpression='userId = :uid',
            ExpressionAttributeValues={':uid': {'S': assigned_to}}
        )
        if result.get('Count', 0) == 0:
            return []
        return [result['Items'][0]]
    else:
        result = dynamodb.scan(
            TableName=os.environ['CONNECTIONS_TABLE'],
            FilterExpression='admin = :admin',
            ExpressionAttributeValues={':admin': {'BOOL': True}}
        )
        return result.get('Items', [])
