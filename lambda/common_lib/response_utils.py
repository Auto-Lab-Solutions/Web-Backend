import json
from decimal import Decimal

response_headers = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token,shared-api-key",
    "Access-Control-Allow-Methods": "OPTIONS,GET,POST,PATCH,PUT"
}

def convert_decimal(obj):
    """Convert Decimal objects to float for JSON serialization"""
    if isinstance(obj, list):
        return [convert_decimal(i) for i in obj]
    elif isinstance(obj, dict):
        return {k: convert_decimal(v) for k, v in obj.items()}
    elif isinstance(obj, Decimal):
        return float(obj)
    return obj

def safe_json_dumps(data):
    """Safely serialize data to JSON with proper error handling"""
    try:
        # First convert any Decimal objects
        converted_data = convert_decimal(data)
        # Then serialize to JSON
        return json.dumps(converted_data, default=str)
    except Exception as e:
        print(f"JSON serialization error: {str(e)}")
        print(f"Data type: {type(data)}")
        print(f"Data content: {data}")
        # Fallback to string representation
        return json.dumps({"error": "Serialization failed", "raw_data": str(data)})

def error_response(message, status_code=400):
    print(f"Error response: {message} (status: {status_code})")
    
    response_body = {
        "success": False,
        "message": message
    }
    
    response = {
        "statusCode": status_code,
        "headers": response_headers,
        "body": safe_json_dumps(response_body)
    }
    
    print(f"Formatted error response: {response}")
    return response

def success_response(data, success=True, status_code=200):
    print(f"Success response with data: {data}")
    
    response_body = {
        "success": success,
        **data
    }
    
    response = {
        "statusCode": status_code,
        "headers": response_headers,
        "body": safe_json_dumps(response_body)
    }
    
    print(f"Formatted success response: {response}")
    return response
