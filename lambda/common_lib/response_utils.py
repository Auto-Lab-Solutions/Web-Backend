import json

response_headers = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*"
}

def error_response(message, status_code=400):
    print(message)
    return {
        "statusCode": status_code,
        "headers": response_headers,
        "body": json.dumps({
            "success": False,
            "message": message
        })
    }

def success_response(data, success=True, status_code=200):
    return {
        "statusCode": status_code,
        "headers": response_headers,
        "body": json.dumps({
            "success": success,
            **data
        })
    }
