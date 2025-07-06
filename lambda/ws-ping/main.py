
def lambda_handler(event, context):
    connection_id = event.get('connectionId')
    domain = event.get('domain')
    stage = event.get('stage')
    request_body = event.get('body', {})
    
    user_id = request_body.get('userId', '')
    print(f"Received ping for connection {connection_id} with userId {user_id}")

    return {}
