/**
 * 单条聊天消息：用户纯文本；助手使用 react-markdown 渲染。
 */
import ReactMarkdown from "react-markdown";

export type ChatRole = "user" | "assistant";

export type MessageBubbleProps = {
  role: ChatRole;
  content: string;
  streaming?: boolean;
  confidence?: number;
  sources?: string[];
};

export function MessageBubble({
  role,
  content,
  streaming,
  confidence,
  sources,
}: MessageBubbleProps) {
  const isUser = role === "user";

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm shadow ${
          isUser
            ? "bg-sky-700/40 text-slate-50 ring-1 ring-sky-500/30"
            : "bg-slate-900/70 text-slate-100 ring-1 ring-slate-700/60"
        }`}
      >
        {isUser ? (
          <div className="whitespace-pre-wrap leading-relaxed">{content}</div>
        ) : (
          <div
            className={[
              "markdown-body leading-relaxed",
              "[&_h1]:text-lg [&_h1]:font-semibold [&_h2]:text-base [&_h2]:font-semibold",
              "[&_ul]:list-disc [&_ul]:pl-5 [&_ol]:list-decimal [&_ol]:pl-5",
              "[&_code]:rounded [&_code]:bg-slate-950/70 [&_code]:px-1 [&_code]:py-0.5",
              "[&_pre]:overflow-x-auto [&_pre]:rounded-lg [&_pre]:bg-slate-950/70 [&_pre]:p-3",
              "[&_a]:text-sky-300 [&_a]:underline",
            ].join(" ")}
          >
            <ReactMarkdown>{content || (streaming ? "…" : "")}</ReactMarkdown>
            {streaming ? (
              <span className="ml-1 inline-block h-3 w-1 animate-pulse rounded bg-sky-400" />
            ) : null}
          </div>
        )}

        {!isUser && !streaming && (confidence !== undefined || (sources && sources.length)) ? (
          <div className="mt-3 border-t border-slate-800 pt-2 text-xs text-slate-400">
            {confidence !== undefined ? (
              <div>
                置信度：<span className="text-slate-200">{confidence.toFixed(2)}</span>
              </div>
            ) : null}
            {sources && sources.length ? (
              <details className="mt-2">
                <summary className="cursor-pointer select-none text-slate-300">引用片段</summary>
                <ul className="mt-2 space-y-1 text-slate-300">
                  {sources.map((s, idx) => (
                    <li key={idx} className="whitespace-pre-wrap rounded bg-slate-950/40 p-2">
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
