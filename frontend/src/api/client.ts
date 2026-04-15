/**
 * HTTP 基址：默认走 Vite 代理 `/api`；也可通过 `VITE_API_BASE` 指向完整后端 URL。
 */
export function getApiBase(): string {
  const raw = import.meta.env.VITE_API_BASE?.trim();
  if (raw) {
    return raw.replace(/\/$/, "");
  }
  return "/api";
}

export async function fetchHealth(): Promise<{ status: string }> {
  const res = await fetch(`${getApiBase()}/health`);
  if (!res.ok) {
    throw new Error(`health failed: ${res.status}`);
  }
  return (await res.json()) as { status: string };
}
