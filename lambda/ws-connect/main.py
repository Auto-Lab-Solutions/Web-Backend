from websocket_utils import get_connection_manager
from exceptions import BusinessLogicError

def lambda_handler(event, context):
    """
    Handle WebSocket connection establishment (manager-based)
    """
    try:
        connection_id = event['requestContext']['connectionId']
        connection_manager = get_connection_manager()
        create_success = connection_manager.create_connection(connection_id)
        return {}
    except BusinessLogicError as e:
        print(f"Connection creation failed: {str(e)}")
        return {"statusCode": e.status_code}
    except Exception as e:
        print(f"Unexpected error in ws-connect: {str(e)}")
        return {"statusCode": 500}
