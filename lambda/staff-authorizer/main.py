import os
import sys

# Add common_lib to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'common_lib'))

import auth_utils as auth
import business_logic_utils as biz

def lambda_handler(event, context):
    """
    Staff authorizer with enhanced error handling and logging
    """
    try:
        resource = event.get('methodArn', '*')

        # Extract the token
        token = auth.extract_token(event)
        if not token:
            print("Missing token in authorization request")
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
            staff_roles = decoded.get('staff_roles', [])

            # Check email and verification
            if not email or not email_verified:
                print(f"Unverified email for user: {email}")
                return auth.generate_policy(
                    principal_id='unauthorized',
                    effect='Deny',
                    resource=resource,
                    context={'errorMessage': 'Unverified email'}
                )
            
            # Check if staff
            if not is_staff:
                print(f"Non-staff user attempted access: {email}")
                return auth.generate_policy(
                    principal_id='unauthorized',
                    effect='Deny',
                    resource=resource,
                    context={'errorMessage': 'Not a staff member'}
                )

            # Check if staff has staff roles
            if not staff_roles:
                print(f"Staff user with no roles attempted access: {email}")
                return auth.generate_policy(
                    principal_id='unauthorized',
                    effect='Deny',
                    resource=resource,
                    context={'errorMessage': 'Staff does not have any staff roles'}
                )

            # Allow access
            print(f"Staff access granted for: {email} with roles: {staff_roles}")
            return auth.generate_policy(
                principal_id=decoded['sub'],
                effect='Allow',
                resource=resource,
                context={
                    'email': email,
                    'is_staff': is_staff,
                    'staff_roles': ','.join(staff_roles)
                }
            )

        except Exception as e:
            print(f'Token verification failed: {str(e)}')
            return auth.generate_policy(
                principal_id='unauthorized',
                effect='Deny',
                resource=resource,
                context={'errorMessage': 'Invalid token'}
            )
            
    except Exception as e:
        print(f'Critical error in staff authorizer: {str(e)}')
        # In case of critical error, deny access
        return auth.generate_policy(
            principal_id='error',
            effect='Deny',
            resource=event.get('methodArn', '*'),
            context={'errorMessage': 'Authorization error'}
        )
