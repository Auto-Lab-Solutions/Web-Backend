exports.onExecutePostLogin = async (event, api) => {
  const userEmail = event.user.email;
  const emailVerified = event.user.email_verified;
  const apiGwEndpoint = 'https://91maaqr173.execute-api.ap-southeast-2.amazonaws.com/production';
  const lambdaEndpoint = apiGwEndpoint + '/get-staff-roles';
  const sharedSecret = 'dsa2GJN4i23SOml35hWa2p';

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

    api.idToken.setCustomClaim('staff_roles', roles);
    api.idToken.setCustomClaim('is_staff', true);
    api.accessToken.setCustomClaim('staff_roles', roles);
    api.accessToken.setCustomClaim('is_staff', true);

  } catch (err) {
    console.error('Lambda request error:', err);
    api.access.deny('Access denied: Internal error while resolving role.');
  }
};
