import db_utils as db
import response_utils as resp
from decimal import Decimal

def lambda_handler(event, context):
    connections = db.get_all_active_connections()
    return resp.success_response({
        "connections": convert_decimal(connections)
    })

def convert_decimal(obj):
    if isinstance(obj, list):
        return [convert_decimal(i) for i in obj]
    elif isinstance(obj, dict):
        return {k: convert_decimal(v) for k, v in obj.items()}
    elif isinstance(obj, Decimal):
        return float(obj)
    return obj
