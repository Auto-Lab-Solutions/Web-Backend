import response_utils as resp
import business_logic_utils as biz
import request_utils as req
import db_utils as db
from exceptions import BusinessLogicError

@biz.handle_business_logic_error
def lambda_handler(event, context):
    try:
        # Get userId from query parameters
        user_id = req.get_query_param(event, 'userId')
        
        # Validate required parameter
        if not user_id:
            raise BusinessLogicError("userId query parameter is required", 400)
        
        # Check if user exists in the database
        user_record = db.get_user_record(user_id)
        
        if user_record:
            return resp.success_response({
                "valid": True,
                "message": "User ID is valid",
                "userId": user_id
            })
        else:
            # Create a new user record if it doesn't exist
            new_user_data = db.build_user_record(user_id, None)
            success = db.create_or_update_user_record(new_user_data)
            
            if success:
                return resp.success_response({
                    "valid": True,
                    "message": "User ID created successfully",
                    "userId": user_id
                })
            else:
                return resp.error_response("Failed to create user record", 500)

    except Exception as e:
        print(f"Error in check user lambda: {str(e)}")
        return resp.error_response("Internal server error", 500)
