exports.onExecutePostLogin = async (event, api) => {
  const userEmail = event.user.email;
  const emailVerified = event.user.email_verified;
  const apiGwEndpoint = process.env.API_GATEWAY_ENDPOINT || 'REPLACE_WITH_YOUR_API_ENDPOINT';
  const lambdaEndpoint = apiGwEndpoint + '/get-staff-roles';
  const sharedSecret = process.env.SHARED_KEY || 'REPLACE_WITH_SECURE_SECRET';

  if (!userEmail || !emailVerified) {
    api.access.deny('Access denied: A verified email is required to use this application.');
    return;
  }

  try {
    const response = await fetch(lambdaEndpoint + '?email=' + userEmail, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
        'shared-api-key': sharedSecret,
      }
    });

    if (!response.ok) {
      console.log('Lambda call failed:', await response.text());
      api.access.deny('Access denied: Unable to verify user role.');
      return;
    }

    const data = await response.json();
    const roles = data.roles;

    if (!roles) {
      api.access.deny('Access denied: No role assigned to this email.');
      return;
    }

    api.idToken.setCustomClaim('is_staff', true);
    api.idToken.setCustomClaim('staff_roles', roles);
    
    api.accessToken.setCustomClaim('is_staff', true);
    api.accessToken.setCustomClaim('staff_roles', roles);
    api.accessToken.setCustomClaim('email', userEmail);
    api.accessToken.setCustomClaim('email_verified', emailVerified);

  } catch (err) {
    console.error('Lambda request error:', err);
    api.access.deny('Access denied: Internal error while resolving role.');
  }
};
