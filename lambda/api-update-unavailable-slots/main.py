import response_utils as resp
import business_logic_utils as biz

@biz.handle_business_logic_error
def lambda_handler(event, context):
    # Get unavailable slot manager and validate staff authentication
    slot_manager = biz.get_unavailable_slot_manager()
    staff_context = slot_manager.validate_staff_authentication(event, slot_manager.admin_roles)
    
    # Update unavailable slots
    result = slot_manager.update_unavailable_slots(event, staff_context)
    
    return resp.success_response(result)
