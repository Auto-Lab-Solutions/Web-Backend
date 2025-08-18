import json
from decimal import Decimal

response_headers = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
    "Access-Control-Allow-Methods": "OPTIONS,GET,POST,PATCH,PUT"
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

def convert_decimal(obj):
    if isinstance(obj, list):
        return [convert_decimal(i) for i in obj]
    elif isinstance(obj, dict):
        return {k: convert_decimal(v) for k, v in obj.items()}
    elif isinstance(obj, Decimal):
        return float(obj)
    return obj
