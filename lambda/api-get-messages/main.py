import db_utils as db
import response_utils as resp
import request_utils as req

def lambda_handler(event, context):
    client_id = req.get_query_param(event, 'clientId')

    if not client_id:
        return resp.error_response("clientId is required.")
    
    if db.get_staff_record(client_id):
        return resp.error_response("Cannot retrieve messages for using staff userId.")

    if not db.get_user_record(client_id):
        return resp.error_response(f"User with userId {client_id} does not exist.")
    
    sender_messages = db.get_messages_by_index(index_name='senderId-index', key_name='senderId', key_value=client_id)
    receiver_messages = db.get_messages_by_index(index_name='receiverId-index', key_name='receiverId', key_value=client_id)
    all_messages = sender_messages + receiver_messages

    sorted_messages = sorted(all_messages, key=lambda x: int(x.get('createdAt', 0)), reverse=True)

    print(f"Retrieved {len(sorted_messages)} messages for clientId: {client_id}")
    return resp.success_response({
        "messages": resp.convert_decimal(sorted_messages)
    })
