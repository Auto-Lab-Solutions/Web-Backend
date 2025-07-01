import db_utils as db

def lambda_handler(event, context):
    connectionId = event['requestContext']['connectionId']
    create_sucess = db.create_connection(connectionId)
    return {}
