'use client';

import { useState } from 'react';
import { api } from '@/lib/api';

export default function TemplatesPage() {
  const [name, setName] = useState('');
  const [status, setStatus] = useState('');

  async function handleCreate() {
    setStatus('作成中...');
    try {
      const { upload_url } = await api.createTemplate(name);
      setStatus(`アップロード URL を取得しました。ファイルを PUT してください: ${upload_url.slice(0, 60)}...`);
    } catch (e) {
      setStatus(`失敗: ${String(e)}`);
    }
  }

  return (
    <section className="space-y-4">
      <h2 className="text-2xl font-bold">テンプレート登録</h2>
      <p className="text-sm text-muted">
        .pptx テンプレートをアップロードして、レイアウト自動分類＆プロファイル化します。
      </p>
      <div className="flex gap-2">
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="テンプレート名"
          className="flex-1 rounded border border-purple-lt px-3 py-2"
        />
        <button
          onClick={handleCreate}
          disabled={!name}
          className="rounded bg-purple px-4 py-2 text-white disabled:bg-muted"
        >
          作成
        </button>
      </div>
      {status && <p className="text-sm">{status}</p>}
    </section>
  );
}
