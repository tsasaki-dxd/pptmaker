'use client';

import { useEffect, useMemo, useState } from 'react';

import { figureTypeLabel } from '@/lib/api';

type Sample = {
  id: string;
  figure_type: string;
  title: string;
  prompt: string;
  notes: string;
  image: string;
  spec: unknown;
};

const ALL = '__all__';

// "composite" is a meta-tag for free-form LayoutSpec specimens — not a
// real figure_type — so it sorts to the end of the gallery instead of
// landing alphabetically in the middle.
function compareFigureTypes(a: string, b: string): number {
  const aLast = a === 'composite';
  const bLast = b === 'composite';
  if (aLast && !bLast) return 1;
  if (!aLast && bLast) return -1;
  return a.localeCompare(b);
}

export default function SamplesPage() {
  const [samples, setSamples] = useState<Sample[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [figureType, setFigureType] = useState<string>(ALL);
  const [search, setSearch] = useState<string>('');
  const [active, setActive] = useState<Sample | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch('/samples/manifest.json')
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json() as Promise<Sample[]>;
      })
      .then((data) => {
        if (!cancelled) setSamples(data);
      })
      .catch((e) => {
        if (!cancelled) setError(String(e));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const figureTypes = useMemo(() => {
    if (!samples) return [] as string[];
    return Array.from(new Set(samples.map((s) => s.figure_type))).sort(
      compareFigureTypes,
    );
  }, [samples]);

  const filtered = useMemo(() => {
    if (!samples) return [] as Sample[];
    const q = search.trim().toLowerCase();
    const matched = samples.filter((s) => {
      if (figureType !== ALL && s.figure_type !== figureType) return false;
      if (!q) return true;
      return (
        s.prompt.toLowerCase().includes(q) ||
        s.title.toLowerCase().includes(q) ||
        s.notes.toLowerCase().includes(q)
      );
    });
    // Re-sort so composite specimens always sit at the end of the
    // grid; the manifest's natural alphabetic order would put them
    // partway through.
    return [...matched].sort((a, b) => {
      const byType = compareFigureTypes(a.figure_type, b.figure_type);
      return byType !== 0 ? byType : a.id.localeCompare(b.id);
    });
  }, [samples, figureType, search]);

  return (
    <section className="space-y-6">
      <header className="space-y-2">
        <h2 className="text-2xl font-bold">レンダリングサンプル</h2>
        <p className="text-sm text-muted">
          現在の実装で生成されるレイアウトの参考集。フィギュア種別 × プロンプト例ごとに、
          実際にレンダラを通した PNG を表示しています (静的アセット)。
        </p>
      </header>

      <div className="flex flex-wrap items-center gap-3 rounded border border-purple-lt/40 bg-white px-4 py-3">
        <label className="flex items-center gap-2 text-sm">
          <span className="text-muted">図種:</span>
          <select
            value={figureType}
            onChange={(e) => setFigureType(e.target.value)}
            className="rounded border border-purple-lt/60 px-2 py-1 text-sm"
          >
            <option value={ALL}>すべて ({samples?.length ?? 0})</option>
            {figureTypes.map((ft) => {
              const n = samples?.filter((s) => s.figure_type === ft).length ?? 0;
              return (
                <option key={ft} value={ft}>
                  {figureTypeLabel(ft)} ({n})
                </option>
              );
            })}
          </select>
        </label>

        <label className="flex flex-1 items-center gap-2 text-sm">
          <span className="text-muted">検索:</span>
          <input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="プロンプト / タイトル / メモ"
            className="min-w-[12rem] flex-1 rounded border border-purple-lt/60 px-2 py-1 text-sm"
          />
        </label>

        <span className="text-xs text-muted">{filtered.length} 件表示中</span>
      </div>

      {error && (
        <div className="rounded border border-amber bg-amber/10 px-4 py-3 text-sm">
          サンプルを読み込めませんでした: {error}
          <div className="mt-1 text-xs text-muted">
            生成は <code>python -m scripts.generate_samples</code> で行います。
          </div>
        </div>
      )}

      {!samples && !error && <div className="text-sm text-muted">読み込み中…</div>}

      {samples && filtered.length === 0 && (
        <div className="rounded border border-purple-lt/60 bg-white px-4 py-8 text-center text-sm text-muted">
          条件に合うサンプルがありません。
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        {filtered.map((s) => (
          <button
            key={s.id}
            type="button"
            onClick={() => setActive(s)}
            className="group flex flex-col rounded border border-purple-lt/60 bg-white text-left transition hover:border-purple hover:shadow"
          >
            <div className="relative overflow-hidden rounded-t bg-purple-bg/40">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={s.image}
                alt={s.title}
                loading="lazy"
                className="block h-auto w-full"
              />
            </div>
            <div className="space-y-1.5 px-4 py-3">
              <div className="flex items-center gap-2">
                <span className="rounded-full bg-purple/10 px-2 py-0.5 text-xs font-medium tracking-wide text-purple-dk">
                  {figureTypeLabel(s.figure_type)}
                </span>
                <h3 className="text-sm font-bold text-purple-dk">{s.title}</h3>
              </div>
              <p className="line-clamp-2 text-xs text-muted">{s.prompt}</p>
            </div>
          </button>
        ))}
      </div>

      {active && <SampleDetail sample={active} onClose={() => setActive(null)} />}
    </section>
  );
}

function SampleDetail({ sample, onClose }: { sample: Sample; onClose: () => void }) {
  // Close on Escape so power users don't need to mouse over.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/60 p-4 sm:p-8"
      onClick={onClose}
    >
      <div
        className="relative my-4 w-full max-w-5xl rounded bg-white p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <button
          type="button"
          onClick={onClose}
          className="absolute right-3 top-3 rounded px-2 py-1 text-sm text-muted hover:bg-purple-bg"
          aria-label="閉じる"
        >
          ✕
        </button>

        <div className="space-y-4">
          <div className="flex items-center gap-3">
            <span className="rounded-full bg-purple/10 px-2 py-0.5 text-xs font-medium tracking-wide text-purple-dk">
              {figureTypeLabel(sample.figure_type)}
            </span>
            <h3 className="text-xl font-bold text-purple-dk">{sample.title}</h3>
          </div>

          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={sample.image}
            alt={sample.title}
            className="block h-auto w-full rounded border border-purple-lt/40"
          />

          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <div>
              <h4 className="text-sm font-bold text-purple-dk">参考プロンプト</h4>
              <p className="mt-1 whitespace-pre-wrap text-sm">{sample.prompt}</p>
              {sample.notes && (
                <>
                  <h4 className="mt-3 text-sm font-bold text-purple-dk">メモ</h4>
                  <p className="mt-1 whitespace-pre-wrap text-sm text-muted">
                    {sample.notes}
                  </p>
                </>
              )}
            </div>
            <div>
              <h4 className="text-sm font-bold text-purple-dk">LayoutSpec</h4>
              <pre className="mt-1 max-h-80 overflow-auto rounded bg-purple-bg/30 p-3 text-xs leading-relaxed">
                {JSON.stringify(sample.spec, null, 2)}
              </pre>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
