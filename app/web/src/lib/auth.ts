/** Cognito client-side authentication (SRP). */

import {
  AuthenticationDetails,
  CognitoUser,
  CognitoUserPool,
  CognitoUserSession,
} from 'amazon-cognito-identity-js';

const poolId = process.env.NEXT_PUBLIC_COGNITO_USER_POOL_ID ?? '';
const clientId = process.env.NEXT_PUBLIC_COGNITO_CLIENT_ID ?? '';

let cachedPool: CognitoUserPool | null = null;
function pool(): CognitoUserPool {
  if (!cachedPool) cachedPool = new CognitoUserPool({ UserPoolId: poolId, ClientId: clientId });
  return cachedPool;
}

export async function signIn(email: string, password: string): Promise<string> {
  return new Promise((resolve, reject) => {
    const user = new CognitoUser({ Username: email, Pool: pool() });
    const details = new AuthenticationDetails({ Username: email, Password: password });
    user.authenticateUser(details, {
      onSuccess: (session: CognitoUserSession) => {
        const token = session.getAccessToken().getJwtToken();
        window.localStorage.setItem('slideforge.accessToken', token);
        resolve(token);
      },
      onFailure: reject,
    });
  });
}

export function signOut(): void {
  const current = pool().getCurrentUser();
  current?.signOut();
  window.localStorage.removeItem('slideforge.accessToken');
}

export function isSignedIn(): boolean {
  return typeof window !== 'undefined' && !!window.localStorage.getItem('slideforge.accessToken');
}
