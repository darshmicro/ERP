export class ApiError extends Error {
  constructor(public status: number, public body: any) {
    super(body?.message ?? `HTTP ${status}`);
  }
}

let csrf: string | null = sessionStorage.getItem("csrf");
export const setCsrf = (t: string | null) => {
  csrf = t;
  t ? sessionStorage.setItem("csrf", t) : sessionStorage.removeItem("csrf");
};

type Opts = { method?: string; body?: unknown; reason?: string; raw?: boolean; form?: FormData };

export async function api<T = any>(path: string, opts: Opts = {}): Promise<T> {
  const headers: Record<string, string> = {};
  if (csrf) headers["X-CSRF-Token"] = csrf;
  if (opts.reason) headers["X-Change-Reason"] = opts.reason;
  let body: BodyInit | undefined;
  if (opts.form) body = opts.form;
  else if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }
  const res = await fetch(`/api/v1${path}`, { method: opts.method ?? "GET", headers, body, credentials: "same-origin" });
  if (!res.ok) {
    let j: any = null;
    try { j = await res.json(); } catch { /* ignore */ }
    if (res.status === 401 && !path.startsWith("/auth/login")) window.dispatchEvent(new Event("merp:unauthenticated"));
    throw new ApiError(res.status, j);
  }
  if (opts.raw) return res as unknown as T;
  return res.json();
}

export const errText = (e: unknown) => {
  if (e instanceof ApiError) {
    const b = e.body;
    const d = Array.isArray(b?.details) ? ": " + b.details.map((x: any) => x.message ?? x).join("; ") : "";
    return (b?.message ?? e.message) + d + (b?.rule_id ? ` [${b.rule_id}]` : "");
  }
  return "Transaction could not be completed.";
};
