import response_utils as resp
import request_utils as req
import validation_utils as valid
import business_logic_utils as biz
from appointment_manager import AppointmentManager

@biz.handle_business_logic_error
@valid.handle_validation_error
def lambda_handler(event, context):
    """Create a new appointment with business logic validation and notifications"""
    
    # Extract request parameters
    staff_user_email = req.get_staff_user_email(event)
    user_id = req.get_body_param(event, 'userId')
    appointment_data = req.get_body_param(event, 'appointmentData')
    
    # Validate appointment data structure
    valid_data, error_msg = valid.AppointmentDataValidator.validate_appointment_data(
        appointment_data, 
        staff_user=bool(staff_user_email)
    )
    if not valid_data:
        raise valid.ValidationError(error_msg)
    
    # Use business logic manager to handle the complete workflow
    result = AppointmentManager.create_appointment(
        staff_user_email=staff_user_email,
        user_id=user_id,
        appointment_data=appointment_data
    )
    
    return resp.success_response(result)



