import role_authorizer

def lambda_handler(event, context):
    return role_authorizer.authorize(event, 'ADMIN')
