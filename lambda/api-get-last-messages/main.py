import db_utils as db
import response_utils as resp
import request_utils as req

def lambda_handler(event, context):
    staff_user_email = req.get_staff_user_email(event)
    
    staff_user_record = db.get_staff_record(staff_user_email)
    if not staff_user_record:
        return resp.error_response("Unauthorized: Staff user not found.")
    
    staff_user_id = staff_user_record.get('userId')
    latest_messages = sorted(get_latest_messages_by_user(staff_user_id), key=lambda x: int(x['createdAt']), reverse=True)

    return resp.success_response({"messages": resp.convert_decimal(latest_messages)})


def get_latest_messages_by_user(user_id):
    sender_messages = db.get_messages_by_index(index_name='senderId-index', key_name='senderId', key_value=user_id)
    receiver_messages = db.get_messages_by_index(index_name='receiverId-index', key_name='receiverId', key_value=user_id)
    staff_unassigned_messages = db.get_messages_by_index(index_name='receiverId-index', key_name='receiverId', key_value='ALL')
    
    all_messages = sender_messages + receiver_messages + staff_unassigned_messages

    return extract_latest_messages_by_conversation(user_id, all_messages)


def extract_latest_messages_by_conversation(user_id, messages):
    latest_by_user = {}

    for message in messages:
        sender_id = message['senderId']
        receiver_id = message['receiverId']
        created_at = int(message['createdAt'])

        other_user = receiver_id if sender_id == user_id else sender_id

        if (other_user not in latest_by_user or
                created_at > int(latest_by_user[other_user]['createdAt'])):
            latest_by_user[other_user] = message

    return list(latest_by_user.values())

