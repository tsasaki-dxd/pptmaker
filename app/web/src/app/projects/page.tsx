'use client';

import { useCallback, useEffect, useState } from 'react';

import {
  api,
  type Blueprint,
  type Project,
  type SlideSpec,
  type SlideTemplateMapping,
  type TemplateLayoutEntry,
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
  const [previewModal, setPreviewModal] = useState<{
    projectName: string;
    slides: { slide_index: number; url: string }[];
  } | null>(null);
  // Post-render preview (Step 3 / done state). Loaded after render
  // completes so the user can eyeball every slide and fire per-slide
  // revisions from the same screen without hopping to the list modal.
  const [stepPreviews, setStepPreviews] = useState<
    { slide_index: number; url: string }[]
  >([]);

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

  async function handleRevise(slideIndex?: number) {
    if (!project || !revisionText.trim()) return;
    setBusy(true);
    try {
      const scope = slideIndex ? `スライド#${slideIndex}` : '全体';
      push(`修正指示送信 (${scope}): "${revisionText}"`);
      await api.revise(project.id, revisionText, slideIndex);
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

  async function handleReviseSlide(slideIndex: number, instruction: string) {
    if (!project || !instruction.trim()) return;
    setBusy(true);
    try {
      push(`スライド#${slideIndex} 修正指示: "${instruction}"`);
      await api.revise(project.id, instruction, slideIndex);
      const bp = await api.getBlueprint(project.id);
      setBlueprint(bp);
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
      if (status === 'partial') {
        push('部分的に完了: .pptx は生成できたが preview/PDF はエラー');
      } else {
        push('完了!');
      }
      setStep('done');
      await refresh();
      await loadStepPreviews();
    } catch (e) {
      push(`失敗: ${String(e)}`);
      setStep('reviewing'); // back to review so user can retry
      await refresh();
    } finally {
      setBusy(false);
    }
  }

  async function loadStepPreviews() {
    if (!project) return;
    try {
      const res = await api.listPreviews(project.id);
      setStepPreviews(res.slides);
    } catch (e) {
      push(`プレビュー取得失敗: ${String(e)}`);
      setStepPreviews([]);
    }
  }

  // Per-slide revision fired from the Step 3 side panel. Reuses the
  // same slide_index-scoped LLM path as Step 2, then triggers a full
  // render (deterministic for unchanged slides since the render
  // pipeline has no LLM in it). While it runs we flip the step back
  // to "rendering" so the user sees progress.
  async function handleStep3ReviseAndRender(
    slideIndex: number | null,
    instruction: string,
  ) {
    if (!project || !instruction.trim()) return;
    setBusy(true);
    try {
      const scope = slideIndex ? `スライド#${slideIndex}` : '全体';
      push(`(step3) 修正指示送信 (${scope}): "${instruction}"`);
      await api.revise(project.id, instruction, slideIndex ?? undefined);
      const bp = await api.getBlueprint(project.id);
      setBlueprint(bp);
      push(`修正完了: v${bp.version}`);

      setStep('rendering');
      push('再レンダリング投入...');
      const r = await api.render(project.id);
      push(`job_id = ${r.job_id} status=${r.status}`);
      const status = await pollRenderComplete(project.id);
      if (status === 'failed') throw new Error('再レンダリング失敗');
      push(status === 'partial' ? '部分完了' : '完了!');
      setStep('done');
      await refresh();
      await loadStepPreviews();
    } catch (e) {
      push(`失敗: ${String(e)}`);
      setStep('done');
    } finally {
      setBusy(false);
    }
  }

  async function pollRenderComplete(
    projectId: string,
  ): Promise<'complete' | 'partial' | 'failed'> {
    const intervalMs = 3000;
    const maxAttempts = 100;
    const startedAt = Date.now();
    for (let i = 0; i < maxAttempts; i++) {
      const p = await api.getProject(projectId);
      const elapsed = Math.round((Date.now() - startedAt) / 1000);
      if (p.status === 'complete' || p.status === 'partial' || p.status === 'failed') {
        return p.status;
      }
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
    setStepPreviews([]);
  }

  async function handleOpenPreviewGallery(p: Project) {
    try {
      const res = await api.listPreviews(p.id);
      setPreviewModal({ projectName: p.name, slides: res.slides });
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
          onRevise={() => handleRevise()}
          onReviseSlide={handleReviseSlide}
          onRender={handleRender}
          onCancel={handleStartOver}
          busy={busy}
        />
      )}

      {(step === 'rendering' || step === 'done') && (
        <Step3Result
          step={step}
          project={project}
          previews={stepPreviews}
          onStartOver={handleStartOver}
          onExport={handleExport}
          onReviseAndRender={handleStep3ReviseAndRender}
          busy={busy}
        />
      )}

      {log.length > 0 && (
        <pre className="whitespace-pre-wrap rounded bg-off p-3 text-xs">{log.join('\n')}</pre>
      )}

      <ProjectsList
        projects={projects}
        onPreview={handleOpenPreviewGallery}
        onExport={handleExport}
        onDuplicate={handleDuplicateProject}
        onDelete={handleDeleteProject}
        busy={busy}
      />

      {previewModal && (
        <PreviewModal
          projectName={previewModal.projectName}
          slides={previewModal.slides}
          onClose={() => setPreviewModal(null)}
        />
      )}
    </section>
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
  onReviseSlide: (slideIndex: number, instruction: string) => void;
  onRender: () => void;
  onCancel: () => void;
  busy: boolean;
}) {
  const {
    blueprint,
    template,
    onMappingChange,
    revisionText,
    setRevisionText,
    onRevise,
    onReviseSlide,
    onRender,
    onCancel,
    busy,
  } = props;
  const templatePages = template?.template_slide_count ?? 0;
  const layoutByIndex = new Map<number, string>();
  for (const l of template?.layouts ?? []) layoutByIndex.set(l.index, l.layout);

  return (
    <div className="space-y-4 rounded border border-purple-lt/60 bg-white p-4">
      <div className="flex items-baseline justify-between">
        <h3 className="text-sm font-bold text-muted">Step 2: 骨格レビュー</h3>
        <span className="text-xs text-muted">
          v{blueprint.version} / {blueprint.slides.length} slides / template {templatePages}p
        </span>
      </div>
      <h4 className="text-base font-bold">{blueprint.title}</h4>

      <div className="space-y-3">
        {blueprint.slides.map((s) => (
          <SlideCard
            key={s.index}
            slide={s}
            templatePages={templatePages}
            layoutByIndex={layoutByIndex}
            onMappingChange={onMappingChange}
            onReviseSlide={onReviseSlide}
            disabled={busy}
          />
        ))}
      </div>

      <div className="space-y-2 rounded border border-purple-lt/60 p-3">
        <label className="flex flex-col gap-1 text-sm">
          <span>修正指示（全体を書き換え）</span>
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
          {busy ? '実行中...' : '全体を修正'}
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

function SlideCard(props: {
  slide: SlideSpec;
  templatePages: number;
  layoutByIndex: Map<number, string>;
  onMappingChange: (slideIndex: number, value: number) => void;
  onReviseSlide: (slideIndex: number, instruction: string) => void;
  disabled: boolean;
}) {
  const { slide, templatePages, layoutByIndex, onMappingChange, onReviseSlide, disabled } = props;
  const [localRevision, setLocalRevision] = useState('');
  const [expanded, setExpanded] = useState(false);
  const current =
    slide.template_slide_index ??
    (templatePages > 0 ? ((slide.index - 1) % templatePages) + 1 : 1);

  return (
    <div className="rounded border border-purple-lt/60 p-3 text-xs">
      <div className="flex flex-wrap items-baseline gap-2">
        <span className="font-mono text-sm font-bold">#{slide.index}</span>
        <span className="rounded bg-purple-lt/40 px-2 py-0.5 text-xs">{slide.layout}</span>
        {slide.figure_type && (
          <span className="rounded bg-amber-50 px-2 py-0.5 text-xs text-amber-800">
            {slide.figure_type}
          </span>
        )}
        <span className="ml-auto flex items-center gap-1">
          <span className="text-muted">テンプレ</span>
          {templatePages > 0 ? (
            <select
              value={current}
              onChange={(e) => onMappingChange(slide.index, Number(e.target.value))}
              disabled={disabled}
              className="rounded border border-purple-lt px-1 py-0.5 text-xs"
            >
              {Array.from({ length: templatePages }, (_, i) => i + 1).map((n) => {
                const lt = layoutByIndex.get(n);
                return (
                  <option key={n} value={n}>
                    {lt ? `#${n} (${lt})` : `#${n}`}
                  </option>
                );
              })}
            </select>
          ) : (
            <span className="text-muted">N/A</span>
          )}
        </span>
      </div>

      <div className="mt-2 space-y-1">
        <ContentTree content={slide.content} />
      </div>

      <div className="mt-2">
        <button
          onClick={() => setExpanded((v) => !v)}
          className="text-xs text-purple underline"
          type="button"
        >
          {expanded ? 'このスライド修正欄を閉じる' : 'このスライドを修正…'}
        </button>
        {expanded && (
          <div className="mt-2 flex flex-col gap-2">
            <textarea
              value={localRevision}
              onChange={(e) => setLocalRevision(e.target.value)}
              placeholder="例: 箇条書きを3項目に絞って、最後の1項目を表に変えて"
              disabled={disabled}
              className="min-h-[60px] rounded border border-purple-lt px-3 py-2"
            />
            <div className="flex gap-2">
              <button
                onClick={() => {
                  onReviseSlide(slide.index, localRevision);
                  setLocalRevision('');
                }}
                disabled={!localRevision.trim() || disabled}
                className="rounded border border-purple px-3 py-1 text-sm text-purple disabled:opacity-50"
                type="button"
              >
                このスライドを修正
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// Render the blueprint slide's `content` dict in a readable form —
// the user wanted to see exactly what's going to land on the slide
// before rendering. Handles the shapes we see in practice; anything
// else falls through to a JSON dump so nothing is silently hidden.
function ContentTree({ content }: { content: Record<string, unknown> }) {
  const title = content.title as string | undefined;
  const body = content.body as string | undefined;
  const subtitle = content.subtitle as string | undefined;

  return (
    <div className="space-y-1">
      {title && <div className="font-bold text-sm text-dark">{title}</div>}
      {subtitle && <div className="text-muted">{subtitle}</div>}
      {body && <div className="whitespace-pre-wrap text-dark">{body}</div>}
      <StructuredContent content={content} />
    </div>
  );
}

function StructuredContent({ content }: { content: Record<string, unknown> }) {
  // title/subtitle/body/slots are already rendered above / internal.
  const RESERVED = new Set(['title', 'subtitle', 'body', 'body_main', 'slots', 'note', 'footer']);
  const extras = Object.entries(content).filter(([k]) => !RESERVED.has(k));
  if (extras.length === 0) return null;
  return (
    <div className="space-y-1">
      {extras.map(([key, value]) => (
        <FieldView key={key} name={key} value={value} />
      ))}
    </div>
  );
}

function FieldView({ name, value }: { name: string; value: unknown }) {
  if (Array.isArray(value)) {
    const allStrings = value.every((v) => typeof v === 'string');
    if (allStrings) {
      return (
        <div>
          <span className="text-muted">{name}:</span>
          <ul className="ml-4 list-disc text-dark">
            {(value as string[]).map((v, i) => (
              <li key={i}>{v}</li>
            ))}
          </ul>
        </div>
      );
    }
    return (
      <div>
        <span className="text-muted">{name}:</span>
        <ul className="ml-4 list-disc text-dark">
          {value.map((v, i) => (
            <li key={i}>
              {typeof v === 'object' && v !== null ? (
                <div className="ml-0">
                  {Object.entries(v as Record<string, unknown>).map(([k, val]) => (
                    <FieldView key={k} name={k} value={val} />
                  ))}
                </div>
              ) : (
                String(v)
              )}
            </li>
          ))}
        </ul>
      </div>
    );
  }
  if (typeof value === 'object' && value !== null) {
    return (
      <div>
        <span className="text-muted">{name}:</span>
        <div className="ml-4">
          {Object.entries(value as Record<string, unknown>).map(([k, v]) => (
            <FieldView key={k} name={k} value={v} />
          ))}
        </div>
      </div>
    );
  }
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    return (
      <div>
        <span className="text-muted">{name}:</span> <span className="text-dark">{String(value)}</span>
      </div>
    );
  }
  return null;
}

// ──────────────────────────────────────────────────────────────────────
// Step 3: render result — preview grid (left) + revise side panel (right)
// ──────────────────────────────────────────────────────────────────────
function Step3Result(props: {
  step: Step;
  project: Project | null;
  previews: { slide_index: number; url: string }[];
  onStartOver: () => void;
  onExport: (projectId: string, format: 'pptx' | 'pdf') => void;
  onReviseAndRender: (slideIndex: number | null, instruction: string) => void;
  busy: boolean;
}) {
  const { step, project, previews, onStartOver, onExport, onReviseAndRender, busy } = props;
  const [selected, setSelected] = useState<number | null>(null);
  const [revision, setRevision] = useState('');
  const [lightbox, setLightbox] = useState<{ url: string; index: number } | null>(null);

  const scopeLabel = selected !== null ? `スライド#${selected}` : '全体';

  function submit() {
    if (!revision.trim()) return;
    onReviseAndRender(selected, revision);
    setRevision('');
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2 rounded border border-purple-lt/60 bg-white p-4">
        <h3 className="text-sm font-bold text-muted">Step 3: レンダリング結果</h3>
        <div className="flex gap-2">
          {project && step === 'done' && (
            <>
              <button
                onClick={() => onExport(project.id, 'pptx')}
                disabled={busy}
                className="rounded border border-purple-lt px-3 py-1 text-xs hover:bg-purple-lt/20 disabled:opacity-50"
                type="button"
              >
                .pptx
              </button>
              <button
                onClick={() => onExport(project.id, 'pdf')}
                disabled={busy}
                className="rounded border border-purple-lt px-3 py-1 text-xs hover:bg-purple-lt/20 disabled:opacity-50"
                type="button"
              >
                .pdf
              </button>
            </>
          )}
          <button
            onClick={onStartOver}
            disabled={busy}
            className="rounded bg-purple px-3 py-1 text-xs text-white disabled:bg-muted"
            type="button"
          >
            新規プロジェクト
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="rounded border border-purple-lt/60 bg-white p-4 lg:col-span-2">
          {step === 'rendering' ? (
            <p className="text-sm">レンダリング中...</p>
          ) : previews.length === 0 ? (
            <p className="text-sm text-muted">プレビュー画像がありません。</p>
          ) : (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {previews.map((s) => {
                const isSelected = selected === s.slide_index;
                return (
                  <button
                    key={s.slide_index}
                    onClick={() => setSelected(isSelected ? null : s.slide_index)}
                    onDoubleClick={() => setLightbox({ url: s.url, index: s.slide_index })}
                    className={`overflow-hidden rounded border text-left transition ${
                      isSelected
                        ? 'border-purple shadow-md ring-2 ring-purple/40'
                        : 'border-purple-lt/60 hover:border-purple'
                    }`}
                    type="button"
                  >
                    <img src={s.url} alt={`slide ${s.slide_index}`} className="w-full" loading="lazy" />
                    <div className="flex items-center justify-between px-2 py-1 text-xs">
                      <span className="text-muted">#{s.slide_index}</span>
                      {isSelected && <span className="font-bold text-purple">選択中</span>}
                    </div>
                  </button>
                );
              })}
            </div>
          )}
          {previews.length > 0 && (
            <p className="mt-2 text-xs text-muted">
              クリック=修正対象に選択 / ダブルクリック=拡大
            </p>
          )}
        </div>

        <div className="rounded border border-purple-lt/60 bg-white p-4">
          <div className="mb-2 flex items-baseline justify-between">
            <h4 className="text-sm font-bold">修正指示</h4>
            <span className="text-xs text-muted">{scopeLabel}</span>
          </div>
          <div className="mb-2 flex gap-2 text-xs">
            <button
              onClick={() => setSelected(null)}
              disabled={busy}
              className={`rounded border px-2 py-1 ${
                selected === null
                  ? 'border-purple bg-purple-lt/30 text-purple'
                  : 'border-purple-lt text-muted hover:bg-purple-lt/20'
              } disabled:opacity-50`}
              type="button"
            >
              全体を修正
            </button>
            {selected !== null && (
              <span className="self-center text-muted">スライド#{selected} のみ修正</span>
            )}
          </div>
          <textarea
            value={revision}
            onChange={(e) => setRevision(e.target.value)}
            placeholder={
              selected !== null
                ? '例: このスライドの箇条書きを3項目に絞って、表にして'
                : '例: 全体的にカジュアルな言い回しに書き換えて'
            }
            disabled={busy || step !== 'done'}
            className="min-h-[100px] w-full rounded border border-purple-lt px-3 py-2 text-sm"
          />
          <button
            onClick={submit}
            disabled={!revision.trim() || busy || step !== 'done'}
            className="mt-2 w-full rounded bg-purple px-3 py-2 text-sm text-white disabled:bg-muted"
            type="button"
          >
            {busy ? '処理中...' : '修正 → 再レンダリング'}
          </button>
        </div>
      </div>

      {lightbox && (
        <div
          className="fixed inset-0 z-40 flex items-center justify-center bg-black/70 p-4"
          onClick={() => setLightbox(null)}
        >
          <img
            src={lightbox.url}
            alt={`slide ${lightbox.index}`}
            className="max-h-full max-w-full"
            onClick={(e) => e.stopPropagation()}
          />
        </div>
      )}
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────
// Persistent project list
// ──────────────────────────────────────────────────────────────────────
function ProjectsList(props: {
  projects: Project[];
  onPreview: (p: Project) => void;
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
              ) : p.status === 'partial' ? (
                <div className="space-y-1">
                  <div className="text-xs text-amber-700">
                    .pptx は出力済み (プレビュー / PDF はエラー)
                  </div>
                  <button
                    onClick={() => onExport(p.id, 'pptx')}
                    className="rounded border border-purple-lt px-2 py-1 text-xs hover:bg-purple-lt/20"
                  >
                    .pptx
                  </button>
                </div>
              ) : (
                <div className="flex gap-2">
                  <button
                    onClick={() => onPreview(p)}
                    className="rounded border border-purple-lt px-2 py-1 text-xs hover:bg-purple-lt/20"
                  >
                    プレビュー
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
