import uuid
import db_utils as db
import wsgw_utils as wsgw

def lambda_handler(event, context):
    connection_id = event.get('connectionId')
    domain = event.get('domain')
    stage = event.get('stage')
    request_body = event.get('body', {})
    
    user_id = request_body.get('userId', '')
    user_email = request_body.get('userEmail', '')
    user_name = request_body.get('userName', '')
    user_device = request_body.get('userDevice', '')
    user_location = request_body.get('userLocation', '')

    assigned_to = ''
    user_record = None

    wsgw_client = wsgw.get_apigateway_client(domain, stage)
    if not wsgw_client:
        print(f"Failed to get API Gateway client for domain: {domain}, stage: {stage}")
        return {}

    if user_id:
        db.delete_old_connections(user_id)
        user_record = db.get_user_record(user_id)
        if user_record:
            if 'assignedTo' in user_record:
                assigned_to = user_record.get('assignedTo')
        else:
            print(f"No user record found for userId: {user_id}")
            sent_success = wsgw.send_notification(
                wsgw_client,
                connection_id,
                {
                    "type": "connection",
                    "subtype": "init",
                    "success": False,
                    "cause": "INVALID_USER_ID"
                }
            )
            return {}

    existing_connection = db.get_connection(connection_id)
    if not existing_connection:
        print(f"Connection not found for connectionId: {connection_id}")
        return {}

    user_id = user_id or str(uuid.uuid4())

    # Update connection with userId and staff status
    
    connection_data = {
        'userId': user_id,
        'staff': 'false'
    }
    update_success = db.update_connection(connection_id, connection_data)
    if not update_success:
        print(f"Failed to update connection {connection_id} with userId {user_id}")
        sent_success = wsgw.send_notification(
            wsgw_client,
            connection_id,
            {
                "type": "connection",
                "subtype": "init",
                "success": False,
                "cause": "UPDATE_CONNECTION_FAILED"
            }
        )
        return {}

    # Create or update user record
    
    new_user_record = db.build_user_record(
        user_id,
        user_record,
        user_email=user_email,
        user_name=user_name,
        user_device=user_device,
        user_location=user_location,
        assigned_to=assigned_to
    )
    create_or_update_success = db.create_or_update_user_record(new_user_record)
    if not create_or_update_success:
        print(f"Failed to create or update user record for userId {user_id}")
        sent_success = wsgw.send_notification(
            wsgw_client,
            connection_id,
            {
                "type": "connection",
                "subtype": "init",
                "success": False,
                "cause": "UPDATE_USER_RECORD_FAILED"
            }
        )
        return {}

    # Send success notification to staff and user

    message_body = {
        "type": "notification",
        "subtype": "user-connected",
        "userId": user_id,
        "userEmail": user_email,
        "userName": user_name,
        "userDevice": user_device,
        "userLocation": user_location,
        "assignedTo": assigned_to
    }
    receivers = [db.get_connection_by_user_id(assigned_to)] if assigned_to else db.get_all_staff_connections()
    if receivers:
        for staff_conn in receivers:
            staff_conn_id = staff_conn.get('connectionId')
            sent_success = wsgw.send_notification(
                wsgw_client,
                staff_conn_id,
                message_body
            )
    
    sent_success = wsgw.send_notification(
        wsgw_client,
        connection_id,
        {
            "type": "connection",
            "subtype": "init",
            "success": True,
            "userId": user_id
        }
    )

    print(f"Connection established for connectionId: {connection_id} with userId: {user_id}")
    return {}

