/**
 * 主页面：上传 + 聊天（SSE 流式）+ Markdown 展示。
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { getApiBase, fetchHealth } from "../api/client";
import { MessageBubble } from "../components/MessageBubble";
import { UploadPanel } from "../components/UploadPanel";
import { parseSseDataLines, type SseJsonEvent } from "../lib/sse";

type UiMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  streaming?: boolean;
  confidence?: number;
  sources?: string[];
};

function uid() {
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function HomePage() {
  const [backendOk, setBackendOk] = useState<boolean | null>(null);
  const [messages, setMessages] = useState<UiMessage[]>([]);
  const [input, setInput] = useState("");
  const [chatBusy, setChatBusy] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);

  const canChat = useMemo(() => backendOk === true && !chatBusy, [backendOk, chatBusy]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        await fetchHealth();
        if (!cancelled) setBackendOk(true);
      } catch {
        if (!cancelled) setBackendOk(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, chatBusy]);

  async function sendStream(userText: string) {
    const controller = new AbortController();
    abortRef.current = controller;

    const assistantId = uid();
    setMessages((prev) => [
      ...prev,
      { id: uid(), role: "user", content: userText },
      { id: assistantId, role: "assistant", content: "", streaming: true },
    ]);

    setChatBusy(true);
    let sseBuf = "";

    const applyEvents = (events: SseJsonEvent[]) => {
      for (const ev of events) {
        if (ev.type === "token") {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId
                ? { ...m, content: m.content + (ev.content ?? "") }
                : m,
            ),
          );
        } else if (ev.type === "metadata") {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId
                ? {
                    ...m,
                    streaming: false,
                    confidence: ev.confidence,
                    sources: ev.sources ?? [],
                  }
                : m,
            ),
          );
        } else if (ev.type === "error") {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId
                ? {
                    ...m,
                    streaming: false,
                    content: m.content
                      ? `${m.content}\n\n（流式错误：${ev.message}）`
                      : `（流式错误：${ev.message}）`,
                  }
                : m,
            ),
          );
        } else if (ev.type === "done") {
          setMessages((prev) =>
            prev.map((m) => (m.id === assistantId ? { ...m, streaming: false } : m)),
          );
        }
      }
    };

    try {
      const res = await fetch(`${getApiBase()}/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: userText }),
        signal: controller.signal,
      });

      if (!res.ok || !res.body) {
        const t = await res.text().catch(() => "");
        throw new Error(t || `请求失败：${res.status}`);
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        sseBuf += decoder.decode(value, { stream: true });
        const parsed = parseSseDataLines(sseBuf);
        sseBuf = parsed.rest;
        applyEvents(parsed.events);
      }

      const tail = parseSseDataLines(sseBuf);
      applyEvents(tail.events);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId
            ? {
                ...m,
                streaming: false,
                content: m.content ? `${m.content}\n\n（请求失败：${msg}）` : `（请求失败：${msg}）`,
              }
            : m,
        ),
      );
    } finally {
      abortRef.current = null;
      setChatBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-6xl px-4 py-6">
      <header className="mb-6 flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-slate-50">
            LangGraph RAG Demo
          </h1>
          <p className="mt-1 text-sm text-slate-400">
            上传文档（Word / PDF / 文本）→ 向量检索 → Agent 回答（SSE）
          </p>
        </div>
        <div className="text-xs text-slate-400">
          后端：
          {backendOk === null ? (
            <span className="text-slate-300">检测中…</span>
          ) : backendOk ? (
            <span className="text-emerald-300">已连接（{getApiBase()}）</span>
          ) : (
            <span className="text-rose-300">
              未连接（请先启动后端，并确保 Vite 代理 `/api` 可用）
            </span>
          )}
        </div>
      </header>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="lg:col-span-1">
          <UploadPanel disabled={backendOk !== true} />
        </div>

        <section className="lg:col-span-2 rounded-2xl border border-slate-800 bg-slate-900/30 p-4 shadow">
          <div className="flex items-center justify-between gap-3">
            <h2 className="text-base font-semibold text-slate-100">对话</h2>
            {chatBusy ? <span className="text-xs text-sky-300">生成中…</span> : null}
          </div>

          <div className="mt-4 h-[52vh] overflow-y-auto rounded-xl border border-slate-800/80 bg-slate-950/30 p-3">
            {messages.length === 0 ? (
              <div className="p-6 text-sm text-slate-400">
                先上传文档，然后在下方输入问题。本页使用 <code className="text-slate-200">fetch</code>{" "}
                读取 SSE 流并实时渲染 Markdown。
              </div>
            ) : (
              <div className="space-y-3">
                {messages.map((m) => (
                  <MessageBubble
                    key={m.id}
                    role={m.role}
                    content={m.content}
                    streaming={m.streaming}
                    confidence={m.confidence}
                    sources={m.sources}
                  />
                ))}
                <div ref={bottomRef} />
              </div>
            )}
          </div>

          <form
            className="mt-3 flex gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              const text = input.trim();
              if (!text || !canChat) return;
              setInput("");
              void sendStream(text);
            }}
          >
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={backendOk ? "输入你的问题…" : "等待后端连接…"}
              disabled={!canChat}
              className="min-w-0 flex-1 rounded-xl border border-slate-800 bg-slate-950/40 px-3 py-2 text-sm text-slate-100 outline-none ring-sky-500/40 placeholder:text-slate-500 focus:border-sky-500/50 focus:ring"
            />
            <button
              type="submit"
              disabled={!canChat || !input.trim()}
              className="rounded-xl bg-sky-600 px-4 py-2 text-sm font-medium text-white shadow hover:bg-sky-500 disabled:cursor-not-allowed disabled:opacity-40"
            >
              发送
            </button>
            <button
              type="button"
              disabled={!chatBusy}
              onClick={() => abortRef.current?.abort()}
              className="rounded-xl border border-slate-800 bg-slate-950/30 px-3 py-2 text-sm text-slate-200 hover:bg-slate-900 disabled:cursor-not-allowed disabled:opacity-40"
            >
              停止
            </button>
          </form>
        </section>
      </div>
    </div>
  );
}
