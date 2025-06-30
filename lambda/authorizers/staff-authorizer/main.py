import auth_utils as auth

def lambda_handler(event, context):
    # Extract the resource ARN from the event (commonly event['methodArn'])
    resource = event.get('methodArn', '*')

    # Extract the token
    token = auth.extract_token(event)
    if not token:
        return auth.generate_policy(
            principal_id='unauthorized',
            effect='Deny',
            resource=resource,
            context={'errorMessage': 'Missing token'}
        )

    try:
        # Verify the JWT
        decoded = auth.verify_jwt(token)
        email = decoded.get('email')
        email_verified = decoded.get('email_verified', False)
        is_staff = decoded.get('is_staff', False)

        # Check email and verification
        if not email or not email_verified:
            return auth.generate_policy(
                principal_id='unauthorized',
                effect='Deny',
                resource=resource,
                context={'errorMessage': 'Unverified email'}
            )
        # Check if staff
        if not is_staff:
            return auth.generate_policy(
                principal_id='unauthorized',
                effect='Deny',
                resource=resource,
                context={'errorMessage': 'Not a staff member'}
            )

        # Allow access
        return auth.generate_policy(
            principal_id=decoded['sub'],
            effect='Allow',
            resource=resource,
            context={
                'email': email,
                'is_staff': is_staff
            }
        )

    except Exception as e:
        print('Token verification failed:', str(e))
        return auth.generate_policy(
            principal_id='unauthorized',
            effect='Deny',
            resource=resource,
            context={'errorMessage': 'Invalid token'}
        )
