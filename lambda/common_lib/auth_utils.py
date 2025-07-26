import json, jwt, os
import urllib.request
from jwt import PyJWKClient

AUTH0_DOMAIN = os.environ.get('AUTH0_DOMAIN')
AUTH0_AUDIENCE = os.environ.get('AUTH0_AUDIENCE')
AUTH0_ISSUER = f'https://{AUTH0_DOMAIN}/'
JWKS_URL = f'{AUTH0_ISSUER}.well-known/jwks.json'

def extract_token(event):    
    headers = event.get('headers', {})
    auth = headers.get('authorization') or headers.get('Authorization')
    if not auth or not auth.startswith('Bearer '):
        return None
    return auth.split(' ')[1]

def verify_jwt(token):
    if not token:
        raise Exception('Unauthorized: No token provided')

    jwks_client = PyJWKClient(JWKS_URL)

    try:
        key = jwks_client.get_signing_key_from_jwt(token)
        decoded = jwt.decode(
            token,
            key.key,
            algorithms=['RS256'],
            audience=AUTH0_AUDIENCE,
            issuer=AUTH0_ISSUER
        )
        return decoded
    except jwt.ExpiredSignatureError:
        raise Exception('Unauthorized: Token has expired')
    except jwt.InvalidTokenError as e:
        raise Exception(f'Unauthorized: Invalid token - {str(e)}')

def generate_policy(principal_id, effect, resource, context=None):
    policy = {
        'principalId': principal_id,
        'policyDocument': {
            'Version': '2012-10-17',
            'Statement': [{
                'Action': 'execute-api:Invoke',
                'Effect': effect,
                'Resource': resource
            }]
        }
    }
    if context:
        policy['context'] = context
    return policy

def get_user_email(token):
    if not token:
        print("No token provided.")
        return None
    
    jwks_client = PyJWKClient(JWKS_URL)
    
    try:
        key = jwks_client.get_signing_key_from_jwt(token)
        decoded = jwt.decode(
            token,
            key.key,
            algorithms=['RS256'],
            audience=AUTH0_AUDIENCE,
            issuer=AUTH0_ISSUER
        )
        return decoded.get('email')
    except jwt.ExpiredSignatureError:
        print("Token has expired.")
        return None
    except jwt.InvalidTokenError as e:
        print(f"Invalid token: {str(e)}")
        return None
    except Exception as e:
        print(f"Error decoding token: {str(e)}")
        return None

def get_user_id(event):
    """Extract user ID from JWT token in the event"""
    token = extract_token(event)
    if not token:
        return None
    
    jwks_client = PyJWKClient(JWKS_URL)
    
    try:
        key = jwks_client.get_signing_key_from_jwt(token)
        decoded = jwt.decode(
            token,
            key.key,
            algorithms=['RS256'],
            audience=AUTH0_AUDIENCE,
            issuer=AUTH0_ISSUER
        )
        return decoded.get('sub')  # 'sub' is the user ID claim in JWT
    except jwt.ExpiredSignatureError:
        print("Token has expired.")
        return None
    except jwt.InvalidTokenError as e:
        print(f"Invalid token: {str(e)}")
        return None
    except Exception as e:
        print(f"Error decoding token: {str(e)}")
        return None
