import response_utils as resp
import request_utils as req
import data_retrieval_utils as data

@data.handle_data_retrieval_error
def lambda_handler(event, context):
    """Get orders with proper access control and filtering"""
    
    # Extract request parameters
    staff_user_email = req.get_staff_user_email(event)
    order_id = req.get_path_param(event, 'orderId')
    user_id = req.get_query_param(event, 'userId')
    
    # Use data retriever to handle access control and filtering
    result = data.DataRetriever.get_orders_with_access_control(
        staff_user_email=staff_user_email,
        user_id=user_id,
        order_id=order_id,
        event=event
    )
    
    return resp.success_response(result)
