import type { Metadata } from 'next';
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
            <h1 className="text-lg font-bold text-purple-dk">SlideForge</h1>
            <nav className="flex gap-4 text-sm">
              <a href="/templates/">テンプレート</a>
              <a href="/projects/">プロジェクト</a>
            </nav>
          </div>
        </header>
        <main className="mx-auto max-w-6xl px-6 py-8">{children}</main>
      </body>
    </html>
  );
}
