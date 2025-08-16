from ..common_lib.websocket_utils import get_connection_manager
from ..common_lib.exceptions import BusinessLogicError

def lambda_handler(event, context):
    """
    Handle WebSocket disconnection (manager-based)
    """
    try:
        connection_manager = get_connection_manager()
        return connection_manager.disconnect_connection(event)
    except BusinessLogicError as e:
        print(f"Disconnection handling failed: {str(e)}")
        return {"statusCode": e.status_code}
    except Exception as e:
        print(f"Unexpected error in ws-disconnect: {str(e)}")
        return {"statusCode": 500}

