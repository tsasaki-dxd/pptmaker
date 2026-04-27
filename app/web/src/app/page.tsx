'use client';

import Link from 'next/link';

export default function HomePage() {
  return (
    <section className="space-y-6">
      <h2 className="text-2xl font-bold">ダッシュボード</h2>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <Card href="/templates/" title="テンプレート" body="コーポレートテンプレートをアップロードして管理" />
        <Card href="/projects/" title="プロジェクト" body="新規作成・骨格生成・修正・エクスポート" />
        <Card href="/projects/" title="提案書を書く" body="自然言語から骨格を生成" />
        <Card href="/samples/" title="サンプル集" body="図種 × 参考プロンプト別のレンダリング例を一覧" />
      </div>
    </section>
  );
}

function Card({ href, title, body }: { href: string; title: string; body: string }) {
  return (
    <Link
      href={href}
      className="block rounded border border-purple-lt/60 bg-white p-4 transition hover:border-purple hover:shadow"
    >
      <div className="text-base font-bold text-purple-dk">{title}</div>
      <p className="mt-2 text-sm text-muted">{body}</p>
    </Link>
  );
}
