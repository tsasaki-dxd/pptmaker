/** Cognito client-side authentication (SRP) with automatic token refresh.
 *
 * Token lifecycle:
 *   * Sign-in caches `idToken`, `accessToken`, `refreshToken` under the
 *     amazon-cognito-identity-js SDK's own localStorage keys
 *     (`CognitoIdentityServiceProvider.<clientId>.<username>.*`).
 *   * `getValidAccessToken()` is the single source of truth for "give
 *     me a token that's good right now" — it calls `getSession()` on
 *     the cached user, which the SDK transparently refreshes when the
 *     access token has expired but the refresh token (30-day default)
 *     is still valid.
 *   * `request()` in api.ts awaits this on every call so 1-hour token
 *     expiry never surfaces to the user as a 401 anymore.
 *
 * We also keep a sync mirror in `slideforge.accessToken` so
 * `isSignedIn()` / `isAdmin()` can stay synchronous (AuthGuard /
 * templates page rely on that), updated whenever
 * `getValidAccessToken()` runs.
 */

import {
  AuthenticationDetails,
  CognitoUser,
  CognitoUserPool,
  CognitoUserSession,
} from 'amazon-cognito-identity-js';

import { getConfig } from './config';

let cachedPool: CognitoUserPool | null = null;
const TOKEN_KEY = 'slideforge.accessToken';

async function pool(): Promise<CognitoUserPool> {
  if (!cachedPool) {
    const { userPoolId, userPoolClientId } = await getConfig();
    cachedPool = new CognitoUserPool({ UserPoolId: userPoolId, ClientId: userPoolClientId });
  }
  return cachedPool;
}

function cacheToken(token: string): void {
  if (typeof window !== 'undefined') {
    window.localStorage.setItem(TOKEN_KEY, token);
  }
}

function clearToken(): void {
  if (typeof window !== 'undefined') {
    window.localStorage.removeItem(TOKEN_KEY);
  }
}

export async function signIn(email: string, password: string): Promise<string> {
  const p = await pool();
  return new Promise((resolve, reject) => {
    const user = new CognitoUser({ Username: email, Pool: p });
    const details = new AuthenticationDetails({ Username: email, Password: password });
    user.authenticateUser(details, {
      onSuccess: (session: CognitoUserSession) => {
        const token = session.getAccessToken().getJwtToken();
        cacheToken(token);
        resolve(token);
      },
      onFailure: reject,
    });
  });
}

/**
 * Return an access token that's valid right now, refreshing via the
 * stored refresh token if necessary. Returns null if no user is signed
 * in or the refresh token itself has expired (in which case the caller
 * should surface a re-login).
 *
 * Internally uses `user.getSession()` from amazon-cognito-identity-js,
 * which checks token expiry against `clockDrift` and invokes the
 * Cognito InitiateAuth refresh flow when needed — that's the
 * idiomatic refresh path for this SDK.
 */
export async function getValidAccessToken(): Promise<string | null> {
  const p = await pool();
  const user = p.getCurrentUser();
  if (!user) {
    clearToken();
    return null;
  }
  return new Promise((resolve) => {
    user.getSession((err: Error | null, session: CognitoUserSession | null) => {
      if (err || !session || !session.isValid()) {
        // Refresh token expired or other auth error — drop the cached
        // token so isSignedIn() returns false and AuthGuard bounces
        // the user to /login on the next mount.
        user.signOut();
        clearToken();
        resolve(null);
        return;
      }
      const token = session.getAccessToken().getJwtToken();
      cacheToken(token);
      resolve(token);
    });
  });
}

export async function signOut(): Promise<void> {
  const current = (await pool()).getCurrentUser();
  current?.signOut();
  clearToken();
}

export function isSignedIn(): boolean {
  return typeof window !== 'undefined' && !!window.localStorage.getItem(TOKEN_KEY);
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
  const token = window.localStorage.getItem(TOKEN_KEY);
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
