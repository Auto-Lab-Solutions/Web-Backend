from ..common_lib.websocket_utils import get_user_init_manager
from ..common_lib.exceptions import BusinessLogicError

def lambda_handler(event, context):
    """
    Handle user WebSocket initialization (manager-based)
    """
    try:
        user_init_manager = get_user_init_manager()
        return user_init_manager.initialize_user_connection(event)
    except BusinessLogicError as e:
        print(f"User initialization failed: {str(e)}")
        return {"statusCode": e.status_code}
    except Exception as e:
        print(f"Unexpected error in ws-init: {str(e)}")
        return {"statusCode": 500}

