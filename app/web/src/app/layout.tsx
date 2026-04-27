import type { Metadata } from 'next';

import { AuthGuard } from '../components/AuthGuard';
import { SignOutButton } from '../components/SignOutButton';
import '../styles/globals.css';

export const metadata: Metadata = {
  title: 'SlideForge',
  description: 'Template-driven AI slide generator',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ja">
      <body>
        <header className="border-b border-purple-lt/50 bg-white px-6 py-3">
          <div className="mx-auto flex max-w-6xl items-center justify-between">
            <a href="/" className="text-lg font-bold text-purple-dk">
              SlideForge
            </a>
            <nav className="flex items-center gap-4 text-sm">
              <a href="/templates/">テンプレート</a>
              <a href="/projects/">新規作成</a>
              <a href="/projects/list/">プロジェクト一覧</a>
              <a href="/samples/">サンプル</a>
              <SignOutButton />
            </nav>
          </div>
        </header>
        <main className="mx-auto max-w-6xl px-6 py-8">
          <AuthGuard>{children}</AuthGuard>
        </main>
      </body>
    </html>
  );
}
