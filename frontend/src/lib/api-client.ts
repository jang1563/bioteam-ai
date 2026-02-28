// API client — fetch wrapper with auth header and base URL

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
  ) {
    super(detail);
    this.name = "ApiError";
  }
}

function getHeaders(): HeadersInit {
  const headers: HeadersInit = { "Content-Type": "application/json" };
  const token =
    typeof window !== "undefined"
      ? localStorage.getItem("bioteam_api_key")
      : null;
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  return headers;
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  retries = 0,
): Promise<T> {
  const url = `${API_BASE}${path}`;
  const res = await fetch(url, {
    ...options,
    headers: { ...getHeaders(), ...(options.headers ?? {}) },
  });

  // Rate limited — retry with backoff (max 2 retries)
  if (res.status === 429 && retries < 2) {
    const retryAfter = parseInt(res.headers.get("Retry-After") ?? "2", 10);
    const delay = Math.min(retryAfter * 1000, 10_000);
    await new Promise((r) => setTimeout(r, delay));
    return request<T>(path, options, retries + 1);
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    if ((res.status === 401 || res.status === 403) && typeof window !== "undefined") {
      window.dispatchEvent(
        new CustomEvent("bioteam:auth-error", { detail: { status: res.status, path } }),
      );
    }
    throw new ApiError(res.status, body.detail ?? res.statusText);
  }

  // 204 No Content
  if (res.status === 204) return undefined as T;

  return res.json();
}

export const api = {
  get: <T>(path: string) => request<T>(path),

  post: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: "POST",
      body: body != null ? JSON.stringify(body) : undefined,
    }),

  put: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: "PUT",
      body: body != null ? JSON.stringify(body) : undefined,
    }),

  patch: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: "PATCH",
      body: body != null ? JSON.stringify(body) : undefined,
    }),

  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
};

export { ApiError, API_BASE };
