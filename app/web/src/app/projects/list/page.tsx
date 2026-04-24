'use client';

import { useCallback, useEffect, useState } from 'react';

import { api, type Project } from '@/lib/api';
import { LoadingOverlay } from '@/components/LoadingOverlay';

export default function ProjectsListPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // True until the first refresh() resolves. Separate from `busy`
  // (which tracks user-initiated operations) so the initial page
  // mount shows "読み込み中..." while the projects list is en route.
  const [listLoading, setListLoading] = useState(true);
  const [previewModal, setPreviewModal] = useState<{
    projectName: string;
    slides: { slide_index: number; url: string }[];
  } | null>(null);

  const refresh = useCallback(async () => {
    try {
      const p = await api.listProjects();
      setProjects(p);
      setError(null);
    } catch (e) {
      setError(`一覧取得失敗: ${String(e)}`);
    } finally {
      setListLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function handleDelete(p: Project) {
    if (!window.confirm(`「${p.name}」を削除しますか？レンダリング済みファイルも消えます。`)) return;
    setBusy(true);
    try {
      await api.deleteProject(p.id);
      await refresh();
    } catch (e) {
      setError(`削除失敗: ${String(e)}`);
    } finally {
      setBusy(false);
    }
  }

  async function handleDuplicate(p: Project) {
    setBusy(true);
    try {
      await api.duplicateProject(p.id);
      await refresh();
    } catch (e) {
      setError(`複製失敗: ${String(e)}`);
    } finally {
      setBusy(false);
    }
  }

  async function handlePreview(p: Project) {
    try {
      const res = await api.listPreviews(p.id);
      setPreviewModal({ projectName: p.name, slides: res.slides });
    } catch (e) {
      setError(`プレビュー取得失敗: ${String(e)}`);
    }
  }

  async function handleExport(p: Project, format: 'pptx' | 'pdf') {
    try {
      const res = await api.exportUrl(p.id, format);
      window.open(res.url, '_blank');
    } catch (e) {
      setError(`export 取得失敗: ${String(e)}`);
    }
  }

  return (
    <section className="space-y-4">
      <div className="flex items-baseline justify-between">
        <h2 className="text-2xl font-bold">プロジェクト一覧</h2>
        <a
          href="/projects/"
          className="rounded bg-purple px-3 py-1 text-sm text-white"
        >
          + 新規作成
        </a>
      </div>

      {error && (
        <div className="rounded border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </div>
      )}

      {projects.length === 0 ? (
        <p className="text-sm text-muted">まだありません</p>
      ) : (
        <ul className="space-y-2">
          {projects.map((p) => (
            <li
              key={p.id}
              className="space-y-2 rounded border border-purple-lt/60 bg-white p-3 text-sm"
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div>
                    <span className="font-medium text-dark">{p.name}</span>
                    <span className="ml-2 rounded bg-purple-lt/40 px-2 py-0.5 text-xs">
                      {p.status}
                    </span>
                  </div>
                  <div className="font-mono text-xs text-muted">{p.id}</div>
                </div>
                <div className="flex shrink-0 gap-1">
                  <button
                    onClick={() => handleDuplicate(p)}
                    disabled={busy}
                    className="rounded border border-purple-lt px-2 py-1 text-xs hover:bg-purple-lt/20 disabled:opacity-50"
                  >
                    複製
                  </button>
                  <button
                    onClick={() => handleDelete(p)}
                    disabled={busy}
                    className="rounded border border-purple-lt px-2 py-1 text-xs hover:bg-purple-lt/20 disabled:opacity-50"
                  >
                    削除
                  </button>
                </div>
              </div>
              <ProjectActionRow
                project={p}
                onPreview={() => handlePreview(p)}
                onExport={(fmt) => handleExport(p, fmt)}
              />
            </li>
          ))}
        </ul>
      )}

      {previewModal && (
        <PreviewModal
          projectName={previewModal.projectName}
          slides={previewModal.slides}
          onClose={() => setPreviewModal(null)}
        />
      )}

      <LoadingOverlay
        when={busy || listLoading}
        label={listLoading ? '読み込み中...' : '処理中...'}
      />
    </section>
  );
}

function ProjectActionRow(props: {
  project: Project;
  onPreview: () => void;
  onExport: (format: 'pptx' | 'pdf') => void;
}) {
  const { project, onPreview, onExport } = props;
  if (project.status === 'draft') return <div className="text-xs text-muted">未着手</div>;
  if (project.status === 'rendering') return <div className="text-xs text-muted">レンダリング中...</div>;
  if (project.status === 'failed') return <div className="text-xs text-red-600">レンダリング失敗</div>;
  if (project.status === 'partial') {
    return (
      <div className="space-y-1">
        <div className="text-xs text-amber-700">
          .pptx は出力済み (プレビュー / PDF はエラー)
        </div>
        <button
          onClick={() => onExport('pptx')}
          className="rounded border border-purple-lt px-2 py-1 text-xs hover:bg-purple-lt/20"
        >
          .pptx
        </button>
      </div>
    );
  }
  return (
    <div className="flex gap-2">
      <button
        onClick={onPreview}
        className="rounded border border-purple-lt px-2 py-1 text-xs hover:bg-purple-lt/20"
      >
        プレビュー
      </button>
      <button
        onClick={() => onExport('pptx')}
        className="rounded border border-purple-lt px-2 py-1 text-xs hover:bg-purple-lt/20"
      >
        .pptx
      </button>
      <button
        onClick={() => onExport('pdf')}
        className="rounded border border-purple-lt px-2 py-1 text-xs hover:bg-purple-lt/20"
      >
        .pdf
      </button>
    </div>
  );
}

function PreviewModal(props: {
  projectName: string;
  slides: { slide_index: number; url: string }[];
  onClose: () => void;
}) {
  const { projectName, slides, onClose } = props;
  return (
    <div
      className="fixed inset-0 z-40 flex items-start justify-center overflow-y-auto bg-black/60 p-6"
      onClick={onClose}
    >
      <div
        className="my-8 w-full max-w-5xl rounded bg-white p-4 shadow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-3 flex items-baseline justify-between">
          <div>
            <h3 className="text-base font-bold">{projectName} — プレビュー</h3>
            <div className="text-xs text-muted">全 {slides.length} 枚</div>
          </div>
          <button
            onClick={onClose}
            className="rounded border border-purple-lt px-3 py-1 text-sm hover:bg-purple-lt/20"
          >
            閉じる
          </button>
        </div>
        {slides.length === 0 ? (
          <p className="text-sm text-muted">プレビュー画像がありません。</p>
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {slides.map((s) => (
              <a
                key={s.slide_index}
                href={s.url}
                target="_blank"
                rel="noopener noreferrer"
                className="block overflow-hidden rounded border border-purple-lt/60"
              >
                <img
                  src={s.url}
                  alt={`slide ${s.slide_index}`}
                  className="w-full"
                  loading="lazy"
                />
                <div className="px-2 py-1 text-xs text-muted">#{s.slide_index}</div>
              </a>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
