import os
import sys

# Add common_lib to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'common_lib'))

import response_utils as resp
import business_logic_utils as biz

@biz.handle_business_logic_error
def lambda_handler(event, context):
    try:
        # Get unavailable slot manager and validate staff authentication
        slot_manager = biz.get_unavailable_slot_manager()
        staff_context = slot_manager.validate_staff_authentication(event, slot_manager.admin_roles)
        
        # Update unavailable slots
        result = slot_manager.update_unavailable_slots(event, staff_context)
        
        return resp.success_response(result)

    except Exception as e:
        print(f"Error in update unavailable slots lambda: {str(e)}")
        return resp.error_response("Internal server error", 500)
