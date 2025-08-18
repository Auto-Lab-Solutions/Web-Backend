import response_utils as resp
import business_logic_utils as biz

@biz.handle_business_logic_error
def lambda_handler(event, context):
    try:
        # Get user manager and validate staff authentication
        user_manager = biz.get_user_manager()
        staff_context = user_manager.validate_staff_authentication(event)
        
        # Get all users
        user_data = user_manager.get_all_users()
        
        return resp.success_response({
            "customerUsers": resp.convert_decimal(user_data['customer_users']),
            "staffUsers": resp.convert_decimal(user_data['staff_users'])
        })

    except Exception as e:
        print(f"Error in get users lambda: {str(e)}")
        return resp.error_response("Internal server error", 500)
