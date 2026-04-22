'use client';

import { useCallback, useEffect, useState } from 'react';

import { api, type Project, type TemplateProfile } from '@/lib/api';

export default function ProjectsPage() {
  const [templates, setTemplates] = useState<TemplateProfile[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [name, setName] = useState('');
  const [templateId, setTemplateId] = useState('');
  const [intent, setIntent] = useState('');
  const [sections, setSections] = useState('課題認識, 提案概要, 体制, 費用, スケジュール');
  const [log, setLog] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);

  const push = (msg: string) => setLog((prev) => [...prev, msg]);

  const refresh = useCallback(async () => {
    try {
      const [t, p] = await Promise.all([api.listTemplates(), api.listProjects()]);
      setTemplates(t);
      setProjects(p);
      if (t.length && !templateId) setTemplateId(t[0].id);
    } catch (e) {
      push(`一覧取得失敗: ${String(e)}`);
    }
  }, [templateId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function handleFlow() {
    setBusy(true);
    try {
      push('プロジェクト作成...');
      const project = await api.createProject(name, templateId);
      push(`project_id = ${project.id}`);

      push('骨格生成中...（LLM 呼び出し、30 秒ほど）');
      const bp = await api.createBlueprint(
        project.id,
        intent,
        sections
          .split(',')
          .map((s) => s.trim())
          .filter(Boolean),
      );
      push(`blueprint_id = ${bp.id} (${bp.slides.length} slides, v${bp.version})`);

      push('レンダリング投入...');
      const r = await api.render(project.id);
      push(`job_id = ${r.job_id} status=${r.status}`);

      push('完了まで 30〜60 秒待って preview/export URL を取得してください');
      await refresh();
    } catch (e) {
      push(`失敗: ${String(e)}`);
    } finally {
      setBusy(false);
    }
  }

  async function handlePreview(projectId: string, slide = 1) {
    try {
      const res = await api.preview(projectId, slide);
      window.open(res.url, '_blank');
    } catch (e) {
      push(`プレビュー取得失敗: ${String(e)}`);
    }
  }

  async function handleExport(projectId: string, format: 'pptx' | 'pdf') {
    try {
      const res = await api.exportUrl(projectId, format);
      window.open(res.url, '_blank');
    } catch (e) {
      push(`export 取得失敗: ${String(e)}`);
    }
  }

  return (
    <section className="space-y-6">
      <div className="space-y-2">
        <h2 className="text-2xl font-bold">プロジェクト</h2>
        <p className="text-sm text-muted">
          テンプレートを選び、自然文で提案書の骨格を生成 → レンダリングします。
        </p>
      </div>

      <div className="space-y-3 rounded border border-purple-lt/60 bg-white p-4">
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          <label className="flex flex-col gap-1 text-sm">
            <span>プロジェクト名</span>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="例: A社向けDX提案"
              disabled={busy}
              className="rounded border border-purple-lt px-3 py-2"
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span>テンプレート</span>
            <select
              value={templateId}
              onChange={(e) => setTemplateId(e.target.value)}
              disabled={busy || templates.length === 0}
              className="rounded border border-purple-lt px-3 py-2"
            >
              {templates.length === 0 && <option value="">先にテンプレートを登録してください</option>}
              {templates.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </select>
          </label>
        </div>
        <label className="flex flex-col gap-1 text-sm">
          <span>ユーザー意図（自然文）</span>
          <textarea
            value={intent}
            onChange={(e) => setIntent(e.target.value)}
            disabled={busy}
            placeholder="例: A社向けのDX推進提案書。現状課題、提案概要、体制、費用、スケジュールを含む"
            className="min-h-[100px] rounded border border-purple-lt px-3 py-2"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span>必須セクション（カンマ区切り）</span>
          <input
            value={sections}
            onChange={(e) => setSections(e.target.value)}
            disabled={busy}
            className="rounded border border-purple-lt px-3 py-2"
          />
        </label>
        <button
          onClick={handleFlow}
          disabled={!name || !templateId || !intent || busy}
          className="rounded bg-purple px-4 py-2 text-white disabled:bg-muted"
        >
          {busy ? '実行中...' : '作成 → 骨格生成 → レンダリング'}
        </button>
        {log.length > 0 && (
          <pre className="whitespace-pre-wrap rounded bg-off p-3 text-xs">{log.join('\n')}</pre>
        )}
      </div>

      <div>
        <h3 className="mb-2 text-lg font-bold">プロジェクト一覧</h3>
        {projects.length === 0 ? (
          <p className="text-sm text-muted">まだありません</p>
        ) : (
          <ul className="space-y-2">
            {projects.map((p) => (
              <li
                key={p.id}
                className="space-y-2 rounded border border-purple-lt/60 bg-white p-3 text-sm"
              >
                <div>
                  <span className="font-medium text-dark">{p.name}</span>
                  <span className="ml-2 rounded bg-purple-lt/40 px-2 py-0.5 text-xs">{p.status}</span>
                </div>
                <div className="font-mono text-xs text-muted">{p.id}</div>
                <div className="flex gap-2">
                  <button
                    onClick={() => handlePreview(p.id, 1)}
                    className="rounded border border-purple-lt px-2 py-1 text-xs hover:bg-purple-lt/20"
                  >
                    プレビュー(1)
                  </button>
                  <button
                    onClick={() => handleExport(p.id, 'pptx')}
                    className="rounded border border-purple-lt px-2 py-1 text-xs hover:bg-purple-lt/20"
                  >
                    .pptx
                  </button>
                  <button
                    onClick={() => handleExport(p.id, 'pdf')}
                    className="rounded border border-purple-lt px-2 py-1 text-xs hover:bg-purple-lt/20"
                  >
                    .pdf
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
