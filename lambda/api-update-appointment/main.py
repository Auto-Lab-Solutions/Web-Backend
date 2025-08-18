import request_utils as req
import response_utils as resp
import permission_utils as perm
import business_logic_utils as biz
from appointment_manager import AppointmentUpdateManager

@perm.handle_permission_error  
@biz.handle_business_logic_error
def lambda_handler(event, context):
    """Update appointment using the new manager-based approach"""
    
    # Get staff user information
    staff_user_email = req.get_staff_user_email(event)
    
    # Get appointment ID from path parameters
    appointment_id = req.get_path_param(event, 'appointmentId')
    if not appointment_id:
        raise biz.BusinessLogicError("appointmentId is required in path")
    
    # Get request body
    body = req.get_body(event)
    if not body:
        raise biz.BusinessLogicError("Request body is required")
    
    # Use the appointment update manager to handle the complete workflow
    result = AppointmentUpdateManager.update_appointment(
        staff_user_email=staff_user_email,
        appointment_id=appointment_id,
        update_data=body
    )
    
    return resp.success_response(result)