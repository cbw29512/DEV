export type CollectorItem = {
  id: number;
  url: string;
  vendor: string;
  exam: string;
  status: string;
  reason: string | null;
  sha256: string | null;
  saved_path: string | null;
  created_ts: number;
};

const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8080";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
  });

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`HTTP ${res.status} ${res.statusText}${text ? ` — ${text}` : ""}`);
  }

  return (await res.json()) as T;
}

export async function apiHealth(): Promise<{ ok: boolean }> {
  return request("/api/health");
}

export async function apiList(): Promise<{ items: CollectorItem[] }> {
  return request("/api/list");
}

export async function apiAdd(input: { url: string; vendor: string; exam: string }): Promise<{ ok: boolean; status?: string; reason?: string }> {
  return request("/api/add", {
    method: "POST",
    body: JSON.stringify(input),
  });
}
