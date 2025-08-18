import os

import response_utils as resp
import request_utils as req
import business_logic_utils as biz

SHARED_KEY = os.environ.get("SHARED_KEY")

@biz.handle_business_logic_error
def lambda_handler(event, context):
    try:
        # Get request parameters
        email = req.get_query_param(event, 'email')
        shared_key = req.get_header(event, 'shared-api-key')
        
        # Get staff role manager and retrieve roles
        role_manager = biz.get_staff_role_manager()
        roles = role_manager.get_staff_roles(email, shared_key, SHARED_KEY)
        
        return resp.success_response({
            "roles": roles
        })

    except Exception as e:
        print(f"Error in get staff roles lambda: {str(e)}")
        return resp.error_response("Internal server error", 500)

