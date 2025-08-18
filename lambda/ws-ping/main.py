
from websocket_utils import get_ping_manager
from exceptions import BusinessLogicError

def lambda_handler(event, context):
    """
    Handle WebSocket ping (manager-based)
    """
    try:
        ping_manager = get_ping_manager()
        return ping_manager.handle_ping(event)
    except BusinessLogicError as e:
        print(f"Ping handling failed: {str(e)}")
        return {"statusCode": e.status_code}
    except Exception as e:
        print(f"Unexpected error in ws-ping: {str(e)}")
        return {"statusCode": 500}
