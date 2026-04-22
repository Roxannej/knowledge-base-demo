/**
 * 单条聊天消息：用户纯文本；助手使用 react-markdown 渲染。
 */
import ReactMarkdown from 'react-markdown';
import rehypeRaw from 'rehype-raw';
import remarkGfm from 'remark-gfm';

export type ChatRole = 'user' | 'assistant';

export type MessageBubbleProps = {
  role: ChatRole;
  content: string;
  streaming?: boolean;
  confidence?: number;
  sources?: string[];
};

function isTableRowCandidate(line: string): boolean {
  const s = line.trim();
  return s.length > 0 && (s.match(/\|/g)?.length ?? 0) >= 2;
}

function isTableSeparator(line: string): boolean {
  return /^\s*\|?(?:\s*:?-{3,}:?\s*\|)+\s*:?-{3,}:?\s*\|?\s*$/.test(
    line.trim()
  );
}

function rowCells(line: string): string[] {
  let s = line.trim();
  if (s.startsWith('|')) s = s.slice(1);
  if (s.endsWith('|')) s = s.slice(0, -1);
  return s.split('|').map((x) => x.trim());
}

function normalizeTableBlock(lines: string[]): string[] {
  if (lines.length < 2) return lines;
  const header = rowCells(lines[0]);
  const cols = Math.max(header.length, 1);
  const out: string[] = [];

  const fmt = (cells: string[]) => {
    const fixed = cells.slice(0, cols);
    while (fixed.length < cols) fixed.push('');
    return `| ${fixed.join(' | ')} |`;
  };

  out.push(fmt(header));
  if (lines.length > 1 && isTableSeparator(lines[1])) {
    out.push(fmt(rowCells(lines[1]).map((c) => (c ? c : '---'))));
    for (const row of lines.slice(2)) out.push(fmt(rowCells(row)));
  } else {
    out.push(`| ${Array.from({ length: cols }, () => '---').join(' | ')} |`);
    for (const row of lines.slice(1)) out.push(fmt(rowCells(row)));
  }
  return out;
}

function normalizeMarkdownTables(md: string): string {
  if (!md || !md.includes('|')) return md;
  const lines = md.replace(/\r\n?/g, '\n').split('\n');
  const out: string[] = [];
  let tableBuf: string[] = [];

  const flushTable = () => {
    if (tableBuf.length === 0) return;
    const normalized = normalizeTableBlock(tableBuf);
    if (out.length > 0 && out[out.length - 1].trim() !== '') out.push('');
    out.push(...normalized);
    out.push('');
    tableBuf = [];
  };

  for (const line of lines) {
    if (isTableRowCandidate(line)) {
      tableBuf.push(line);
    } else {
      flushTable();
      out.push(line);
    }
  }
  flushTable();

  return out.join('\n').replace(/\n{3,}/g, '\n\n');
}

function fixVisibleEscapes(text: string): string {
  if (!text || !text.includes('\\')) return text;
  return text
    .replace(/\\r\\n/g, '')
    .replace(/\\n/g, '')
    .replace(/\\t/g, '');
}

export function MessageBubble({
  role,
  content,
  streaming,
  confidence,
  sources,
}: MessageBubbleProps) {
  const isUser = role === 'user';
  const normalizedContent = isUser
    ? content
    : normalizeMarkdownTables(fixVisibleEscapes(content));

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm shadow ${
          isUser
            ? 'bg-sky-700/40 text-slate-50 ring-1 ring-sky-500/30'
            : 'bg-slate-900/70 text-slate-100 ring-1 ring-slate-700/60'
        }`}
      >
        {isUser ? (
          <div className="whitespace-pre-wrap leading-relaxed">{content}</div>
        ) : (
          <div
            className={[
              'markdown-body leading-relaxed',
              '[&_h1]:text-lg [&_h1]:font-semibold [&_h2]:text-base [&_h2]:font-semibold',
              '[&_ul]:list-disc [&_ul]:pl-5 [&_ol]:list-decimal [&_ol]:pl-5',
              '[&_table]:my-3 [&_table]:w-full [&_table]:border-collapse [&_table]:overflow-hidden [&_table]:rounded-md',
              '[&_thead_th]:border [&_thead_th]:border-slate-700 [&_thead_th]:bg-slate-800/70 [&_thead_th]:px-2 [&_thead_th]:py-1',
              '[&_tbody_td]:border [&_tbody_td]:border-slate-800 [&_tbody_td]:px-2 [&_tbody_td]:py-1 align-top',
              '[&_code]:rounded [&_code]:bg-slate-950/70 [&_code]:px-1 [&_code]:py-0.5',
              '[&_pre]:overflow-x-auto [&_pre]:rounded-lg [&_pre]:bg-slate-950/70 [&_pre]:p-3',
              '[&_a]:text-sky-300 [&_a]:underline',
            ].join(' ')}
          >
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              rehypePlugins={[rehypeRaw]}
            >
              {normalizedContent || (streaming ? '…' : '')}
            </ReactMarkdown>
            {streaming ? (
              <span className="ml-1 inline-block h-3 w-1 animate-pulse rounded bg-sky-400" />
            ) : null}
          </div>
        )}

        {!isUser &&
        !streaming &&
        (confidence !== undefined || (sources && sources.length)) ? (
          <div className="mt-3 border-t border-slate-800 pt-2 text-xs text-slate-400">
            {confidence !== undefined ? (
              <div>
                置信度：
                <span className="text-slate-200">{confidence.toFixed(2)}</span>
              </div>
            ) : null}
            {sources && sources.length ? (
              <details className="mt-2">
                <summary className="cursor-pointer select-none text-slate-300">
                  引用片段
                </summary>
                <ul className="mt-2 space-y-1 text-slate-300">
                  {sources.map((s, idx) => (
                    <li
                      key={idx}
                      className="whitespace-pre-wrap rounded bg-slate-950/40 p-2"
                    >
                      {s}
                    </li>
                  ))}
                </ul>
              </details>
            ) : null}
          </div>
        ) : null}
      </div>
    </div>
  );
}
