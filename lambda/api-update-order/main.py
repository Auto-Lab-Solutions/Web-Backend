import request_utils as req
import response_utils as resp
import permission_utils as perm
import business_logic_utils as biz
from order_manager import OrderUpdateManager

@perm.handle_permission_error
@biz.handle_business_logic_error 
def lambda_handler(event, context):
    """Update order using the new manager-based approach"""
    
    # Get staff user information
    staff_user_email = req.get_staff_user_email(event)
    
    # Get order ID from path parameters
    order_id = req.get_path_param(event, 'orderId')
    if not order_id:
        raise biz.BusinessLogicError("orderId is required in path")
    
    # Get request body
    body = req.get_body(event)
    if not body:
        raise biz.BusinessLogicError("Request body is required")
    
    # Use the order update manager to handle the complete workflow
    result = OrderUpdateManager.update_order(
        staff_user_email=staff_user_email,
        order_id=order_id,
        update_data=body
    )
    
    return resp.success_response(result)
