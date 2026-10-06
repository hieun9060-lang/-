// Cloudflare Access 가 붙여 주는 로그인 토큰(JWT)을 검증한다.
// Access 앞단 없이 이 함수가 인터넷에 그대로 노출되면 누구나 호출할 수 있으므로, 검증에 실패하면 거부한다.
const TEAM_RE = /^[a-z0-9-]+(\.[a-z0-9-]+)*\.cloudflareaccess\.com$/;
let jwksCache = { at: 0, team: '', keys: null };

function b64uToBytes(s) {
  const b = atob(s.replace(/-/g, '+').replace(/_/g, '/').padEnd(Math.ceil(s.length / 4) * 4, '='));
  return Uint8Array.from(b, (c) => c.charCodeAt(0));
}
const utf8 = (bytes) => new TextDecoder().decode(bytes);

async function getKeys(team, fetchImpl) {
  if (jwksCache.keys && jwksCache.team === team && Date.now() - jwksCache.at < 10 * 60 * 1000) return jwksCache.keys;
  const res = await fetchImpl(`https://${team}/cdn-cgi/access/certs`);
  if (!res.ok) throw new Error('certs');
  const { keys } = await res.json();
  jwksCache = { at: Date.now(), team, keys };
  return keys;
}

export function resetAccessCache() { jwksCache = { at: 0, team: '', keys: null }; }

export async function verifyAccess(request, env, fetchImpl = fetch) {
  const team = (env.ACCESS_TEAM_DOMAIN || '').trim().toLowerCase();
  const aud = (env.ACCESS_AUD || '').trim();
  if (!TEAM_RE.test(team) || !aud) {
    return { ok: false, status: 501, detail: 'Cloudflare Access 설정(ACCESS_TEAM_DOMAIN, ACCESS_AUD)이 필요합니다. README의 "선택 기능"을 참고하세요.' };
  }
  const token = request.headers.get('Cf-Access-Jwt-Assertion');
  if (!token) return { ok: false, status: 401, detail: '로그인이 필요합니다.' };
  try {
    const [h, p, sig] = token.split('.');
    if (!h || !p || !sig) throw new Error('format');
    const header = JSON.parse(utf8(b64uToBytes(h)));
    if (header.alg !== 'RS256') throw new Error('alg');
    const jwk = (await getKeys(team, fetchImpl)).find((k) => k.kid === header.kid);
    if (!jwk) throw new Error('kid');
    const key = await crypto.subtle.importKey('jwk', jwk, { name: 'RSASSA-PKCS1-v1_5', hash: 'SHA-256' }, false, ['verify']);
    const valid = await crypto.subtle.verify('RSASSA-PKCS1-v1_5', key, b64uToBytes(sig), new TextEncoder().encode(`${h}.${p}`));
    if (!valid) throw new Error('sig');
    const claims = JSON.parse(utf8(b64uToBytes(p)));
    const now = Math.floor(Date.now() / 1000);
    const auds = Array.isArray(claims.aud) ? claims.aud : [claims.aud];
    if (!(claims.exp > now) || (claims.nbf && claims.nbf > now + 60) || claims.iss !== `https://${team}` || !auds.includes(aud)) throw new Error('claims');
    return { ok: true, email: claims.email || '' };
  } catch {
    return { ok: false, status: 401, detail: '로그인 정보를 확인할 수 없습니다. 페이지를 새로고침해 다시 로그인하세요.' };
  }
}

export const json = (data, status = 200) => new Response(JSON.stringify(data), {
  status, headers: { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' } });

export async function guard(request, env, fetchImpl = fetch) {
  const a = await verifyAccess(request, env, fetchImpl);
  if (!a.ok) return json({ detail: a.detail }, a.status);
  if (request.headers.get('X-Requested-With') !== 'aeo-app') return json({ detail: '잘못된 요청입니다.' }, 403);
  return null;
}
