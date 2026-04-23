'use client';

import { useCallback, useEffect, useState } from 'react';

import {
  api,
  type Blueprint,
  type Project,
  type SlideSpec,
  type SlideTemplateMapping,
  type TemplateProfile,
} from '@/lib/api';

type Step = 'input' | 'reviewing' | 'rendering' | 'done';

export default function ProjectsPage() {
  const [templates, setTemplates] = useState<TemplateProfile[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);

  // Step 1 form
  const [name, setName] = useState('');
  const [templateId, setTemplateId] = useState('');
  const [intent, setIntent] = useState('');
  const [sections, setSections] = useState('課題認識, 提案概要, 体制, 費用, スケジュール');

  // Wizard state
  const [step, setStep] = useState<Step>('input');
  const [project, setProject] = useState<Project | null>(null);
  const [blueprint, setBlueprint] = useState<Blueprint | null>(null);
  const [selectedTemplate, setSelectedTemplate] = useState<TemplateProfile | null>(null);
  const [revisionText, setRevisionText] = useState('');
  const [busy, setBusy] = useState(false);
  const [log, setLog] = useState<string[]>([]);

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

  // ────────────────────────────────────────────────────────────────────
  // Step 1 → 2: create project + generate blueprint
  // ────────────────────────────────────────────────────────────────────
  async function handleGenerateBlueprint() {
    setBusy(true);
    setLog([]);
    try {
      // Lazy-fetch the chosen template's slide count so the dropdowns
      // in step 2 know how many options to show. First request triggers
      // the server-side .pptx scan.
      push('テンプレート解析...');
      const t = await api.getTemplate(templateId);
      setSelectedTemplate(t);
      if (!t.template_slide_count) {
        push(
          '警告: テンプレのスライド数を取得できませんでした (デフォルトのマッピングが効きません)',
        );
      }

      push('プロジェクト作成...');
      const p = await api.createProject(name, templateId);
      setProject(p);
      push(`project_id = ${p.id}`);

      push('骨格生成ジョブ投入...');
      const job = await api.createBlueprint(
        p.id,
        intent,
        sections.split(',').map((s) => s.trim()).filter(Boolean),
      );
      const startedAt = Date.now();
      push(`job_id = ${job.job_id} (ポーリング中...)`);
      for (let i = 0; i < 90; i++) {
        const j = await api.getBlueprintJob(p.id, job.job_id);
        if (j.status === 'complete') {
          push(`骨格生成完了: blueprint_id = ${j.blueprint_id}`);
          break;
        }
        if (j.status === 'failed') {
          throw new Error(`骨格生成失敗: ${j.error ?? '(詳細不明)'}`);
        }
        if (i > 0 && i % 5 === 0) {
          const elapsed = Math.round((Date.now() - startedAt) / 1000);
          setLog((prev) => [...prev.slice(0, -1), `骨格生成 polling... (${elapsed}s / 180s)`]);
        }
        await new Promise((r) => setTimeout(r, 2000));
      }

      // Pull the blueprint to display in step 2.
      const bp = await api.getBlueprint(p.id);
      setBlueprint(bp);
      setStep('reviewing');
    } catch (e) {
      push(`失敗: ${String(e)}`);
      await refresh();
    } finally {
      setBusy(false);
    }
  }

  // ────────────────────────────────────────────────────────────────────
  // Step 2 actions
  // ────────────────────────────────────────────────────────────────────
  async function handleSlideMappingChange(slideIndex: number, value: number) {
    if (!project || !blueprint) return;
    const mappings: SlideTemplateMapping[] = [
      { index: slideIndex, template_slide_index: value },
    ];
    try {
      const updated = await api.patchBlueprintMapping(project.id, mappings);
      setBlueprint(updated);
    } catch (e) {
      push(`マッピング更新失敗: ${String(e)}`);
    }
  }

  async function handleRevise() {
    if (!project || !revisionText.trim()) return;
    setBusy(true);
    try {
      push(`修正指示送信: "${revisionText}"`);
      await api.revise(project.id, revisionText);
      const bp = await api.getBlueprint(project.id);
      setBlueprint(bp);
      setRevisionText('');
      push(`修正完了: v${bp.version}`);
    } catch (e) {
      push(`修正失敗: ${String(e)}`);
    } finally {
      setBusy(false);
    }
  }

  // ────────────────────────────────────────────────────────────────────
  // Step 2 → 3: render
  // ────────────────────────────────────────────────────────────────────
  async function handleRender() {
    if (!project) return;
    setBusy(true);
    setStep('rendering');
    try {
      push('レンダリング投入...');
      const r = await api.render(project.id);
      push(`job_id = ${r.job_id} status=${r.status}`);

      push('レンダリング polling...');
      const status = await pollRenderComplete(project.id);
      if (status === 'failed') {
        throw new Error('レンダリング失敗 (詳細は CloudWatch ログ参照)');
      }
      push('完了!');
      setStep('done');
      await refresh();
    } catch (e) {
      push(`失敗: ${String(e)}`);
      setStep('reviewing'); // back to review so user can retry
      await refresh();
    } finally {
      setBusy(false);
    }
  }

  async function pollRenderComplete(projectId: string): Promise<'complete' | 'failed'> {
    const intervalMs = 3000;
    const maxAttempts = 100;
    const startedAt = Date.now();
    for (let i = 0; i < maxAttempts; i++) {
      const p = await api.getProject(projectId);
      const elapsed = Math.round((Date.now() - startedAt) / 1000);
      if (p.status === 'complete' || p.status === 'failed') return p.status;
      if (i > 0 && i % 5 === 0) {
        setLog((prev) => [
          ...prev.slice(0, -1),
          `レンダリング polling... (${elapsed}s / 300s, status=${p.status})`,
        ]);
      }
      await new Promise((r) => setTimeout(r, intervalMs));
    }
    throw new Error('レンダリングがタイムアウトしました（5分経過）');
  }

  function handleStartOver() {
    setStep('input');
    setProject(null);
    setBlueprint(null);
    setRevisionText('');
    setLog([]);
    setName('');
    setIntent('');
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

  async function handleDeleteProject(p: Project) {
    if (!window.confirm(`「${p.name}」を削除しますか？レンダリング済みファイルも消えます。`)) return;
    try {
      await api.deleteProject(p.id);
      push(`削除: ${p.name}`);
      await refresh();
    } catch (e) {
      push(`削除失敗: ${String(e)}`);
    }
  }

  async function handleDuplicateProject(p: Project) {
    setBusy(true);
    setLog([]);
    try {
      push(`複製中: ${p.name}`);
      const copied = await api.duplicateProject(p.id);
      push(`複製完了: ${copied.id}`);

      // Land in Step 2 with the copied blueprint pre-loaded so the
      // user can keep editing right where they'd want to.
      const t = await api.getTemplate(copied.template_id);
      setSelectedTemplate(t);
      setProject(copied);
      const bp = await api.getBlueprint(copied.id);
      setBlueprint(bp);
      setStep('reviewing');
      await refresh();
    } catch (e) {
      push(`複製失敗: ${String(e)}`);
    } finally {
      setBusy(false);
    }
  }

  // ────────────────────────────────────────────────────────────────────
  // Render
  // ────────────────────────────────────────────────────────────────────
  return (
    <section className="space-y-6">
      <div className="space-y-2">
        <h2 className="text-2xl font-bold">プロジェクト</h2>
        <p className="text-sm text-muted">
          テンプレートを選び、自然文で骨格を生成 → レビュー / 修正 → レンダリングの 3 ステップ。
        </p>
      </div>

      {step === 'input' && (
        <Step1Input
          name={name}
          setName={setName}
          templates={templates}
          templateId={templateId}
          setTemplateId={setTemplateId}
          intent={intent}
          setIntent={setIntent}
          sections={sections}
          setSections={setSections}
          busy={busy}
          onSubmit={handleGenerateBlueprint}
        />
      )}

      {step === 'reviewing' && blueprint && (
        <Step2Review
          blueprint={blueprint}
          template={selectedTemplate}
          onMappingChange={handleSlideMappingChange}
          revisionText={revisionText}
          setRevisionText={setRevisionText}
          onRevise={handleRevise}
          onRender={handleRender}
          onCancel={handleStartOver}
          busy={busy}
        />
      )}

      {(step === 'rendering' || step === 'done') && (
        <Step3Result step={step} project={project} onStartOver={handleStartOver} />
      )}

      {log.length > 0 && (
        <pre className="whitespace-pre-wrap rounded bg-off p-3 text-xs">{log.join('\n')}</pre>
      )}

      <ProjectsList
        projects={projects}
        onPreview={handlePreview}
        onExport={handleExport}
        onDuplicate={handleDuplicateProject}
        onDelete={handleDeleteProject}
        busy={busy}
      />
    </section>
  );
}

// ──────────────────────────────────────────────────────────────────────
// Step 1: input form
// ──────────────────────────────────────────────────────────────────────
function Step1Input(props: {
  name: string;
  setName: (s: string) => void;
  templates: TemplateProfile[];
  templateId: string;
  setTemplateId: (s: string) => void;
  intent: string;
  setIntent: (s: string) => void;
  sections: string;
  setSections: (s: string) => void;
  busy: boolean;
  onSubmit: () => void;
}) {
  const { name, setName, templates, templateId, setTemplateId, intent, setIntent, sections, setSections, busy, onSubmit } = props;
  return (
    <div className="space-y-3 rounded border border-purple-lt/60 bg-white p-4">
      <h3 className="text-sm font-bold text-muted">Step 1: 入力</h3>
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
        onClick={onSubmit}
        disabled={!name || !templateId || !intent || busy}
        className="rounded bg-purple px-4 py-2 text-white disabled:bg-muted"
      >
        {busy ? '実行中...' : '骨格を生成'}
      </button>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────
// Step 2: blueprint review
// ──────────────────────────────────────────────────────────────────────
function Step2Review(props: {
  blueprint: Blueprint;
  template: TemplateProfile | null;
  onMappingChange: (slideIndex: number, value: number) => void;
  revisionText: string;
  setRevisionText: (s: string) => void;
  onRevise: () => void;
  onRender: () => void;
  onCancel: () => void;
  busy: boolean;
}) {
  const { blueprint, template, onMappingChange, revisionText, setRevisionText, onRevise, onRender, onCancel, busy } = props;
  const templatePages = template?.template_slide_count ?? 0;

  return (
    <div className="space-y-4 rounded border border-purple-lt/60 bg-white p-4">
      <div className="flex items-baseline justify-between">
        <h3 className="text-sm font-bold text-muted">Step 2: 骨格レビュー</h3>
        <span className="text-xs text-muted">
          v{blueprint.version} / {blueprint.slides.length} slides / template {templatePages}p
        </span>
      </div>
      <h4 className="text-base font-bold">{blueprint.title}</h4>

      <div className="overflow-x-auto">
        <table className="min-w-full text-xs">
          <thead className="text-left text-muted">
            <tr>
              <th className="px-2 py-1">#</th>
              <th className="px-2 py-1">layout</th>
              <th className="px-2 py-1">figure</th>
              <th className="px-2 py-1">主要内容</th>
              <th className="px-2 py-1">テンプレページ</th>
            </tr>
          </thead>
          <tbody>
            {blueprint.slides.map((s) => (
              <SlideRow
                key={s.index}
                slide={s}
                templatePages={templatePages}
                onMappingChange={onMappingChange}
                disabled={busy}
              />
            ))}
          </tbody>
        </table>
      </div>

      <div className="space-y-2 rounded border border-purple-lt/60 p-3">
        <label className="flex flex-col gap-1 text-sm">
          <span>修正指示（LLMで全体を書き換え）</span>
          <textarea
            value={revisionText}
            onChange={(e) => setRevisionText(e.target.value)}
            placeholder="例: 「費用」スライドを2枚に分けて、内訳を表で見せて"
            disabled={busy}
            className="min-h-[60px] rounded border border-purple-lt px-3 py-2"
          />
        </label>
        <button
          onClick={onRevise}
          disabled={!revisionText.trim() || busy}
          className="rounded border border-purple px-3 py-1 text-sm text-purple disabled:opacity-50"
        >
          {busy ? '実行中...' : '修正'}
        </button>
      </div>

      <div className="flex gap-2">
        <button
          onClick={onRender}
          disabled={busy}
          className="rounded bg-purple px-4 py-2 text-white disabled:bg-muted"
        >
          これでレンダリング
        </button>
        <button
          onClick={onCancel}
          disabled={busy}
          className="rounded border border-purple-lt px-4 py-2 text-sm text-dark hover:bg-purple-lt/20 disabled:opacity-50"
        >
          キャンセル (新規)
        </button>
      </div>
    </div>
  );
}

function SlideRow(props: {
  slide: SlideSpec;
  templatePages: number;
  onMappingChange: (slideIndex: number, value: number) => void;
  disabled: boolean;
}) {
  const { slide, templatePages, onMappingChange, disabled } = props;
  const summary = summarizeContent(slide);
  const current =
    slide.template_slide_index ??
    (templatePages > 0 ? ((slide.index - 1) % templatePages) + 1 : 1);
  return (
    <tr className="border-t border-purple-lt/40">
      <td className="px-2 py-1 align-top font-mono">{slide.index}</td>
      <td className="px-2 py-1 align-top">{slide.layout}</td>
      <td className="px-2 py-1 align-top">{slide.figure_type ?? '-'}</td>
      <td className="px-2 py-1 align-top">{summary}</td>
      <td className="px-2 py-1 align-top">
        {templatePages > 0 ? (
          <select
            value={current}
            onChange={(e) => onMappingChange(slide.index, Number(e.target.value))}
            disabled={disabled}
            className="rounded border border-purple-lt px-1 py-0.5 text-xs"
          >
            {Array.from({ length: templatePages }, (_, i) => i + 1).map((n) => (
              <option key={n} value={n}>
                #{n}
              </option>
            ))}
          </select>
        ) : (
          <span className="text-muted">N/A</span>
        )}
      </td>
    </tr>
  );
}

function summarizeContent(slide: SlideSpec): string {
  const c = slide.content as Record<string, unknown>;
  const title = c.title as string | undefined;
  if (title) return title;
  const items = c.items as unknown[] | undefined;
  if (Array.isArray(items) && items.length > 0) {
    const first = typeof items[0] === 'string' ? items[0] : JSON.stringify(items[0]);
    return `${first}${items.length > 1 ? ` (+${items.length - 1})` : ''}`;
  }
  const value = c.value as string | undefined;
  if (value) return `${value} ${(c.label as string) ?? ''}`.trim();
  return '(no preview)';
}

// ──────────────────────────────────────────────────────────────────────
// Step 3: render result
// ──────────────────────────────────────────────────────────────────────
function Step3Result(props: { step: Step; project: Project | null; onStartOver: () => void }) {
  const { step, project, onStartOver } = props;
  return (
    <div className="space-y-3 rounded border border-purple-lt/60 bg-white p-4">
      <h3 className="text-sm font-bold text-muted">Step 3: レンダリング</h3>
      {step === 'rendering' && <p className="text-sm">レンダリング中...</p>}
      {step === 'done' && project && (
        <>
          <p className="text-sm">完了しました。下のプロジェクト一覧から preview / export してください。</p>
          <button
            onClick={onStartOver}
            className="rounded bg-purple px-4 py-2 text-white"
          >
            新規プロジェクト
          </button>
        </>
      )}
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────
// Persistent project list
// ──────────────────────────────────────────────────────────────────────
function ProjectsList(props: {
  projects: Project[];
  onPreview: (id: string, slide: number) => void;
  onExport: (id: string, format: 'pptx' | 'pdf') => void;
  onDuplicate: (p: Project) => void;
  onDelete: (p: Project) => void;
  busy: boolean;
}) {
  const { projects, onPreview, onExport, onDuplicate, onDelete, busy } = props;
  return (
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
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div>
                    <span className="font-medium text-dark">{p.name}</span>
                    <span className="ml-2 rounded bg-purple-lt/40 px-2 py-0.5 text-xs">{p.status}</span>
                  </div>
                  <div className="font-mono text-xs text-muted">{p.id}</div>
                </div>
                <div className="flex shrink-0 gap-1">
                  <button
                    onClick={() => onDuplicate(p)}
                    disabled={busy}
                    className="rounded border border-purple-lt px-2 py-1 text-xs hover:bg-purple-lt/20 disabled:opacity-50"
                  >
                    複製
                  </button>
                  <button
                    onClick={() => onDelete(p)}
                    disabled={busy}
                    className="rounded border border-purple-lt px-2 py-1 text-xs hover:bg-purple-lt/20 disabled:opacity-50"
                  >
                    削除
                  </button>
                </div>
              </div>
              {p.status === 'draft' ? (
                <div className="text-xs text-muted">未着手</div>
              ) : p.status === 'rendering' ? (
                <div className="text-xs text-muted">レンダリング中...</div>
              ) : p.status === 'failed' ? (
                <div className="text-xs text-red-600">レンダリング失敗</div>
              ) : (
                <div className="flex gap-2">
                  <button
                    onClick={() => onPreview(p.id, 1)}
                    className="rounded border border-purple-lt px-2 py-1 text-xs hover:bg-purple-lt/20"
                  >
                    プレビュー(1)
                  </button>
                  <button
                    onClick={() => onExport(p.id, 'pptx')}
                    className="rounded border border-purple-lt px-2 py-1 text-xs hover:bg-purple-lt/20"
                  >
                    .pptx
                  </button>
                  <button
                    onClick={() => onExport(p.id, 'pdf')}
                    className="rounded border border-purple-lt px-2 py-1 text-xs hover:bg-purple-lt/20"
                  >
                    .pdf
                  </button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
