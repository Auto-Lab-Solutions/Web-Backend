import response_utils as resp
import business_logic_utils as biz

@biz.handle_business_logic_error
def lambda_handler(event, context):
    try:
        # Get unavailable slot manager
        slot_manager = biz.get_unavailable_slot_manager()
        
        # Get unavailable slots data
        slots_data = slot_manager.get_unavailable_slots(event)
        
        return resp.success_response(slots_data)

    except Exception as e:
        print(f"Error in get unavailable slots lambda: {str(e)}")
        return resp.error_response("Internal server error", 500)
