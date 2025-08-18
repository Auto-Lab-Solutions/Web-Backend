import response_utils as resp
import request_utils as req
import business_logic_utils as biz

@biz.handle_business_logic_error
def lambda_handler(event, context):
    """Send message with business logic validation and notifications"""
    
    # Extract request parameters
    staff_user_email = req.get_staff_user_email(event)
    client_id = req.get_body_param(event, 'clientId')
    message_id = req.get_body_param(event, 'messageId')
    message = req.get_body_param(event, 'message')
    
    # Use business logic manager to handle the complete workflow
    result = biz.MessageManager.send_message(
        staff_user_email=staff_user_email,
        client_id=client_id,
        message_id=message_id,
        message=message
    )
    
    return resp.success_response(result)
