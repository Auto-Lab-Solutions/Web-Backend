import json
import db_utils as db
import auth_utils as auth
import wsgw_utils as wsgw

PERMITTED_ROLE = 'CUSTOMER_SUPPORT'

def lambda_handler(event, context):
    connection_id = event.get('connectionId')
    domain = event.get('domain')
    stage = event.get('stage')
    request_body = event.get('body', {})
    token = request_body.get('token', '')

    user_email = auth.get_user_email(token)
    if not user_email:
        print("Invalid or missing token.")
        return {}
    
    staff_user_record = db.get_staff_record(user_email)
    if not staff_user_record:
        print(f"No staff record found for email: {user_email}")
        return {}
    
    staff_user_id = staff_user_record.get('userId')
    staff_roles = staff_user_record.get('roles', [])
    if not staff_user_id or not staff_roles:
        print(f"Staff record is missing userId or roles for email: {user_email}")
        return {}

    if PERMITTED_ROLE not in staff_roles:
        print(f"User {user_email} does not have necessary permissions to establish a connection.")
        return {}
    
    db.delete_old_connections(staff_user_id)

    if not db.get_connection(connection_id):
        print(f"Connection not found for connectionId: {connection_id}")
        return {}

    connection_data = {
        'userId': staff_user_id,
        'staff': 'true'
    }
    update_success = db.update_connection(connection_id, connection_data)

    wsgw_client = wsgw.get_apigateway_client(domain, stage)
    if not wsgw_client:
        print(f"Failed to get API Gateway client for domain: {domain}, stage: {stage}")
        return {}

    notification_success = wsgw.send_notification(
        wsgw_client,
        connection_id,
        {
            "type": "connection",
            "subtype": "init",
            "success": update_success,
            "userId": staff_user_id
        }
    )

    print(f"Connection established for connectionId: {connection_id} with userId: {staff_user_id}")
    return {}
