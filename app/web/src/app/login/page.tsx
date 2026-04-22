'use client';

import { useRouter } from 'next/navigation';
import { useState } from 'react';

import { signIn } from '../../lib/auth';

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await signIn(email, password);
      router.replace('/');
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'ログインに失敗しました';
      setError(msg);
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="mx-auto mt-12 max-w-sm space-y-6 rounded border border-purple-lt/60 bg-white p-6">
      <h2 className="text-xl font-bold text-purple-dk">SlideForge ログイン</h2>
      <form onSubmit={onSubmit} className="space-y-4">
        <div>
          <label className="mb-1 block text-sm" htmlFor="email">
            メール
          </label>
          <input
            id="email"
            type="email"
            autoComplete="username"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full rounded border border-purple-lt/60 px-3 py-2"
          />
        </div>
        <div>
          <label className="mb-1 block text-sm" htmlFor="password">
            パスワード
          </label>
          <input
            id="password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full rounded border border-purple-lt/60 px-3 py-2"
          />
        </div>
        {error && <p className="text-sm text-red-600">{error}</p>}
        <button
          type="submit"
          disabled={loading}
          className="w-full rounded bg-purple px-4 py-2 font-bold text-white transition hover:bg-purple-dk disabled:opacity-50"
        >
          {loading ? '認証中…' : 'ログイン'}
        </button>
      </form>
    </section>
  );
}
