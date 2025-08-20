import boto3, os, json
from botocore.exceptions import ClientError

# Environment variables
WEBSOCKET_ENDPOINT_URL = os.environ.get('WEBSOCKET_ENDPOINT_URL')
WEBSOCKET_API_ID = os.environ.get('WEBSOCKET_API_ID')
AWS_REGION = os.environ.get('AWS_REGION', os.environ.get('AWS_DEFAULT_REGION', 'us-east-1'))
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'production')

def get_apigateway_client(domain=None, stage=None):
    try:
        if domain and stage:
            endpoint_url = "https://" + domain + "/" + stage
        elif WEBSOCKET_ENDPOINT_URL:
            endpoint_url = WEBSOCKET_ENDPOINT_URL
        elif WEBSOCKET_API_ID:
            # Construct the endpoint URL from API ID
            endpoint_url = f"https://{WEBSOCKET_API_ID}.execute-api.{AWS_REGION}.amazonaws.com/{ENVIRONMENT}"
        else:
            print("Error: No WebSocket endpoint URL or API ID configured")
            return None
            
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
