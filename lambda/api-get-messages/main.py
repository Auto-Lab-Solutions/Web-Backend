import response_utils as resp
import request_utils as req
import business_logic_utils as biz

@biz.handle_business_logic_error
def lambda_handler(event, context):
    try:
        # Get client ID parameter
        client_id = req.get_query_param(event, 'clientId')
        
        # Get message manager and retrieve messages
        message_manager = biz.get_message_manager()
        messages = message_manager.get_user_messages(client_id)
        
        print(f"Retrieved {len(messages)} messages for clientId: {client_id}")
        return resp.success_response({
            "messages": resp.convert_decimal(messages)
        })

    except Exception as e:
        print(f"Error in get messages lambda: {str(e)}")
        return resp.error_response("Internal server error", 500)
