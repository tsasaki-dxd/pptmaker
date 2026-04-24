'use client';

/**
 * Full-screen loading overlay. Renders nothing when ``when`` is false
 * so the wrapper can be dropped at the bottom of any page without
 * disturbing layout. When ``when`` is true, a semi-transparent
 * backdrop covers the whole viewport and intercepts all pointer
 * events — users can't accidentally fire a second request while an
 * async call is in flight.
 *
 * ``label`` is optional — shows under the spinner when provided, so
 * the user knows what's running (e.g. "レンダリング中…").
 *
 * Use for flows that hit the LLM / SQS / S3 (blueprint generation,
 * per-slide revise, render, re-render, template upload, duplicate,
 * delete). Quick presigned-URL lookups don't need it.
 */
export function LoadingOverlay({
  when,
  label,
}: {
  when: boolean;
  label?: string;
}) {
  if (!when) return null;
  return (
    <div
      role="status"
      aria-live="polite"
      aria-label={label ?? '処理中'}
      className="fixed inset-0 z-50 flex flex-col items-center justify-center gap-3 bg-black/30 backdrop-blur-sm"
      // Swallow clicks so nothing underneath responds.
      onClick={(e) => e.preventDefault()}
      onMouseDown={(e) => e.preventDefault()}
    >
      <div className="h-10 w-10 animate-spin rounded-full border-4 border-white border-t-transparent" />
      {label && (
        <div className="rounded bg-white/90 px-3 py-1 text-sm font-medium text-dark">
          {label}
        </div>
      )}
    </div>
  );
}
