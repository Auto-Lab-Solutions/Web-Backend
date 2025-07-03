import db_utils as db
import response_utils as resp
import request_utils as req

def lambda_handler(event, context):
    customer_users = db.get_all_users()
    staff_users = db.get_all_staff_records()
    return resp.success_response({
        "customerUsers": customer_users,
        "staffUsers": staff_users
    })
