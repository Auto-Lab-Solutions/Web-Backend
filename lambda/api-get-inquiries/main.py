import response_utils as resp
import request_utils as req
import business_logic_utils as biz

@biz.handle_business_logic_error
def lambda_handler(event, context):
    try:
        # Get inquiry manager and validate staff authentication
        inquiry_manager = biz.get_inquiry_manager()
        staff_context = inquiry_manager.validate_staff_authentication(event)
        
        # Get inquiry ID from path parameters (optional)
        inquiry_id = req.get_path_param(event, 'inquiryId')
        
        if inquiry_id:
            # Get single inquiry by ID
            inquiry = inquiry_manager.get_inquiry_by_id(inquiry_id)
            return resp.success_response({
                "inquiry": resp.convert_decimal(inquiry)
            })
        else:
            # Get all inquiries with filters
            inquiries = inquiry_manager.get_all_inquiries_with_filters(event)
            return resp.success_response({
                "inquiries": resp.convert_decimal(inquiries),
                "count": len(inquiries)
            })

    except Exception as e:
        print(f"Error in get inquiries lambda: {str(e)}")
        return resp.error_response("Internal server error", 500)
