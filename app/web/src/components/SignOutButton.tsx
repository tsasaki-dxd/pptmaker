'use client';

import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';

import { isSignedIn, signOut } from '../lib/auth';

export function SignOutButton() {
  const router = useRouter();
  const [show, setShow] = useState(false);

  useEffect(() => {
    setShow(isSignedIn());
  }, []);

  if (!show) return null;

  async function onClick() {
    await signOut();
    router.replace('/login/');
  }

  return (
    <button
      type="button"
      onClick={onClick}
      className="text-sm text-muted hover:text-purple"
    >
      サインアウト
    </button>
  );
}
