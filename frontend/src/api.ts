export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) { super(message); this.status = status }
}
export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api${path}`, { ...init, credentials: 'include', headers: { Accept: 'application/json', ...init.headers } })
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null)
    const detail = body && typeof body === 'object' && 'detail' in body ? body.detail : null
    const message = typeof detail === 'string' ? detail : Array.isArray(detail) ? detail.map((x: {msg?: string}) => x.msg || 'Ошибка поля').join('; ') : `Ошибка HTTP ${response.status}`
    if (response.status === 401 || response.status === 403) window.dispatchEvent(new CustomEvent('session-expired'))
    throw new ApiError(response.status, message)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}
export function write<T>(path: string, method: 'POST' | 'PATCH', body: unknown) {
  return request<T>(path, { method, headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body) })
}
export type City = {id: string; name: string; yandex_region_id: string | null}
export type Category = {id: string; name: string}
export type Phrase = {id: string; phrase: string; city_id: string | null; category_id: string; enabled: boolean}
export type Run = {id: string; status: string; method: string; started_at: string; error: string | null}
export type Topic = {category_id: string; category_name: string; expected_queries: number; complete: boolean; average_frequency?: number | null; successful_queries?: number; current_total?: number | null; previous_total?: number | null; delta?: number | null; delta_percent?: number | null; trend?: string; compared_queries?: number}
export type Dashboard = {items: Topic[]; updated_at: string | null; catalog_changed: boolean | null; has_data: boolean}
export type Daily = {categories: Topic[]; current_date: string; previous_date: string; comparison_status: string; aggregation_note: string}
