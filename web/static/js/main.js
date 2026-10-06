import { api } from './api.js';
import { $, $$, esc, ICON, toast, spinner, dialog, korDate } from './util.js';
import { renderCalendar } from './calendar.js';
import { renderStats } from './stats.js';
import { renderEvidence } from './evidence.js';
import { renderManage } from './manage.js';
import { renderAnalysis } from './analysis.js';
import { renderAeo } from './aeo.js';
import { renderSettings } from './settings.js';
import { openChat } from './chat.js';

const TABS = [['calendar', '리서치 캘린더'], ['stats', '리서치 통계'], ['evidence', '근거 자료'], ['manage', '수집 관리'], ['analysis', 'AI 분석'], ['aeo', 'AI 언급']];
const RENDER = { calendar: renderCalendar, stats: renderStats, evidence: renderEvidence, manage: renderManage, analysis: renderAnalysis, aeo: renderAeo };
const app = $('#app');
const ctx = { boot: null, state: null, goto, reloadBoot, runNow, refresh: () => renderTab() };
let tab = 'calendar';
let poller = null;

function initState() {
  const t = ctx.boot.today;
  ctx.state = {
    cal: { view: 'day', anchor: t }, stats: { range: 'month', anchor: t, platform: 'all', mode: 'total' },
    evidence: { company: '', topic: '', days: 'all', q: '' }, analysis: { kind: 'week', anchor: t },
    aeo: { date: '', sub: 'insight', qFilter: 'all', qEngine: 'all', qText: '' },
  };
}

async function reloadBoot() {
  const old = ctx.boot;
  ctx.boot = await api('/bootstrap');
  if (old) ctx.boot.today = old.today;
  return ctx.boot;
}

function login() {
  app.innerHTML = `<div class="card login"><div class="eyebrow">기숙학원 모니터링</div><h2>로그인</h2>
    <form id="lf"><input type="password" id="pw" placeholder="비밀번호" autocomplete="current-password" required aria-label="비밀번호">
    <div class="err-msg" id="lerr" role="alert"></div><button class="btn primary" style="width:100%;justify-content:center" type="submit">로그인</button></form></div>`;
  $('#pw').focus();
  $('#lf').onsubmit = async (e) => {
    e.preventDefault();
    try { await api('/login', { method: 'POST', body: { password: $('#pw').value } }); start(); }
    catch (err) { $('#lerr').textContent = err.message; $('#pw').select(); }
  };
}

function shell() {
  const b = ctx.boot, g = b.goal || {};
  app.innerHTML = `<div class="wrap">
    <div class="page-head"><div><div class="eyebrow">${esc(b.workspace.name || '')}</div><h1>${esc(b.workspace.title || '기숙학원 모니터링')}</h1></div>
      <div class="row"><button class="btn sm" id="theme" aria-label="라이트/다크 전환">◐ 화면 모드</button><button class="btn sm" id="logout">${ICON.logout} 로그아웃</button></div></div>
    <div class="card pad"><div class="goal"><div><div class="eyebrow">확정 리서치</div><h2>${esc(g.title || '')}</h2><p>${esc(g.desc || '')}</p></div>
      <div class="row"><button class="btn" id="chat">${ICON.chat} AI 챗봇</button><button class="btn primary" id="run">${ICON.play} 지금 실행</button></div></div>
      <div id="jobbar"></div></div>
    <div class="card" style="margin-top:14px"><div class="tabs" role="tablist">${TABS.map(([k, n]) => `<button class="tab" role="tab" data-tab="${k}" aria-selected="${k === tab}">${n}</button>`).join('')}</div><div class="view" id="view"></div></div>
    <details class="card acc" id="settings" style="margin-top:14px"><summary>${ICON.gear} 운영 설정 ${ICON.chev}</summary><div id="setbody"></div></details></div>`;
  $('#logout').onclick = async () => { await api('/logout', { method: 'POST' }); location.reload(); };
  $('#theme').onclick = () => {
    const r = document.documentElement;
    const cur = r.getAttribute('data-theme') || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
    const n = cur === 'dark' ? 'light' : 'dark';
    r.setAttribute('data-theme', n);
    try { localStorage.setItem('aeo-theme', n); } catch { /* 저장 불가 환경 */ }
  };
  $('#chat').onclick = () => openChat();
  $('#run').onclick = () => runNow('all');
  $$('.tab').forEach((t) => t.onclick = () => goto(t.dataset.tab));
  $('#settings').addEventListener('toggle', (e) => { if (e.target.open) renderSettings($('#setbody'), ctx); });
  showJob(ctx.boot.job, ctx.boot.running);
}

function goto(t) {
  tab = t;
  try { history.replaceState(null, '', '#' + t); } catch { /* noop */ }
  $$('.tab').forEach((x) => x.setAttribute('aria-selected', x.dataset.tab === t));
  renderTab();
}
function renderTab() { const v = $('#view'); v.onclick = null; RENDER[tab](v, ctx); }

const KIND = { all: '전체 수집·측정', content: '채널 수집', ai: 'AI 언급 측정', analysis: '분석' };
function showJob(job, running) {
  const bar = $('#jobbar');
  if (!bar) return;
  $('#run')?.toggleAttribute('disabled', !!running);
  if (!job) { bar.innerHTML = '<div class="sub" style="margin-top:8px">아직 실행 기록이 없습니다. 매일 설정된 시각에 자동 실행되며, 지금 실행으로 바로 시작할 수도 있습니다.</div>'; return; }
  const when = (job.started_at || '').replace('T', ' ').slice(5, 16);
  if (running || job.status === 'running') bar.innerHTML = `<div class="jobbar">${spinner}<span><b>${KIND[job.kind] || job.kind}</b> 진행 중 — ${esc(job.progress || '시작하는 중')}</span></div>`;
  else bar.innerHTML = `<div class="jobbar ${job.status === 'done' ? 'ok' : 'err'}"><span>마지막 실행 ${esc(when)} · ${KIND[job.kind] || job.kind} · ${job.status === 'done' ? '완료' : '문제 있음'}${job.progress && job.progress !== '완료' ? '<div class="sub" style="color:inherit">' + esc(job.progress) + '</div>' : ''}</span></div>`;
}

async function pollJob() {
  clearInterval(poller);
  poller = setInterval(async () => {
    try {
      const r = await api('/jobs/latest');
      showJob(r.job, r.running);
      if (!r.running) {
        clearInterval(poller);
        toast(r.job?.status === 'done' ? '실행이 끝났습니다.' : '실행이 끝났지만 일부 문제가 있습니다. 상단 상태를 확인하세요.', r.job?.status === 'done' ? '' : 'err');
        await reloadBoot();
        renderTab();
      }
    } catch { /* 일시적 오류는 다음 주기에 재시도 */ }
  }, 3000);
}

async function runNow(kind = 'all') {
  try {
    await api('/run', { method: 'POST', body: { kind } });
    showJob({ kind, status: 'running', progress: '시작하는 중', started_at: '' }, true);
    pollJob();
  } catch (e) { toast(e.message, 'err'); }
}

async function start() {
  try {
    const me = await api('/me');
    if (!me.authenticated) return login();
    await reloadBoot();
  } catch (e) { app.innerHTML = `<div class="empty"><b>서버에 연결하지 못했습니다</b>${esc(e.message)}</div>`; return; }
  initState();
  const h = location.hash.replace('#', '');
  if (RENDER[h]) tab = h;
  shell();
  renderTab();
  if (ctx.boot.running) pollJob();
}

window.addEventListener('aeo:unauth', login);
try { const t = localStorage.getItem('aeo-theme'); if (t) document.documentElement.setAttribute('data-theme', t); } catch { /* noop */ }
if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js').catch(() => {});
start();
