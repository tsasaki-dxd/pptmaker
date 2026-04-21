'use client';

import { useState } from 'react';
import { api } from '@/lib/api';

export default function ProjectsPage() {
  const [name, setName] = useState('');
  const [templateId, setTemplateId] = useState('');
  const [intent, setIntent] = useState('');
  const [sections, setSections] = useState('課題認識, 提案概要, 体制, 費用, スケジュール');
  const [log, setLog] = useState<string[]>([]);

  function push(msg: string) {
    setLog((prev) => [...prev, msg]);
  }

  async function handleFlow() {
    try {
      push('プロジェクト作成...');
      const project = await api.createProject(name, templateId);
      push(`project_id = ${project.id}`);

      push('骨格生成中...');
      const bp = await api.createBlueprint(
        project.id,
        intent,
        sections.split(',').map((s) => s.trim()).filter(Boolean),
      );
      push(`blueprint_id = ${bp.id} (${bp.slides.length} slides)`);

      push('レンダリング投入...');
      const r = await api.render(project.id);
      push(`job_id = ${r.job_id} status=${r.status}`);

      push('完了まで数十秒待ってプレビューを確認してください');
    } catch (e) {
      push(`失敗: ${String(e)}`);
    }
  }

  return (
    <section className="space-y-4">
      <h2 className="text-2xl font-bold">プロジェクト</h2>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        <Field label="プロジェクト名" value={name} onChange={setName} />
        <Field label="テンプレート ID" value={templateId} onChange={setTemplateId} />
      </div>
      <Field label="ユーザー意図（自然文）" value={intent} onChange={setIntent} textarea />
      <Field label="必須セクション（カンマ区切り）" value={sections} onChange={setSections} />
      <button
        onClick={handleFlow}
        disabled={!name || !templateId || !intent}
        className="rounded bg-purple px-4 py-2 text-white disabled:bg-muted"
      >
        作成して骨格生成＋レンダリング
      </button>
      <pre className="mt-4 whitespace-pre-wrap rounded bg-white p-3 text-xs text-dark shadow-inner">
        {log.join('\n')}
      </pre>
    </section>
  );
}

function Field({
  label,
  value,
  onChange,
  textarea,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  textarea?: boolean;
}) {
  return (
    <label className="flex flex-col gap-1 text-sm">
      <span className="text-dark">{label}</span>
      {textarea ? (
        <textarea
          className="min-h-[120px] rounded border border-purple-lt px-3 py-2"
          value={value}
          onChange={(e) => onChange(e.target.value)}
        />
      ) : (
        <input
          className="rounded border border-purple-lt px-3 py-2"
          value={value}
          onChange={(e) => onChange(e.target.value)}
        />
      )}
    </label>
  );
}
