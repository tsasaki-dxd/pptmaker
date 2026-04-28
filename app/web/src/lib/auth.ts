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

/**
 * Read `cognito:groups` from the cached access token. Used purely for UI
 * gating (e.g. hiding the template delete button) — the backend still
 * enforces admin-only operations on its side.
 *
 * No signature verification: the token came from our own login flow and
 * the client can't grant itself privileges since the API re-validates
 * the JWT against the Cognito JWKS.
 */
function decodeGroups(): string[] {
  if (typeof window === 'undefined') return [];
  const token = window.localStorage.getItem('slideforge.accessToken');
  if (!token) return [];
  const parts = token.split('.');
  if (parts.length !== 3) return [];
  try {
    const payload = JSON.parse(
      atob(parts[1].replace(/-/g, '+').replace(/_/g, '/')),
    ) as { 'cognito:groups'?: string[] };
    return payload['cognito:groups'] ?? [];
  } catch {
    return [];
  }
}

export function isAdmin(): boolean {
  return decodeGroups().includes('admin');
}
