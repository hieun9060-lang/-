import test from 'node:test';
import assert from 'node:assert/strict';
import { verifyAccess, resetAccessCache } from '../_lib/access.js';
import { handleRun } from '../api/run.js';
import { handleChat } from '../api/chat.js';

const TEAM = 'myteam.cloudflareaccess.com', AUD = 'aud-123';
const b64u = (buf) => Buffer.from(buf).toString('base64url');
const kp = await crypto.subtle.generateKey({ name: 'RSASSA-PKCS1-v1_5', modulusLength: 2048, publicExponent: new Uint8Array([1, 0, 1]), hash: 'SHA-256' }, true, ['sign', 'verify']);
const jwk = { ...(await crypto.subtle.exportKey('jwk', kp.publicKey)), kid: 'k1', alg: 'RS256', use: 'sig' };

async function token(over = {}, key = kp.privateKey, kid = 'k1') {
  const h = b64u(JSON.stringify({ alg: 'RS256', kid }));
  const claims = { iss: `https://${TEAM}`, aud: [AUD], exp: Math.floor(Date.now() / 1000) + 600, email: 'me@example.com', ...over };
  const p = b64u(JSON.stringify(claims));
  const sig = await crypto.subtle.sign('RSASSA-PKCS1-v1_5', key, new TextEncoder().encode(`${h}.${p}`));
  return `${h}.${p}.${b64u(sig)}`;
}
const env = { ACCESS_TEAM_DOMAIN: TEAM, ACCESS_AUD: AUD, GITHUB_TOKEN: 'ghp_x', GITHUB_REPO: 'me/repo', GITHUB_BRANCH: 'main', GEMINI_API_KEY: 'g' };
const calls = [];
const fakeFetch = async (url, init) => {
  calls.push([String(url), init]);
  if (String(url).includes('/cdn-cgi/access/certs')) return new Response(JSON.stringify({ keys: [jwk] }), { status: 200 });
  if (String(url).includes('/dispatches')) return new Response(null, { status: 204 });
  if (String(url).includes('generativelanguage')) return new Response(JSON.stringify({ candidates: [{ content: { parts: [{ text: '경쟁사는 모집 게시물이 많습니다.' }] } }] }), { status: 200 });
  return new Response('x', { status: 404 });
};
const req = (t, headers = {}, body = '{}') => new Request('https://x.pages.dev/api/run', { method: 'POST', body,
  headers: { 'Cf-Access-Jwt-Assertion': t, 'X-Requested-With': 'aeo-app', ...headers } });

test('accepts a valid Access token', async () => {
  resetAccessCache();
  const r = await verifyAccess(req(await token()), env, fakeFetch);
  assert.equal(r.ok, true); assert.equal(r.email, 'me@example.com');
});

test('rejects missing, expired, wrong audience, wrong issuer, forged signature, wrong alg', async () => {
  resetAccessCache();
  assert.equal((await verifyAccess(new Request('https://x/'), env, fakeFetch)).status, 401);
  assert.equal((await verifyAccess(req(await token({ exp: 1 })), env, fakeFetch)).ok, false);
  assert.equal((await verifyAccess(req(await token({ aud: ['other'] })), env, fakeFetch)).ok, false);
  assert.equal((await verifyAccess(req(await token({ iss: 'https://evil.cloudflareaccess.com' })), env, fakeFetch)).ok, false);
  const other = await crypto.subtle.generateKey({ name: 'RSASSA-PKCS1-v1_5', modulusLength: 2048, publicExponent: new Uint8Array([1, 0, 1]), hash: 'SHA-256' }, true, ['sign', 'verify']);
  assert.equal((await verifyAccess(req(await token({}, other.privateKey)), env, fakeFetch)).ok, false);
  const t = await token(); const [h, p, s] = t.split('.');
  const none = `${b64u(JSON.stringify({ alg: 'none', kid: 'k1' }))}.${p}.${s}`;
  assert.equal((await verifyAccess(req(none), env, fakeFetch)).ok, false);
  assert.equal((await verifyAccess(req('garbage'), env, fakeFetch)).ok, false);
});

test('not configured → 501, bad team domain refused', async () => {
  assert.equal((await verifyAccess(req(await token()), {}, fakeFetch)).status, 501);
  assert.equal((await verifyAccess(req(await token()), { ACCESS_TEAM_DOMAIN: 'evil.com', ACCESS_AUD: AUD }, fakeFetch)).status, 501);
});

test('run: dispatches the workflow only for authenticated, header-bearing requests', async () => {
  resetAccessCache(); calls.length = 0;
  const res = await handleRun({ request: req(await token()), env }, fakeFetch);
  assert.equal(res.status, 200);
  const d = calls.find((c) => c[0].includes('/dispatches'));
  assert.match(d[0], /repos\/me\/repo\/actions\/workflows\/monitor\.yml\/dispatches/);
  assert.equal(JSON.parse(d[1].body).ref, 'main');
  assert.equal((await handleRun({ request: req(await token(), { 'X-Requested-With': '' }), env }, fakeFetch)).status, 403);
  assert.equal((await handleRun({ request: new Request('https://x/', { method: 'POST' }), env }, fakeFetch)).status, 401);
  assert.equal((await handleRun({ request: req(await token()), env: { ...env, GITHUB_TOKEN: '' } }, fakeFetch)).status, 501);
  assert.equal((await handleRun({ request: req(await token()), env: { ...env, GITHUB_REPO: 'a b/../c' } }, fakeFetch)).status, 501);
});

test('chat: uses only the exported context, validates input', async () => {
  resetAccessCache(); calls.length = 0;
  const assets = { fetch: async () => new Response(JSON.stringify({ 오늘: '2026-10-06' }), { status: 200 }) };
  const ok = await handleChat({ request: req(await token(), {}, JSON.stringify({ messages: [{ role: 'user', content: '동향은?' }] })), env: { ...env, ASSETS: assets } }, fakeFetch);
  assert.equal(ok.status, 200); assert.equal((await ok.json()).by, 'Gemini');
  const g = calls.find((c) => c[0].includes('generativelanguage'));
  assert.ok(JSON.parse(g[1].body).contents[0].parts[0].text.includes('<data>'));
  assert.equal(g[1].headers['x-goog-api-key'], 'g'); assert.ok(!g[0].includes('key='));
  const bad = await handleChat({ request: req(await token(), {}, JSON.stringify({ messages: [{ role: 'system', content: 'x' }] })), env: { ...env, ASSETS: assets } }, fakeFetch);
  assert.equal(bad.status, 400);
  const nokey = await handleChat({ request: req(await token(), {}, '{"messages":[{"role":"user","content":"a"}]}'), env: { ...env, GEMINI_API_KEY: '', ASSETS: assets } }, fakeFetch);
  assert.equal(nokey.status, 501);
});
