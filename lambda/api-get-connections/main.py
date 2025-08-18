import response_utils as resp
import request_utils as req
import data_retrieval_utils as data

@data.handle_data_retrieval_error
def lambda_handler(event, context):
    """Get WebSocket connections with proper staff access control"""
    
    # Extract staff user email
    staff_user_email = req.get_staff_user_email(event)
    
    # Use data retriever to handle access control
    result = data.StaffDataRetriever.get_connections_with_access_control(
        staff_user_email=staff_user_email
    )
    
    return resp.success_response(result)


