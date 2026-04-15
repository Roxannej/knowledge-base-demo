/**
 * 文档上传区：选择 .docx / .pdf / .txt / .md，可选 replace 清空旧索引。
 */
import { useId, useState } from 'react';
import { getApiBase } from '../api/client';

export type UploadPanelProps = {
  disabled?: boolean;
  onUploaded?: (info: { chunks: number; filename: string }) => void;
};

export function UploadPanel({ disabled, onUploaded }: UploadPanelProps) {
  const replaceId = useId();
  const [replace, setReplace] = useState(true);
  const [busy, setBusy] = useState(false);
  const [hint, setHint] = useState<string | null>(null);

  async function onPickFile(
    file: File | null,
    inputEl: HTMLInputElement | null
  ) {
    if (!file) return;
    if (file.size === 0) {
      setHint('文件大小为 0，请选择有效文件');
      return;
    }
    setBusy(true);
    setHint(null);
    try {
      // 走 /upload/binary：请求体即文件字节，避免 multipart/boundary 在部分环境或误配头时导致 400
      const params = new URLSearchParams();
      params.set('replace', replace ? 'true' : 'false');
      params.set('filename', file.name || 'upload.bin');
      const res = await fetch(
        `${getApiBase()}/upload/binary?${params.toString()}`,
        {
          method: 'POST',
          body: await file.arrayBuffer(),
        }
      );
      const text = await res.text();
      let json: unknown = null;
      try {
        json = JSON.parse(text) as {
          chunks?: number;
          filename?: string;
          detail?: string;
        };
      } catch {
        // non-json error
      }
      if (!res.ok) {
        const detail =
          json && typeof json === 'object' && json && 'detail' in json
            ? String((json as { detail: unknown }).detail)
            : text;
        throw new Error(detail || `上传失败：${res.status}`);
      }
      const chunks = (json as { chunks?: number })?.chunks ?? 0;
      const filename = (json as { filename?: string })?.filename ?? file.name;
      setHint(`已入库：${filename}（${chunks} chunks）`);
      onUploaded?.({ chunks, filename });
    } catch (e) {
      setHint(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
      if (inputEl) inputEl.value = '';
    }
  }

  return (
    <section className="rounded-2xl border border-slate-800 bg-slate-900/40 p-4 shadow">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-slate-100">文档上传</h2>
          <p className="mt-1 text-xs text-slate-400">
            支持 Word（.docx）/ PDF / .txt / .md
          </p>
        </div>
        <label className="flex items-center gap-2 text-xs text-slate-300">
          <input
            id={replaceId}
            type="checkbox"
            checked={replace}
            onChange={(e) => setReplace(e.target.checked)}
            disabled={disabled || busy}
          />
          覆盖旧索引
        </label>
      </div>

      <div className="mt-4">
        <input
          type="file"
          accept=".docx,.pdf,.txt,.md,.markdown,application/pdf"
          disabled={disabled || busy}
          onChange={(e) => {
            const input = e.target;
            void onPickFile(input.files?.[0] ?? null, input);
          }}
          className="block w-full cursor-pointer text-sm text-slate-200 file:mr-3 file:cursor-pointer file:rounded-lg file:border-0 file:bg-slate-800 file:px-3 file:py-2 file:text-sm file:text-slate-100 hover:file:bg-slate-700"
        />
      </div>

      <div className="mt-3 min-h-[1.25rem] text-xs text-slate-400">
        {busy ? <span className="text-sky-300">上传解析中…</span> : null}
        {!busy && hint ? <span className="text-slate-200">{hint}</span> : null}
      </div>
    </section>
  );
}
