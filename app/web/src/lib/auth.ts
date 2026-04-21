/** Cognito client-side authentication (SRP). */

import {
  AuthenticationDetails,
  CognitoUser,
  CognitoUserPool,
  CognitoUserSession,
} from 'amazon-cognito-identity-js';

import { getConfig } from './config';

let cachedPool: CognitoUserPool | null = null;

async function pool(): Promise<CognitoUserPool> {
  if (!cachedPool) {
    const { userPoolId, userPoolClientId } = await getConfig();
    cachedPool = new CognitoUserPool({ UserPoolId: userPoolId, ClientId: userPoolClientId });
  }
  return cachedPool;
}

export async function signIn(email: string, password: string): Promise<string> {
  const p = await pool();
  return new Promise((resolve, reject) => {
    const user = new CognitoUser({ Username: email, Pool: p });
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

export async function signOut(): Promise<void> {
  const current = (await pool()).getCurrentUser();
  current?.signOut();
  window.localStorage.removeItem('slideforge.accessToken');
}

export function isSignedIn(): boolean {
  return typeof window !== 'undefined' && !!window.localStorage.getItem('slideforge.accessToken');
}
