exports.onExecutePostLogin = async (event, api) => {
  const userEmail = event.user.email;
  const emailVerified = event.user.email_verified;
  const apiGwEndpoint = 'https://api-dev.autolabsolutions.com';
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
      const errorText = await response.text();
      console.error('Lambda call failed:', response.status, errorText);
      api.access.deny('Access denied: Unable to verify user role.');
      return;
    }

    // Check if the response is JSON before parsing
    const contentType = response.headers.get('content-type');
    if (!contentType || !contentType.includes('application/json')) {
      const responseText = await response.text();
      console.error('Invalid response format. Expected JSON, got:', contentType);
      console.error('Response:', responseText.substring(0, 200));
      api.access.deny('Access denied: Invalid response format from role verification service.');
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
