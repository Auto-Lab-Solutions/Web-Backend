import os
import db_utils as db
import response_utils as resp
import request_utils as req

SHARED_KEY = os.environ.get("SHARED_KEY")

def lambda_handler(event, context):
    email = req.get_query_param(event, 'email')
    shared_key = req.get_header(event, 'shared-api-key')

    if not email or not shared_key:
        return resp.error_response("Email and sharedKey are required.")
    if shared_key != SHARED_KEY:
        return resp.error_response("Invalid sharedKey provided.")
    
    staff_record = db.get_staff_record(email)
    if not staff_record:
        return resp.error_response(f"No staff record found for email: {email}.")
    
    return resp.success_response({
        "roles": staff_record.get('roles', [])
    })

