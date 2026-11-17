// REST client for the Adrobot T3 FastAPI backend (proxy to Keitaro Admin API).
export const API_BASE_URL: string =
  (import.meta.env['VITE_API_URL'] as string | undefined) ?? "http://localhost:8000";

export type Campaign = {
  id: number;
  name: string;
  geo: string;
  offer_id: number;
  keitaro_campaign_id?: number | null;
  keitaro_id?: number | null;
  keitaro_url?: string | null;
  keitaro_streams_url?: string | null;
  view_in_kt_url?: string | null;
  created_at: string;
};
export type CampaignInput = { name: string; geo: string; offer_id: number };

export type StreamOffer = { id: number; name: string; weight: number; is_pinned: boolean; status: "active" | "removed" };
export type Stream = {
  id: number; name: string; type: string; weight: number;
  schema?: string | null; action_type?: string | null;
  offers?: StreamOffer[] | null; is_dirty?: boolean; keitaro_campaign_id?: number;
};
export type StreamsResponse = Stream[] | { streams: Stream[]; campaign?: Campaign; keitaro_url?: string; view_in_kt_url?: string };
export type Offer = { id: number; name: string; group_id?: number; state?: string };

export const GEOS = [
  ["US", "США"], ["GB", "Великобритания"], ["DE", "Германия"], ["FR", "Франция"],
  ["ES", "Испания"], ["IT", "Италия"], ["PL", "Польша"], ["BR", "Бразилия"],
  ["KZ", "Казахстан"], ["RU", "Россия"],
] as const;

async function extractError(res: Response): Promise<string> {
  try {
    const body = await res.json();
    const e = body?.detail ?? body?.error ?? body?.message;
    if (typeof e === "string") return e;
    if (e) return JSON.stringify(e);
  } catch { /* ignore */ }
  return `Ошибка ${res.status} ${res.statusText}`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
    throw new Error(`Бэкенд недоступен (${API_BASE_URL})`);
  }
  if (!res.ok) throw new Error(await extractError(res));
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => undefined);
  if (data && typeof data === "object" && "success" in data && data.success === false) {
    throw new Error(String((data as { error?: unknown; detail?: unknown }).detail ?? (data as { error?: unknown }).error ?? "Неизвестная ошибка"));
  }
  return data as T;
}

export const keitaroId = (c: Campaign) => c.keitaro_campaign_id ?? c.keitaro_id ?? null;
export const ktStreamsUrl = (c?: Campaign | null) =>
  c ? c.view_in_kt_url ?? c.keitaro_streams_url ?? c.keitaro_url ?? null : null;

export const createCampaign = (data: CampaignInput) =>
  request<unknown>("/api/campaigns", { method: "POST", body: JSON.stringify(data) });
export const getCampaigns = () => request<Campaign[]>("/api/campaigns");
export const updateCampaign = (id: number, data: Partial<CampaignInput>) =>
  request<Campaign>(`/api/campaigns/${id}`, { method: "PUT", body: JSON.stringify(data) });
export const deleteCampaign = (id: number) =>
  request<unknown>(`/api/campaigns/${id}`, { method: "DELETE" });

const s = (id: number) => `/api/campaigns/${id}/streams`;
export const getStreams = (id: number) => request<StreamsResponse>(s(id));
export const syncStreams = (id: number) => request<StreamsResponse>(`${s(id)}/sync`, { method: "POST" });
export const getOffers = () => request<Offer[]>("/api/offers");
export const addOffer = (id: number, sid: number, offer_id: number) =>
  request<unknown>(`${s(id)}/${sid}/offers`, { method: "POST", body: JSON.stringify({ offer_id }) });
export const removeOffer = (id: number, sid: number, oid: number) =>
  request<unknown>(`${s(id)}/${sid}/offers/${oid}`, { method: "DELETE" });
export const restoreOffer = (id: number, sid: number, oid: number) =>
  request<unknown>(`${s(id)}/${sid}/offers/${oid}/restore`, { method: "POST" });
export const pinOffer = (id: number, sid: number, oid: number, is_pinned: boolean) =>
  request<unknown>(`${s(id)}/${sid}/offers/${oid}/pin`, { method: "PATCH", body: JSON.stringify({ is_pinned }) });
export const publishStream = (id: number, sid: number) =>
  request<unknown>(`${s(id)}/${sid}/publish`, { method: "POST" });
export const cancelStream = (id: number, sid: number) =>
  request<unknown>(`${s(id)}/${sid}/cancel`, { method: "POST" });

export const errText = (e: unknown) => (e instanceof Error ? e.message : String(e));
export const fieldClass =
  "h-10 w-full rounded-lg border border-input bg-secondary px-3 text-foreground outline-none transition-shadow focus:border-ring focus:ring-2 focus:ring-ring/30";
