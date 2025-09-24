import boto3, os, json
from botocore.exceptions import ClientError

# Environment variables
WEBSOCKET_ENDPOINT_URL = os.environ.get('WEBSOCKET_ENDPOINT_URL')
WEBSOCKET_API_ID = os.environ.get('WEBSOCKET_API_ID')
AWS_REGION = os.environ.get('AWS_REGION', os.environ.get('AWS_DEFAULT_REGION', 'us-east-1'))
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'production')

def get_apigateway_client(domain=None):
    try:
        if WEBSOCKET_ENDPOINT_URL:
            endpoint_url = WEBSOCKET_ENDPOINT_URL
        elif WEBSOCKET_API_ID:
            # Construct the endpoint URL from API ID
            endpoint_url = f"https://{WEBSOCKET_API_ID}.execute-api.{AWS_REGION}.amazonaws.com/{ENVIRONMENT}"
        elif domain:
            # For WebSocket API Management, domain already contains the stage
            endpoint_url = f"https://{domain}"
        else:
            print("Error: No WebSocket endpoint URL or API ID configured")
            return None
            
        print(f"Creating API Gateway Management client with endpoint: {endpoint_url}")
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
        error_code = e.response['Error']['Code']
        if error_code == 'GoneException':
            print(f"Connection {connection_id} is no longer available (GoneException).")
            # Clean up stale connection from database
            import db_utils as db
            db.delete_connection(connection_id)
        elif error_code == 'NotFoundException':
            print(f"Connection {connection_id} not found (NotFoundException). The WebSocket API endpoint may be incorrect.")
            print(f"Error details: {e}")
            # Also clean up the stale connection
            import db_utils as db
            db.delete_connection(connection_id)
        else:
            print(f"Error sending notification to {connection_id}: {e}")
            print(f"Error code: {error_code}")
        return False
