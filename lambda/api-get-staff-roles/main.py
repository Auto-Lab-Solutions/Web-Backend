import os
import json
import traceback

import response_utils as resp
import request_utils as req
import business_logic_utils as biz

SHARED_KEY = os.environ.get("SHARED_KEY")

@biz.handle_business_logic_error
def lambda_handler(event, context):
    print(f"Lambda invoked with event: {json.dumps(event, default=str)}")
    print(f"Context: {context}")
    
    # Validate environment variables
    if not SHARED_KEY:
        print("Error: SHARED_KEY environment variable is not set")
        error_response = resp.error_response("Internal server error: Missing configuration", 500)
        print(f"Returning error response: {json.dumps(error_response, default=str)}")
        return error_response
    
    try:
        # Get request parameters
        print("Extracting request parameters...")
        email = req.get_query_param(event, 'email')
        shared_key = req.get_header(event, 'shared-api-key')
        
        print(f"Email parameter: {email}")
        print(f"Shared key header present: {bool(shared_key)}")
        
        # Enhanced validation with better error messages
        if not email:
            print("Missing email parameter")
            error_response = resp.error_response("Email query parameter is required", 400)
            print(f"Returning error response: {json.dumps(error_response, default=str)}")
            return error_response
        
        if not shared_key:
            print("Missing shared-api-key header")
            error_response = resp.error_response("shared-api-key header is required", 400)
            print(f"Returning error response: {json.dumps(error_response, default=str)}")
            return error_response
        
        # Get staff role manager and retrieve roles
        print("Getting staff role manager...")
        role_manager = biz.get_staff_role_manager()
        
        print(f"Retrieving roles for email: {email}")
        roles = role_manager.get_staff_roles(email, shared_key, SHARED_KEY)
        
        print(f"Retrieved roles: {roles}")
        
        success_response = resp.success_response({
            "roles": roles
        })
        
        print(f"Returning success response: {json.dumps(success_response, default=str)}")
        return success_response
        
    except Exception as e:
        print(f"Unexpected error in lambda_handler: {str(e)}")
        print(f"Error type: {type(e).__name__}")
        traceback.print_exc()
        
        error_response = resp.error_response(f"Internal server error: {str(e)}", 500)
        print(f"Returning error response: {json.dumps(error_response, default=str)}")
        return error_response

