'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

import { api, type TemplateProfile } from '@/lib/api';
import { isAdmin } from '@/lib/auth';
import { LoadingOverlay } from '@/components/LoadingOverlay';

export default function TemplatesPage() {
  const [name, setName] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [status, setStatus] = useState<string>('');
  const [uploading, setUploading] = useState(false);
  const [list, setList] = useState<TemplateProfile[] | null>(null);
  // isAdmin() reads localStorage, which is only available after hydration.
  // Default to false on the server / first render, then flip on mount.
  const [admin, setAdmin] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const refresh = useCallback(async () => {
    try {
      const rows = await api.listTemplates();
      setList(rows);
    } catch (e) {
      setStatus(`一覧取得失敗: ${String(e)}`);
    }
  }, []);

  useEffect(() => {
    void refresh();
    setAdmin(isAdmin());
  }, [refresh]);

  async function handleCreate() {
    if (!name || !file) return;
    setUploading(true);
    setStatus('作成中...');
    try {
      const { template_id, upload_url } = await api.createTemplate(name);
      setStatus(`アップロード中: ${file.name} (${Math.round(file.size / 1024)} KB)...`);
      await api.uploadTemplateFile(upload_url, file);
      setStatus(`✅ 登録完了: template_id = ${template_id}`);
      setName('');
      setFile(null);
      if (fileInputRef.current) fileInputRef.current.value = '';
      await refresh();
    } catch (e) {
      setStatus(`失敗: ${String(e)}`);
    } finally {
      setUploading(false);
    }
  }

  async function handleDelete(t: TemplateProfile) {
    if (!window.confirm(`「${t.name}」を削除しますか？この操作は取り消せません。`)) return;
    try {
      await api.deleteTemplate(t.id);
      setStatus(`削除: ${t.name}`);
      await refresh();
    } catch (e) {
      setStatus(`削除失敗: ${String(e)}`);
    }
  }

  return (
    <section className="space-y-6">
      <div className="space-y-2">
        <h2 className="text-2xl font-bold">テンプレート登録</h2>
        <p className="text-sm text-muted">
          .pptx テンプレートをアップロードすると、以降のプロジェクトで再利用できます。
        </p>
      </div>

      <div className="space-y-3 rounded border border-purple-lt/60 bg-white p-4">
        <label className="block text-sm">
          <span className="mb-1 block">テンプレート名</span>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="例: DXデザインシステム_v1"
            disabled={uploading}
            className="w-full rounded border border-purple-lt px-3 py-2"
          />
        </label>
        <label className="block text-sm">
          <span className="mb-1 block">.pptx ファイル</span>
          <input
            ref={fileInputRef}
            type="file"
            accept=".pptx,application/vnd.openxmlformats-officedocument.presentationml.presentation"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            disabled={uploading}
            className="w-full text-sm"
          />
        </label>
        <button
          onClick={handleCreate}
          disabled={!name || !file || uploading}
          className="rounded bg-purple px-4 py-2 text-white disabled:bg-muted"
        >
          {uploading ? 'アップロード中...' : '作成 + アップロード'}
        </button>
        {status && <p className="text-sm">{status}</p>}
      </div>

      <div>
        <h3 className="mb-2 text-lg font-bold">登録済みテンプレート</h3>
        {list === null ? (
          <p className="text-sm text-muted">読み込み中…</p>
        ) : list.length === 0 ? (
          <p className="text-sm text-muted">まだありません</p>
        ) : (
          <ul className="space-y-2">
            {list.map((t) => (
              <li
                key={t.id}
                className="flex items-start justify-between gap-3 rounded border border-purple-lt/60 bg-white p-3 text-sm"
              >
                <div>
                  <div className="font-medium text-dark">{t.name}</div>
                  <div className="font-mono text-xs text-muted">{t.id}</div>
                  <div className="text-xs text-muted">{new Date(t.created_at).toLocaleString('ja-JP')}</div>
                </div>
                {admin && (
                  <button
                    onClick={() => handleDelete(t)}
                    className="shrink-0 rounded border border-purple-lt px-3 py-1 text-xs text-dark hover:bg-purple-lt/20"
                  >
                    削除
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>

      <LoadingOverlay
        when={uploading || list === null}
        label={uploading ? (status || 'アップロード中...') : '読み込み中...'}
      />
    </section>
  );
}
