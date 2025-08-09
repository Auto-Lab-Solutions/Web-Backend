import db_utils as db
import auth_utils as auth
import wsgw_utils as wsgw

PERMITTED_ROLES = ['CUSTOMER_SUPPORT', 'CLERK']

def lambda_handler(event, context):
    connection_id = event.get('connectionId')
    domain = event.get('domain')
    stage = event.get('stage')
    request_body = event.get('body', {})
    token = request_body.get('token', '')

    wsgw_client = wsgw.get_apigateway_client(domain, stage)
    if not wsgw_client:
        print(f"Failed to get API Gateway client for domain: {domain}, stage: {stage}")
        return {}

    if not db.get_connection(connection_id):
        print(f"Connection not found for connectionId: {connection_id}")
        return {}

    user_email = auth.get_user_email(token)
    if not user_email:
        wsgw.send_notification(
            wsgw_client,
            connection_id,
            {
                "type": "connection",
                "subtype": "init",
                "success": False,
                "error": "INVALID_TOKEN",
            }
        )
        return {}
    
    staff_user_record = db.get_staff_record(user_email)
    if not staff_user_record:
        wsgw.send_notification(
            wsgw_client,
            connection_id,
            {
                "type": "connection",
                "subtype": "init",
                "success": False,
                "error": "INVALID_USER",
            }
        )
        return {}
    
    staff_user_id = staff_user_record.get('userId')
    staff_roles = staff_user_record.get('roles', [])
    if not staff_user_id or not staff_roles:
        wsgw.send_notification(
            wsgw_client,
            connection_id,
            {
                "type": "connection",
                "subtype": "init",
                "success": False,
                "error": "MISSING_USER_ID_OR_ROLES",
            }
        )
        return {}

    if not any(role in staff_roles for role in PERMITTED_ROLES):
        wsgw.send_notification(
            wsgw_client,
            connection_id,
            {
                "type": "connection",
                "subtype": "init",
                "success": False,
                "error": "UNAUTHORIZED_ROLE",
            }
        )
        return {}
    
    db.delete_old_connections(staff_user_id)

    connection_data = {
        'userId': staff_user_id,
        'staff': 'true'
    }
    update_success = db.update_connection(connection_id, connection_data)

    if not update_success:
        wsgw.send_notification(
            wsgw_client,
            connection_id,
            {
                "type": "connection",
                "subtype": "init",
                "success": False,
                "error": "UPDATE_CONNECTION_FAILED"
            }
        )
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
