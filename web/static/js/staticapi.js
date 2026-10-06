/* 정적 사이트 모드: 서버 API 대신 data/*.json 을 읽는다. 수정 기능은 설정 파일(GitHub)로 안내한다. */
import { ApiError } from './errors.js';
import { META } from './mode.js';
import { addDays, periodRange } from './util.js';

const cache = new Map();

async function load(path, { optional = false } = {}) {
  if (cache.has(path)) return cache.get(path);
  let res;
  try { res = await fetch(`/data/${path}`, { cache: 'no-cache', credentials: 'same-origin' }); }
  catch {
    // 로그인(Access) 만료 시 로그인 페이지로 리다이렉트되며 요청이 실패한다 → 한 번 새로고침해 다시 로그인
    if (!sessionStorage.getItem('aeo-reloaded')) { sessionStorage.setItem('aeo-reloaded', '1'); location.reload(); }
    throw new ApiError('데이터를 불러오지 못했습니다. 로그인이 만료되었다면 페이지를 새로고침하세요.', 0);
  }
  if (res.status === 404 && optional) return null;
  const ct = res.headers.get('content-type') || '';
  if (res.redirected || !ct.includes('json')) {
    if (optional && res.status === 404) return null;
    // Cloudflare Access 로그인 페이지로 돌려보내졌거나 파일이 없음
    if (!sessionStorage.getItem('aeo-reloaded')) { sessionStorage.setItem('aeo-reloaded', '1'); location.reload(); }
    throw new ApiError('로그인이 만료되었습니다. 페이지를 새로고침하세요.', 401);
  }
  sessionStorage.removeItem('aeo-reloaded');
  if (!res.ok) throw new ApiError('데이터를 불러오지 못했습니다.', res.status);
  const data = await res.json();
  cache.set(path, data);
  return data;
}

const READ_ONLY = '이 화면은 보기 전용입니다. 회사·채널·질문·설정은 GitHub의 설정 파일(config/monitor.yaml)에서 고칩니다.';

function emptyCalendar(boot, view, anchor) {
  const [start, end] = periodRange(view, anchor);
  const comps = boot.companies.filter((c) => c.channels.length);
  return {
    view, anchor, start, end, total: 0, daily: {}, hasChannels: comps.length > 0,
    companies: comps.map((c) => ({ id: c.id, name: c.name, role: c.role, color: c.color, count: 0, issue: '', summary: '', highlight: '', summaryBy: '', topics: {}, posts: [] })),
  };
}
function emptyStats(range, anchor, platform) {
  const [start, end] = periodRange(range, anchor);
  return { range, anchor, start, end, total: 0, prevTotal: 0, byPlatform: {}, topics: [], platform,
    graph: { start, end, platform, monthly: false, buckets: [], total: 0, byPlatform: {}, byTopic: [], companies: [] } };
}

export function filterPosts(posts, { company, topic, days, q }, today) {
  const cutoff = !days || days === 'all' ? '0000-00-00' : addDays(today, -(Number(days) - 1));
  const ql = (q || '').trim().toLowerCase().slice(0, 80);
  return posts.filter((p) => p.date >= cutoff && (!company || p.company_id === company) && (!topic || p.topic === topic)
    && (!ql || p.title.toLowerCase().includes(ql) || (p.snippet || '').toLowerCase().includes(ql)));
}

export async function evidenceCsv(params) {
  const boot = await load('bootstrap.json');
  const { items } = await load('posts.json');
  const rows = filterPosts(items, params, boot.today);
  const cell = (v) => { let s = String(v ?? ''); if (/^[=+\-@]/.test(s)) s = "'" + s; return `"${s.replace(/"/g, '""')}"`; };
  const lines = [['날짜', '회사', '채널', '주제', '제목', '요약', '원문 주소'].map(cell).join(',')];
  rows.forEach((p) => lines.push([p.date, p.company, p.platform, p.topic, p.title, p.snippet, p.url].map(cell).join(',')));
  return new Blob(['﻿' + lines.join('\r\n')], { type: 'text/csv;charset=utf-8' });
}

async function viaFunction(path, body, fallbackMsg) {
  let res;
  try {
    res = await fetch(path, { method: 'POST', credentials: 'same-origin', body: JSON.stringify(body),
      headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'aeo-app' } });
  } catch { throw new ApiError(fallbackMsg, 0); }
  let data = null;
  try { data = await res.json(); } catch { /* 본문 없음 */ }
  if (!res.ok) throw new ApiError(data?.detail || fallbackMsg, res.status);
  return data;
}

export async function staticApi(path, { method = 'GET', body, params = {} } = {}) {
  if (method === 'POST' && path === '/run') {
    return viaFunction('/api/run', { kind: body?.kind || 'all' },
      `실행 요청 기능이 설정되지 않았습니다. GitHub의 Actions 탭 → "Monitor" → Run workflow 로 직접 실행하세요. (${META.repo ? `https://github.com/${META.repo}/actions` : ''})`);
  }
  if (method === 'POST' && path === '/chat') {
    return viaFunction('/api/chat', body, 'AI 챗봇은 Cloudflare 추가 설정이 필요합니다 (README의 "선택 기능" 참고).');
  }
  if (method !== 'GET') throw new ApiError(READ_ONLY, 405);

  const boot = await load('bootstrap.json');
  if (path === '/me') return { authenticated: true, noAuth: true };
  if (path === '/bootstrap') return boot;
  if (path === '/calendar') {
    const { view, anchor } = params;
    const [start] = periodRange(view, anchor);
    const d = await load(`calendar/${view}/${start}.json`, { optional: true });
    return d ? { ...d, anchor } : emptyCalendar(boot, view, anchor);
  }
  if (path === '/stats') {
    const { range, anchor, platform = 'all' } = params;
    const [start] = periodRange(range, anchor);
    const d = await load(`stats/${range}/${platform}/${start}.json`, { optional: true });
    return d ? { ...d, anchor } : emptyStats(range, anchor, platform);
  }
  if (path === '/evidence') {
    const { items, topics } = await load('posts.json');
    const rows = filterPosts(items, params, boot.today);
    const off = Number(params.offset || 0), lim = Math.max(1, Math.min(Number(params.limit || 50), 200));
    return { total: rows.length, items: rows.slice(off, off + lim), topics };
  }
  if (path === '/questions') return load('questions.json');
  if (path === '/settings') return load('settings.json');
  if (path === '/analysis') {
    const { kind, anchor } = params;
    const [start, end] = periodRange(kind, anchor);
    const report = await load(`analysis/${kind}/${start}.json`, { optional: true });
    return { kind, anchor, start, end, report, ai: true };
  }
  if (path === '/jobs/latest') { const m = await load('meta.json'); return { job: m.job, running: false, recent: m.job ? [m.job] : [] }; }
  if (path === '/aeo/index') return (await load('aeo/index.json', { optional: true })) || { days: [], latest: null };
  const m = path.match(/^\/aeo\/day\/(\d{4}-\d{2}-\d{2})$/);
  if (m) {
    const d = await load(`aeo/day/${m[1]}.json`, { optional: true });
    if (!d) throw new ApiError('해당 날짜의 AI 언급 데이터가 없습니다.', 404);
    return d;
  }
  throw new ApiError('지원하지 않는 요청입니다.', 404);
}
