import db_utils as db
import response_utils as resp
import request_utils as req

def lambda_handler(event, context):
    staff_user_email = req.get_staff_user_email(event)

    staff_user_record = db.get_staff_record(staff_user_email)
    if not staff_user_record:
        return resp.error_response("Unauthorized: Staff user not found.")

    staff_user_id = staff_user_record.get('userId')
    staff_roles = staff_user_record.get('roles', [])
    
    if not staff_user_id or not staff_roles:
        return resp.error_response("Unauthorized: Invalid staff user record.")
    
    customer_users = db.get_all_users()
    staff_users = db.get_all_staff_records()
    return resp.success_response({
        "customerUsers": customer_users,
        "staffUsers": staff_users
    })
