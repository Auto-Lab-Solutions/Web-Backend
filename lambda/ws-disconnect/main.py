import db_utils as db
import wsgw_utils as wsgw

def lambda_handler(event, context):
    connection_id = event['requestContext']['connectionId']
    domain = event["requestContext"]["domainName"]
    stage = event["requestContext"]["stage"]

    connection_item = db.get_connection(connection_id)
    if not connection_item:
        print(f"Connection not found for connectionId: {connection_id}")
        return {}

    db.delete_connection(connection_id)

    user_id = connection_item.get('userId')
    if not user_id:
        print(f"Connection closed for connectionId: {connection_id} with no userId.")
        return {}
    
    wsgw_client = wsgw.get_apigateway_client(domain, stage)

    message_body = {
        "type": "notification",
        "subtype": "user-disconnected",
        "success": True,
        "userId": user_id
    }
    
    user_record = db.get_user_record(user_id)
    assigned_to = user_record.get('assignedTo') if user_record else ''
    staff_connections = db.get_assigned_or_all_staff_connections(assigned_to)
    for connection in staff_connections:
        staff_conn_id = connection.get('connectionId')
        wsgw.send_notification(wsgw_client, staff_conn_id, message_body)

    print(f"Connection closed for connectionId: {connection_id} with userId: {user_id}")
    return {}

