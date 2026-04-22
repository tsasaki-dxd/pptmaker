'use client';

import { usePathname, useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';

import { isSignedIn } from '../lib/auth';

const PUBLIC_PATHS = new Set(['/login', '/login/']);

/**
 * Client-side auth guard. If the user has no access token in localStorage
 * and the current path is not in PUBLIC_PATHS, send them to /login.
 * Otherwise render children.
 *
 * The static Next.js export has no server-side middleware, so this gate
 * runs in the browser after hydration. We render null until the first
 * check completes to avoid a one-frame flash of the dashboard for
 * unauthenticated visitors.
 */
export function AuthGuard({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const isPublic = PUBLIC_PATHS.has(pathname);
    if (!isSignedIn() && !isPublic) {
      router.replace('/login/');
      return;
    }
    setReady(true);
  }, [pathname, router]);

  if (!ready) return null;
  return <>{children}</>;
}
