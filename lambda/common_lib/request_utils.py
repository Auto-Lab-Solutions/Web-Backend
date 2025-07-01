import json

def get_query_param(event, key, default=None):
    return (event.get('queryStringParameters') or {}).get(key, default)

def get_header(event, key, default=None):
    return (event.get('headers') or {}).get(key, default)

def get_path_param(event, key, default=None):
    return (event.get('pathParameters') or {}).get(key, default)

def get_body(event, default=None):
    body = event.get('body')
    if body:
        try:
            return json.loads(body)
        except (json.JSONDecodeError, TypeError):
            return default
    return default

def get_body_param(event, key, default=None):
    body = get_body(event, {})
    return body.get(key, default)

def get_authorizer_context(event):
    return event.get('requestContext', {}).get('authorizer', {})

def get_staff_user_email(event):
    context = get_authorizer_context(event)
    if context:
        return context.get('email', None)
    return None

def get_staff_user_roles(event):
    context = get_authorizer_context(event)
    if context:
        roles_text = context.get('staff_roles', None)
        if roles_text:
            return roles_text.split(',')
    return []
