import { api } from './api.js';
import { esc, ROLE, PLATFORM, colorVar, rangeLabel, shift, hbars, ICON, korDate, shortDate } from './util.js';

function seriesLabel(g, i) {
  const b = g.buckets[i];
  return g.monthly ? `${b.slice(0, 4)}년 ${Number(b.slice(5))}월` : korDate(b);
}

function pills(g) {
  const max = Math.max(1, ...g.companies.map((c) => c.total));
  return `<div class="pills">${g.companies.map((c) => `
    <div class="pillcol" style="--cc:${colorVar(c.color)}" title="${esc(c.name)} ${c.total}건">
      <div class="mini">${c.total}건</div>
      <div class="pill"><i style="height:${Math.max(c.total ? 8 : 0, (100 * c.total) / max)}%"></i></div>
      <div class="lbl"><span class="sq" style="background:${colorVar(c.color)}"></span> ${esc(c.name)}</div>
      <div class="mini">${esc(ROLE[c.role])}</div></div>`).join('')}</div>`;
}

function seriesRows(g) {
  const gmax = Math.max(1, ...g.companies.flatMap((c) => c.series));
  return g.companies.map((c) => `
    <div class="series" style="--cc:${colorVar(c.color)}"><div><b>${esc(c.name)}</b><div class="mini">${esc(ROLE[c.role])}</div></div>
      <div class="bars" role="img" aria-label="${esc(c.name)} 기간별 게시물">${c.series.map((n, i) =>
        `<i style="height:${n ? Math.max(8, (100 * n) / gmax) : 2}%;${n ? '' : 'opacity:.25'}" title="${esc(seriesLabel(g, i))}: ${n}건"></i>`).join('')}</div>
      <div class="num" style="text-align:right"><b>${c.total}</b>건</div></div>`).join('');
}

export async function renderStats(root, ctx) {
  const st = ctx.state.stats;
  root.innerHTML = '<div class="loading">불러오는 중…</div>';
  let d;
  try { d = await api('/stats', { params: { range: st.range, anchor: st.anchor, platform: st.platform } }); }
  catch (e) { root.innerHTML = `<div class="empty"><b>불러오지 못했습니다</b>${esc(e.message)}</div>`; return; }
  const g = d.graph;
  const diff = d.total - d.prevTotal;
  const tile = (label, v, note = '') => `<div class="tile"><div class="eyebrow">${label}</div><div class="v">${v}</div><div class="sub">${note}</div></div>`;
  const bp = d.byPlatform;
  root.innerHTML = `
    <div class="section"><div class="row between"><div><div class="eyebrow">활동량 분석</div><h2>리서치 통계</h2></div>
      <div class="row"><button class="btn icon" data-act="prev" aria-label="이전">${ICON.left}</button>
        <b style="min-width:120px;text-align:center">${esc(rangeLabel(st.range, d.start, d.end, d.anchor))}</b>
        <button class="btn sm" data-act="today">오늘</button><button class="btn icon" data-act="next" aria-label="다음">${ICON.right}</button>
        <div class="seg">${[['week', '주간'], ['month', '월간'], ['year', '연간']].map(([k, n]) => `<button data-act="range" data-v="${k}" aria-pressed="${st.range === k}">${n}</button>`).join('')}</div></div></div></div>
    <div class="tiles" style="border-top:1px solid var(--border)">
      ${tile('전체 게시물', d.total, `직전 기간 ${d.prevTotal}건 (<span class="${diff >= 0 ? 'up' : 'down'}">${diff >= 0 ? '+' : ''}${diff}</span>)`)}
      ${tile('블로그 게시물', bp.blog || 0)}${tile('유튜브 게시물', bp.youtube || 0)}${tile('홈페이지·RSS', (bp.homepage || 0) + (bp.rss || 0))}</div>
    <div class="section"><div class="row between"><div><div class="eyebrow">회사별 게시 활동</div><h2>회사별 활동 그래프</h2></div>
      <div class="row"><div class="seg">${[['total', '통합'], ['series', '회사별']].map(([k, n]) => `<button data-act="mode" data-v="${k}" aria-pressed="${st.mode === k}">${n}</button>`).join('')}</div>
      <div class="seg">${[['all', '전체'], ['blog', '블로그'], ['youtube', '유튜브'], ['homepage', '홈페이지']].map(([k, n]) => `<button data-act="platform" data-v="${k}" aria-pressed="${st.platform === k}">${n}</button>`).join('')}</div></div></div>
      ${g.companies.length ? `<div class="card" style="margin-top:12px;padding:8px 16px">${st.mode === 'total' ? pills(g) : seriesRows(g)}</div>`
        : '<p class="sub" style="margin-top:12px">채널이 등록된 회사가 없습니다. 수집 관리에서 추가하세요.</p>'}</div>
    <div class="section"><div class="eyebrow">게시물 주제</div><h2>주제별 분포</h2>
      <div style="margin-top:10px">${d.topics.length ? hbars(d.topics.map((t) => ({ name: t.topic, value: t.n, text: `${t.n}건`, target: true })), { max: Math.max(...d.topics.map((t) => t.n)) })
        : '<p class="sub">이 기간의 게시물이 없습니다.</p>'}</div></div>`;
  root.onclick = (e) => {
    const b = e.target.closest('[data-act]');
    if (!b) return;
    if (b.dataset.act === 'prev') st.anchor = shift(st.range, st.anchor, -1);
    else if (b.dataset.act === 'next') st.anchor = shift(st.range, st.anchor, 1);
    else if (b.dataset.act === 'today') st.anchor = ctx.boot.today;
    else if (b.dataset.act === 'range') st.range = b.dataset.v;
    else if (b.dataset.act === 'mode') st.mode = b.dataset.v;
    else if (b.dataset.act === 'platform') st.platform = b.dataset.v;
    renderStats(root, ctx);
  };
}
