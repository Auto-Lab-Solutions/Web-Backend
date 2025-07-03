import db_utils as db
import response_utils as resp

def lambda_handler(event, context):
    connections = db.get_all_active_connections()
    return resp.success_response({
        "connections": resp.convert_decimal(connections)
    })


