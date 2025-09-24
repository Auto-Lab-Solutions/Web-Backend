import response_utils as resp
import business_logic_utils as biz

@biz.handle_business_logic_error
def lambda_handler(event, context):
    try:
        # Get upload manager and validate staff authentication
        upload_manager = biz.get_upload_manager()
        staff_context = upload_manager.validate_staff_authentication(event, upload_manager.permitted_roles)
        
        # Generate upload URL (supports both reports and attachments)
        upload_data = upload_manager.generate_upload_url(event, staff_context)
        
        return resp.success_response(upload_data)

    except Exception as e:
        print(f"Error in get upload URL lambda: {str(e)}")
        return resp.error_response("Internal server error", 500)

