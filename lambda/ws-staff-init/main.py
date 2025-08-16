from websocket_utils import get_staff_init_manager
from exceptions import BusinessLogicError

def lambda_handler(event, context):
    """
    Handle staff WebSocket initialization (manager-based)
    """
    try:
        staff_init_manager = get_staff_init_manager()
        return staff_init_manager.initialize_staff_connection(event)
    except BusinessLogicError as e:
        print(f"Staff initialization failed: {str(e)}")
        return {"statusCode": e.status_code}
    except Exception as e:
        print(f"Unexpected error in ws-staff-init: {str(e)}")
        return {"statusCode": 500}
