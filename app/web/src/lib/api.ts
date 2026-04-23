/** Minimal API client with Cognito access token. */

import { getConfig } from './config';

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const { apiEndpoint } = await getConfig();
  const token = typeof window !== 'undefined' ? window.localStorage.getItem('slideforge.accessToken') : null;
  const isBodyJson = init.body && typeof init.body === 'string';
  const res = await fetch(`${apiEndpoint}${path}`, {
    ...init,
    headers: {
      ...(isBodyJson ? { 'Content-Type': 'application/json' } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init.headers,
    },
  });
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return (await res.json()) as T;
}

export interface TemplateProfile {
  id: string;
  tenant_id: string;
  name: string;
  original_s3_path: string;
  design_tokens: Record<string, unknown>;
  layouts: unknown[];
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
  createBlueprint: (project_id: string, intent: string, required_sections: string[]) =>
    request<BlueprintJob>(`/api/projects/${project_id}/blueprint`, {
      method: 'POST',
      body: JSON.stringify({ intent, required_sections, mode: 'freeform' }),
    }),
  getBlueprintJob: (project_id: string, job_id: string) =>
    request<BlueprintJob>(`/api/projects/${project_id}/blueprint/job/${job_id}`),
  getBlueprint: (project_id: string) => request<Blueprint>(`/api/projects/${project_id}/blueprint`),
  revise: (project_id: string, instruction: string) =>
    request<{ id: string; patch: unknown[] }>(`/api/projects/${project_id}/revise`, {
      method: 'POST',
      body: JSON.stringify({ instruction }),
    }),
  render: (project_id: string) =>
    request<{ job_id: string; status: string }>(`/api/projects/${project_id}/render`, { method: 'POST' }),
  preview: (project_id: string, slide_index: number) =>
    request<{ slide_index: number; url: string }>(`/api/projects/${project_id}/preview/${slide_index}`),
  exportUrl: (project_id: string, format: 'pptx' | 'pdf') =>
    request<{ format: string; url: string }>(`/api/projects/${project_id}/export?format=${format}`),
};
