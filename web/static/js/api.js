export class ApiError extends Error {
  constructor(message, status) { super(message); this.status = status; }
}

export async function api(path, { method = 'GET', body, params } = {}) {
  const url = new URL('/api' + path, location.origin);
  for (const [k, v] of Object.entries(params || {})) if (v !== undefined && v !== null && v !== '') url.searchParams.set(k, v);
  const res = await fetch(url, {
    method,
    headers: { 'X-Requested-With': 'aeo-app', ...(body ? { 'Content-Type': 'application/json' } : {}) },
    credentials: 'same-origin',
    body: body ? JSON.stringify(body) : undefined,
  });
  let data = null;
  try { data = await res.json(); } catch { /* 본문 없음 */ }
  if (res.status === 401 && path !== '/login') window.dispatchEvent(new Event('aeo:unauth'));
  if (!res.ok) {
    const d = data?.detail;
    const msg = typeof d === 'string' ? d : Array.isArray(d) ? '입력값을 확인하세요.' : '요청에 실패했습니다.';
    throw new ApiError(msg, res.status);
  }
  return data;
}
