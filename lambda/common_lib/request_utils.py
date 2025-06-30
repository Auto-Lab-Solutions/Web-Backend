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
