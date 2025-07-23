import db_utils as db
import request_utils as req
import response_utils as resp

PERMITTED_ROLE = 'CUSTOMER_SUPPORT'

def lambda_handler(event, context):
    staff_user_email = req.get_staff_user_email(event)
    if not staff_user_email:
        return resp.error_response("Unauthorized: Staff authentication required", 401)

    staff_user_record = db.get_staff_record(staff_user_email)
    if not staff_user_record:
        return resp.error_response("Unauthorized: Staff user not found.")

    staff_user_id = staff_user_record.get('userId')
    staff_roles = staff_user_record.get('roles', [])
    
    if not staff_user_id or not staff_roles:
        return resp.error_response("Unauthorized: Invalid staff user record.")

    if PERMITTED_ROLE not in staff_roles:
        return resp.error_response("Unauthorized: Insufficient permissions.")
    
    connections = db.get_all_active_connections()
    return resp.success_response({
        "connections": resp.convert_decimal(connections)
    })


