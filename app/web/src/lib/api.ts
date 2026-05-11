/** Minimal API client with Cognito access token. */

import { getValidAccessToken } from './auth';
import { getConfig } from './config';

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const { apiEndpoint } = await getConfig();
  // Pulls a token that's guaranteed-valid right now; the auth helper
  // transparently uses the refresh token to swap an expired access
  // token for a fresh one, so 1-hour JWT expiry never bubbles up as a
  // 401 mid-session anymore.
  const token = typeof window !== 'undefined' ? await getValidAccessToken() : null;
  const isBodyJson = init.body && typeof init.body === 'string';
  const res = await fetch(`${apiEndpoint}${path}`, {
    ...init,
    headers: {
      ...(isBodyJson ? { 'Content-Type': 'application/json' } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init.headers,
    },
  });
  if (res.status === 401 && typeof window !== 'undefined') {
    // Refresh token has expired (or some other auth lapse). The token
    // helper has already cleared local cache as a side effect of its
    // failed refresh, so route to login instead of throwing into the
    // UI as a generic "401 ..." string.
    window.location.assign('/login');
    // Bail with a typed error so the caller's catch path still runs
    // (and the redirect kicks in before any chained Promise resolves).
    throw new Error('401 unauthorized — redirecting to login');
  }
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return (await res.json()) as T;
}

export interface TemplateLayoutEntry {
  index: number;
  layout: string;
  confidence?: number;
  reason?: string;
}

export interface TemplateProfile {
  id: string;
  tenant_id: string;
  name: string;
  original_s3_path: string;
  design_tokens: Record<string, unknown>;
  layouts: TemplateLayoutEntry[];
  template_slide_count: number;
  created_at: string;
}

export interface Project {
  id: string;
  name: string;
  template_id: string;
  status: string;
  created_at: string;
}

export interface SlideSpec {
  index: number;
  layout: string;
  figure_type?: string;
  content: Record<string, unknown>;
  template_slide_index?: number | null;
}

/**
 * Figure types known to the backend's FigureType Literal. Kept in
 * sync with app/api/models/schemas.py — when a new figure_type is
 * added there, mirror it here.
 */
export const FIGURE_TYPES = [
  'table',
  'cards_grid',
  'two_column',
  'timeline',
  'stat_callout',
  'bullet_list',
  'comparison',
  'matrix_2x2',
  'swot',
  'pyramid',
  'org_chart',
  'kpi_dashboard',
  'pull_quote',
  'icon_list',
  'process_flow',
  'gantt',
  'stack_bar',
  'waterfall',
  'cost_breakdown',
  'bar_chart',
  'line_chart',
  'pie_chart',
  'image_slot',
  'flowchart',
  'spider_map',
  'system_map',
  'value_flow',
  'value_chain',
  'business_canvas',
  'scheme_diagram',
] as const;
export type FigureType = (typeof FIGURE_TYPES)[number];

/**
 * Display labels for figure types (UI-only). The wire format stays the
 * machine-readable snake_case identifier; users see Japanese.
 * Falls back to the raw id if a future backend type isn't in this map.
 *
 * Includes a few chart / composite ids ("bar_chart", "line_chart",
 * "pie_chart", "composite") that are NOT in FIGURE_TYPES — those only
 * appear in the samples gallery (LayoutSpec-only specimens) and the
 * dropdown lists them by raw id without these labels.
 */
export const FIGURE_TYPE_LABELS: Record<string, string> = {
  table: 'テーブル',
  cards_grid: 'カードグリッド',
  two_column: '2カラム',
  timeline: 'タイムライン',
  stat_callout: '統計コールアウト',
  bullet_list: '箇条書き',
  comparison: '比較',
  matrix_2x2: '2×2マトリクス',
  swot: 'SWOT分析',
  pyramid: 'ピラミッド',
  org_chart: '組織図',
  kpi_dashboard: 'KPIダッシュボード',
  pull_quote: '引用',
  icon_list: 'アイコンリスト',
  process_flow: 'プロセスフロー',
  gantt: 'ガントチャート',
  stack_bar: '積み上げ棒グラフ',
  waterfall: 'ウォーターフォール',
  cost_breakdown: 'コスト内訳',
  image_slot: '画像スロット',
  flowchart: 'フローチャート',
  spider_map: 'スパイダーマップ',
  system_map: 'システムマップ',
  value_flow: 'バリューフロー',
  value_chain: 'バリューチェーン',
  business_canvas: 'ビジネスキャンバス',
  scheme_diagram: 'スキーム図',
  bar_chart: '棒グラフ',
  line_chart: '折れ線グラフ',
  pie_chart: '円グラフ',
  // Samples-gallery-only — "composite" tags free-form LayoutSpec
  // specimens that mix multiple primitives, not a real figure_type.
  composite: '複合レイアウト',
};

export function figureTypeLabel(ft: string): string {
  return FIGURE_TYPE_LABELS[ft] ?? ft;
}

export interface SlideTemplateMapping {
  index: number;
  template_slide_index?: number;
  figure_type?: FigureType;
  /** Set true (with figure_type omitted) to clear the slide's figure_type. */
  clear_figure_type?: boolean;
}

export interface Blueprint {
  id: string;
  project_id: string;
  version: number;
  title: string;
  slides: SlideSpec[];
  created_at: string;
}

export type BlueprintJobStatus = 'pending' | 'complete' | 'failed';

export interface BlueprintJob {
  job_id: string;
  project_id: string;
  status: BlueprintJobStatus;
  blueprint_id?: string | null;
  error?: string | null;
  created_at?: string | null;
}

/** Same shape as BlueprintJob but tracking a revision rather than a
 *  brand-new blueprint. The new BlueprintRow's id appears in
 *  `blueprint_id` once the worker finishes. */
export type RevisionJobStatus = 'pending' | 'complete' | 'failed';

export interface RevisionJob {
  job_id: string;
  project_id: string;
  status: RevisionJobStatus;
  blueprint_id?: string | null;
  error?: string | null;
  created_at?: string | null;
}

export const api = {
  health: () => request<{ status: string }>('/health'),
  listTemplates: () => request<TemplateProfile[]>('/api/templates'),
  getTemplate: (id: string) => request<TemplateProfile>(`/api/templates/${id}`),
  createTemplate: (name: string) =>
    request<{ template_id: string; upload_url: string }>(
      `/api/templates?name=${encodeURIComponent(name)}`,
      { method: 'POST' },
    ),
  deleteTemplate: (id: string) =>
    request<{ deleted: string }>(`/api/templates/${id}`, { method: 'DELETE' }),
  /** Upload a .pptx file to a presigned S3 URL returned by createTemplate. */
  uploadTemplateFile: async (uploadUrl: string, file: File): Promise<void> => {
    const res = await fetch(uploadUrl, {
      method: 'PUT',
      headers: {
        'Content-Type':
          'application/vnd.openxmlformats-officedocument.presentationml.presentation',
      },
      body: file,
    });
    if (!res.ok) throw new Error(`upload failed: ${res.status} ${await res.text()}`);
  },
  listProjects: () => request<Project[]>('/api/projects'),
  getProject: (id: string) => request<Project>(`/api/projects/${id}`),
  createProject: (name: string, template_id: string) =>
    request<Project>('/api/projects', {
      method: 'POST',
      body: JSON.stringify({ name, template_id }),
    }),
  deleteProject: (id: string) =>
    request<{ deleted: string }>(`/api/projects/${id}`, { method: 'DELETE' }),
  duplicateProject: (id: string) =>
    request<Project>(`/api/projects/${id}/duplicate`, { method: 'POST' }),
  createBlueprint: (project_id: string, intent: string, required_sections: string[]) =>
    request<BlueprintJob>(`/api/projects/${project_id}/blueprint`, {
      method: 'POST',
      body: JSON.stringify({ intent, required_sections, mode: 'freeform' }),
    }),
  getBlueprintJob: (project_id: string, job_id: string) =>
    request<BlueprintJob>(`/api/projects/${project_id}/blueprint/job/${job_id}`),
  getBlueprint: (project_id: string) => request<Blueprint>(`/api/projects/${project_id}/blueprint`),
  patchBlueprintMapping: (project_id: string, mappings: SlideTemplateMapping[]) =>
    request<Blueprint>(`/api/projects/${project_id}/blueprint`, {
      method: 'PATCH',
      body: JSON.stringify({ mappings }),
    }),
  /**
   * Enqueue a revision job. The server returns immediately with a
   * RevisionJob handle; poll getRevisionJob until status flips off
   * "pending" then re-fetch the blueprint.
   */
  revise: (
    project_id: string,
    instruction: string,
    slide_index?: number,
  ) =>
    request<RevisionJob>(`/api/projects/${project_id}/revise`, {
      method: 'POST',
      body: JSON.stringify(
        slide_index === undefined
          ? { instruction }
          : { instruction, slide_index },
      ),
    }),
  getRevisionJob: (project_id: string, job_id: string) =>
    request<RevisionJob>(
      `/api/projects/${project_id}/revise/job/${job_id}`,
    ),
  render: (project_id: string) =>
    request<{ job_id: string; status: string }>(`/api/projects/${project_id}/render`, { method: 'POST' }),
  preview: (project_id: string, slide_index: number) =>
    request<{ slide_index: number; url: string }>(`/api/projects/${project_id}/preview/${slide_index}`),
  listPreviews: (project_id: string) =>
    request<{ slides: { slide_index: number; url: string }[] }>(
      `/api/projects/${project_id}/previews`,
    ),
  exportUrl: (project_id: string, format: 'pptx' | 'pdf') =>
    request<{ format: string; url: string }>(`/api/projects/${project_id}/export?format=${format}`),
};
