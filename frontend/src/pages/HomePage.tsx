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

type WorkflowEventItem = {
  id: string;
  time: string;
  node: string;
  updatedKeys: string[];
};

type DeepResearchResponse = {
  report_id: string;
  report_path: string;
  question: string;
  index_name: string;
  created_at: string;
  researcher_notes: string;
  analyst_notes: string;
  report_markdown: string;
};

function uid() {
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function nowTimeLabel() {
  const d = new Date();
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}:${String(
    d.getSeconds(),
  ).padStart(2, "0")}`;
}

export function HomePage() {
  const [backendOk, setBackendOk] = useState<boolean | null>(null);
  const [messages, setMessages] = useState<UiMessage[]>([]);
  const [input, setInput] = useState("");
  const [chatBusy, setChatBusy] = useState(false);
  const [retrievalStrategy, setRetrievalStrategy] = useState<
    "similarity" | "mmr" | "score_threshold" | "hybrid"
  >("similarity");
  const [scoreThreshold, setScoreThreshold] = useState(0.25);
  const [mmrLambda, setMmrLambda] = useState(0.65);
  const [hybridAlpha, setHybridAlpha] = useState(0.6);
  const [workflowMode, setWorkflowMode] = useState<"agent" | "task">("agent");
  const [guardrailMode, setGuardrailMode] = useState<"strict" | "relaxed">("relaxed");
  const [runMode, setRunMode] = useState<"chat" | "deep_research">("chat");
  const [includeWorkflowEvents, setIncludeWorkflowEvents] = useState(false);
  const [workflowEvents, setWorkflowEvents] = useState<WorkflowEventItem[]>([]);
  const [lastReportMeta, setLastReportMeta] = useState<{
    reportId: string;
    reportPath: string;
    createdAt: string;
    indexName: string;
  } | null>(null);
  const [threadId] = useState(() => `demo-${uid()}`);
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
    setWorkflowEvents([]);
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
        } else if (ev.type === "workflow_event") {
          setWorkflowEvents((prev) => [
            ...prev,
            {
              id: uid(),
              time: nowTimeLabel(),
              node: ev.node,
              updatedKeys: Array.isArray(ev.updated_keys) ? ev.updated_keys : [],
            },
          ]);
        } else if (ev.type === "done") {
          setMessages((prev) =>
            prev.map((m) => (m.id === assistantId ? { ...m, streaming: false } : m)),
          );
        }
      }
    };

    try {
      const qs = new URLSearchParams({
        retrieval_strategy: retrievalStrategy,
        score_threshold: String(scoreThreshold),
        mmr_lambda: String(mmrLambda),
        hybrid_alpha: String(hybridAlpha),
        workflow_mode: workflowMode,
        guardrail_mode: guardrailMode,
        thread_id: threadId,
        include_workflow_events: String(includeWorkflowEvents),
      });
      const res = await fetch(`${getApiBase()}/chat/stream?${qs.toString()}`, {
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

  async function runDeepResearch(question: string) {
    const assistantId = uid();
    setMessages((prev) => [
      ...prev,
      { id: uid(), role: "user", content: question },
      { id: assistantId, role: "assistant", content: "正在执行 Deep Research…", streaming: true },
    ]);
    setChatBusy(true);
    setWorkflowEvents([]);
    setLastReportMeta(null);

    try {
      const qs = new URLSearchParams({
        retrieval_strategy: retrievalStrategy,
        score_threshold: String(scoreThreshold),
        mmr_lambda: String(mmrLambda),
        hybrid_alpha: String(hybridAlpha),
      });
      const res = await fetch(`${getApiBase()}/deep-research?${qs.toString()}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
      });
      if (!res.ok) {
        const t = await res.text().catch(() => "");
        throw new Error(t || `请求失败：${res.status}`);
      }
      const data = (await res.json()) as DeepResearchResponse;
      const reportBody =
        `# Deep Research 完成\n\n` +
        `- report_id: ${data.report_id}\n` +
        `- created_at: ${data.created_at}\n` +
        `- index_name: ${data.index_name}\n` +
        `- report_path: ${data.report_path}\n\n` +
        `${data.report_markdown || "（未返回报告正文）"}`;

      setLastReportMeta({
        reportId: data.report_id,
        reportPath: data.report_path,
        createdAt: data.created_at,
        indexName: data.index_name,
      });
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId
            ? {
                ...m,
                streaming: false,
                content: reportBody,
              }
            : m,
        ),
      );
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId
            ? {
                ...m,
                streaming: false,
                content: `（Deep Research 失败：${msg}）`,
              }
            : m,
        ),
      );
    } finally {
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
            {chatBusy ? (
              <span className="text-xs text-sky-300">
                {runMode === "deep_research" ? "研究中…" : "生成中…"}
              </span>
            ) : null}
          </div>
          <div className="mt-3 grid grid-cols-1 gap-2 rounded-xl border border-slate-800/80 bg-slate-950/20 p-2 sm:grid-cols-7">
            <label className="flex flex-col gap-1 text-xs text-slate-300">
              运行模式
              <select
                value={runMode}
                onChange={(e) => setRunMode(e.target.value as "chat" | "deep_research")}
                disabled={chatBusy}
                className="rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100"
              >
                <option value="chat">chat</option>
                <option value="deep_research">deep_research</option>
              </select>
            </label>
            <label className="flex flex-col gap-1 text-xs text-slate-300">
              检索策略
              <select
                value={retrievalStrategy}
                onChange={(e) =>
                  setRetrievalStrategy(
                    e.target.value as "similarity" | "mmr" | "score_threshold" | "hybrid",
                  )
                }
                disabled={chatBusy}
                className="rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100"
              >
                <option value="similarity">similarity</option>
                <option value="mmr">mmr</option>
                <option value="score_threshold">score_threshold</option>
                <option value="hybrid">hybrid</option>
              </select>
            </label>
            <label className="flex flex-col gap-1 text-xs text-slate-300">
              工作流模式
              <select
                value={workflowMode}
                onChange={(e) => setWorkflowMode(e.target.value as "agent" | "task")}
                disabled={chatBusy || runMode === "deep_research"}
                className="rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100"
              >
                <option value="agent">agent</option>
                <option value="task">task</option>
              </select>
            </label>
            <label className="flex flex-col gap-1 text-xs text-slate-300">
              Guardrails
              <select
                value={guardrailMode}
                onChange={(e) => setGuardrailMode(e.target.value as "strict" | "relaxed")}
                disabled={chatBusy || runMode === "deep_research"}
                className="rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100"
              >
                <option value="relaxed">relaxed</option>
                <option value="strict">strict</option>
              </select>
            </label>
            <label className="flex flex-col gap-1 text-xs text-slate-300">
              事件流
              <select
                value={includeWorkflowEvents ? "on" : "off"}
                onChange={(e) => setIncludeWorkflowEvents(e.target.value === "on")}
                disabled={chatBusy || workflowMode !== "task" || runMode === "deep_research"}
                className="rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100 disabled:opacity-50"
              >
                <option value="off">off</option>
                <option value="on">on</option>
              </select>
            </label>
            <label className="flex flex-col gap-1 text-xs text-slate-300">
              score_threshold
              <input
                type="number"
                min={0}
                max={1}
                step={0.05}
                value={scoreThreshold}
                onChange={(e) => setScoreThreshold(Number(e.target.value || 0))}
                disabled={chatBusy || retrievalStrategy !== "score_threshold"}
                className="rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100 disabled:opacity-50"
              />
            </label>
            <label className="flex flex-col gap-1 text-xs text-slate-300">
              mmr_lambda
              <input
                type="number"
                min={0}
                max={1}
                step={0.05}
                value={mmrLambda}
                onChange={(e) => setMmrLambda(Number(e.target.value || 0))}
                disabled={chatBusy || (retrievalStrategy !== "mmr" && retrievalStrategy !== "hybrid")}
                className="rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100 disabled:opacity-50"
              />
            </label>
            <label className="flex flex-col gap-1 text-xs text-slate-300">
              hybrid_alpha
              <input
                type="number"
                min={0}
                max={1}
                step={0.05}
                value={hybridAlpha}
                onChange={(e) => setHybridAlpha(Number(e.target.value || 0))}
                disabled={chatBusy || retrievalStrategy !== "hybrid"}
                className="rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100 disabled:opacity-50"
              />
            </label>
          </div>

          {workflowMode === "task" && includeWorkflowEvents && runMode === "chat" ? (
            <div className="mt-2 rounded-lg border border-slate-800/80 bg-slate-950/20 p-2 text-xs text-slate-300">
              <div className="mb-1 text-slate-400">Workflow Events（thread_id: {threadId}）</div>
              <div className="max-h-24 overflow-y-auto space-y-1">
                {workflowEvents.length === 0 ? (
                  <div className="text-slate-500">等待事件…</div>
                ) : (
                  workflowEvents.map((event) => (
                    <div key={event.id} className="flex items-start gap-2">
                      <span className="text-emerald-300">●</span>
                      <span className="text-slate-400">{event.time}</span>
                      <span className="text-slate-200">{event.node}</span>
                      <span className="text-slate-500">
                        {event.updatedKeys.length > 0 ? event.updatedKeys.join(", ") : "no state updates"}
                      </span>
                    </div>
                  ))
                )}
              </div>
            </div>
          ) : null}

          {runMode === "deep_research" && lastReportMeta ? (
            <div className="mt-2 rounded-lg border border-slate-800/80 bg-slate-950/20 p-2 text-xs text-slate-300">
              <div className="mb-1 text-slate-400">Latest Deep Research Report</div>
              <div className="space-y-1">
                <div>
                  report_id: <code className="text-slate-100">{lastReportMeta.reportId}</code>
                </div>
                <div>
                  created_at: <code className="text-slate-100">{lastReportMeta.createdAt}</code>
                </div>
                <div>
                  index_name: <code className="text-slate-100">{lastReportMeta.indexName}</code>
                </div>
                <div>
                  report_path: <code className="text-slate-100">{lastReportMeta.reportPath}</code>
                </div>
              </div>
            </div>
          ) : null}

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
              if (runMode === "deep_research") {
                void runDeepResearch(text);
              } else {
                void sendStream(text);
              }
            }}
          >
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={
                backendOk
                  ? runMode === "deep_research"
                    ? "输入研究问题…"
                    : "输入你的问题…"
                  : "等待后端连接…"
              }
              disabled={!canChat}
              className="min-w-0 flex-1 rounded-xl border border-slate-800 bg-slate-950/40 px-3 py-2 text-sm text-slate-100 outline-none ring-sky-500/40 placeholder:text-slate-500 focus:border-sky-500/50 focus:ring"
            />
            <button
              type="submit"
              disabled={!canChat || !input.trim()}
              className="rounded-xl bg-sky-600 px-4 py-2 text-sm font-medium text-white shadow hover:bg-sky-500 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {runMode === "deep_research" ? "研究" : "发送"}
            </button>
            <button
              type="button"
              disabled={!chatBusy || runMode === "deep_research"}
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
