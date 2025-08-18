import boto3, os, json
from botocore.exceptions import ClientError

# Environment variables
WEBSOCKET_ENDPOINT_URL = os.environ.get('WEBSOCKET_ENDPOINT_URL')

def get_apigateway_client(domain=None, stage=None):
    try:
        if domain and stage:
            endpoint_url = "https://" + domain + "/" + stage
        else:
            endpoint_url = WEBSOCKET_ENDPOINT_URL
        return boto3.client('apigatewaymanagementapi', endpoint_url=endpoint_url)
    except Exception as e:
        print(f"Error creating API Gateway Management client: {e}")
        return None

def send_notification(client, connection_id, data):
    try:
        client.post_to_connection(
            ConnectionId=connection_id,
            Data=json.dumps(data)
        )
        print(f"Notification sent to {connection_id}")
        return True
    except ClientError as e:
        if e.response['Error']['Code'] == 'GoneException':
            print(f"Connection {connection_id} is no longer available.")
        else:
            print(f"Error sending notification to {connection_id}: {e}")
