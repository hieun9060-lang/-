import { api } from './api.js';
import { STATIC } from './mode.js';
import { $, $$, esc, link, ROLE, PLATFORM, colorVar, korDate, shortDate, korMonth, rangeLabel, shift, addDays, weekStart, parse, ymd, DOW, ICON, toast, spinner } from './util.js';

const sq = (c) => `<span class="sq" style="background:${colorVar(c.color)}"></span>`;

function prow(p) {
  const u = link(p.url);
  return `<div class="prow"><span class="mini">${esc(PLATFORM[p.platform] || p.platform)}</span><span class="t" title="${esc(p.title)}">${esc(p.title)}</span>
    ${u ? `<a href="${esc(u)}" target="_blank" rel="noopener noreferrer" title="원문 열기">${ICON.out} 원문</a>` : ''}</div>`;
}

function card(c) {
  const has = c.count > 0;
  const by = c.summaryBy ? `<span class="mini" title="요약 생성 방식">· ${esc(c.summaryBy)}</span>` : '';
  return `<article class="co ${c.role === 'ours' ? 'ours' : ''} ${has ? 'has' : ''}" style="--cc:${colorVar(c.color)}">
    <div class="head"><div><div class="name">${sq(c)}${esc(c.name)}</div><div class="mini">${esc(ROLE[c.role])}</div></div><span class="cnt">${c.count}건</span></div>
    ${has ? `<div class="issue">중심 이슈<b>${esc(c.issue)}</b> ${by}</div><p>${esc(c.summary)}</p>
        <div class="hl">핵심 요약: ${esc(c.highlight)}</div>${c.posts.slice(0, 3).map(prow).join('')}`
      : `<div class="statebox"><b>상태</b>&nbsp; 활동 없음</div><p>선택한 기간에 새로 확인된 게시물이 없습니다.</p>
        <div class="hl empty">핵심 요약: 선택 기간에 새로 확인된 게시물이 없습니다.</div>`}
  </article>`;
}

function postRow(p, c) {
  const u = link(p.url);
  return `<div class="post" style="--cc:${colorVar(c.color)}"><div style="min-width:0">
      <div class="meta"><b style="color:var(--text)">${esc(c.name)}</b><span class="badge gray">${esc(p.topic)}</span><span>${esc(PLATFORM[p.platform] || p.platform)}</span><span>${esc(p.date)}</span></div>
      <div class="tt">${esc(p.title)}</div>${p.snippet ? `<div class="sn">${esc(p.snippet)}</div>` : ''}</div>
      ${u ? `<a class="plink" href="${esc(u)}" target="_blank" rel="noopener noreferrer">${ICON.out} 원문 열기</a>` : ''}</div>`;
}

function compare(data, st) {
  const limit = st.view === 'day' ? 60 : 10;
  const blocks = data.companies.filter((c) => c.count).map((c) => `
    <div class="cmp" style="--cc:${colorVar(c.color)}"><div class="who"><b>${esc(c.name)}</b><div class="mini">${c.count}건 · ${esc(ROLE[c.role])}</div></div>
    <div>${c.posts.slice(0, limit).map((p) => postRow(p, c)).join('')}
      ${c.count > limit ? `<button class="btn sm" data-act="evidence" data-company="${esc(c.id)}">근거 자료에서 ${c.count}건 모두 보기</button>` : ''}</div></div>`);
  return blocks.join('') || '<p class="sub" style="margin-top:12px">이 기간에 새로 확인된 게시물이 없습니다.</p>';
}

function dayGrid(data, st) {
  const comp = Object.fromEntries(data.companies.map((c) => [c.id, c]));
  const first = weekStart(data.start), last = addDays(weekStart(data.end), 6);
  const days = [];
  for (let d = first; d <= last; d = addDays(d, 1)) days.push(d);
  const monthOf = parse(data.start).getMonth();
  const today = ymd(new Date());
  const cell = (d) => {
    const counts = data.daily[d] || {};
    const chips = Object.entries(counts).filter(([id]) => comp[id]).map(([id, n]) =>
      `<span class="chip" style="--cc:${colorVar(comp[id].color)}" title="${esc(comp[id].name)} ${n}건"><i class="sq" style="background:${colorVar(comp[id].color)};width:8px;height:8px"></i>${n}</span>`).join('');
    const out = st.view === 'month' && parse(d).getMonth() !== monthOf;
    return `<button class="cell ${out ? 'out' : ''} ${d === today ? 'today' : ''}" data-act="goday" data-date="${d}" aria-label="${korDate(d)}">
      <span class="dn">${st.view === 'week' ? `${DOW[(parse(d).getDay() + 6) % 7]} ${parse(d).getDate()}` : parse(d).getDate()}</span><div class="chips">${chips}</div></button>`;
  };
  return `<div class="calgrid ${st.view}">${DOW.map((x) => `<div class="dow">${x}</div>`).join('')}${days.map(cell).join('')}</div>`;
}

export async function renderCalendar(root, ctx) {
  const st = ctx.state.cal;
  root.innerHTML = '<div class="loading">불러오는 중…</div>';
  let data;
  try { data = await api('/calendar', { params: { view: st.view, anchor: st.anchor } }); }
  catch (e) { root.innerHTML = `<div class="empty"><b>불러오지 못했습니다</b>${esc(e.message)}</div>`; return; }
  if (!data.hasChannels) {
    root.innerHTML = `<div class="empty"><b>아직 수집할 채널이 없습니다</b>
      '수집 관리'에서 우리 학원과 경쟁 학원의 블로그·유튜브·홈페이지 주소를 등록하면, 매일 새 게시물을 모아 이 화면에 보여줍니다.<br><br>
      <button class="btn primary" data-act="manage">${STATIC ? '등록 방법 보기' : '수집 관리로 이동'}</button></div>`;
    bind(root, ctx, data);
    return;
  }
  const label = rangeLabel(st.view, data.start, data.end, data.anchor);
  const legend = data.companies.map((c) => `<span>${sq(c)}${esc(c.name)}${c.role === 'ours' ? ' <span class="badge">우리 학원</span>' : ''}</span>`).join('');
  const title = { day: `${korDate(data.anchor)} 업체별 동향`, week: `${label} 업체별 동향`, month: `${korMonth(data.anchor)} 업체별 동향` }[st.view];
  root.innerHTML = `
    <div class="toolbar">
      <button class="btn icon" data-act="prev" aria-label="이전">${ICON.left}</button>
      <div class="datebox"><div class="eyebrow">누적 리서치</div><div class="big">${esc(label)}</div><div class="sub">${data.total}건의 게시물</div></div>
      <button class="btn sm" data-act="today">오늘</button>
      <button class="btn icon" data-act="next" aria-label="다음">${ICON.right}</button>
      <div class="seg" role="group" aria-label="보기 단위">${[['day', '일간'], ['week', '주간'], ['month', '월간']].map(([k, n]) =>
        `<button data-act="view" data-view="${k}" aria-pressed="${st.view === k}">${n}</button>`).join('')}</div>
      <div class="legend">${legend}</div>
    </div>
    ${st.view !== 'day' ? `<div class="section">${dayGrid(data, st)}</div>` : ''}
    <div class="section"><div class="row between"><div><div class="eyebrow">${st.view === 'day' ? '일별' : st.view === 'week' ? '주간' : '월간'} 업체 동향</div><h2>${esc(title)}</h2></div>
      <div class="row">${st.view === 'day' && !STATIC ? `<button class="btn sm" data-act="digest">${ICON.spark} 업체 동향 AI 요약</button>` : ''}</div></div>
      <div class="cards">${data.companies.map(card).join('')}</div></div>
    <div class="section"><div class="eyebrow">회사별 ${st.view === 'day' ? '일간' : st.view === 'week' ? '주간' : '월간'} 비교</div>
      <h2>${st.view === 'day' ? shortDate(data.anchor) : esc(label)} 게시물</h2>${compare(data, st)}</div>`;
  bind(root, ctx, data);
}

function bind(root, ctx, data) {
  const st = ctx.state.cal;
  root.onclick = async (e) => {
    const b = e.target.closest('[data-act]');
    if (!b) return;
    const act = b.dataset.act;
    if (act === 'prev' || act === 'next') { st.anchor = shift(st.view, st.anchor, act === 'prev' ? -1 : 1); }
    else if (act === 'today') { st.anchor = ctx.boot.today; }
    else if (act === 'view') { st.view = b.dataset.view; }
    else if (act === 'goday') { st.view = 'day'; st.anchor = b.dataset.date; }
    else if (act === 'manage') { return ctx.goto('manage'); }
    else if (act === 'evidence') { ctx.state.evidence.company = b.dataset.company; ctx.state.evidence.days = 'all'; return ctx.goto('evidence'); }
    else if (act === 'digest') {
      b.disabled = true; b.innerHTML = `${spinner} 요약 중…`;
      try {
        const r = await api('/summaries', { method: 'POST', body: { date: data.anchor } });
        toast(r.companies ? `업체 동향을 요약했습니다 (${r.models.join(', ') || '규칙'})` : '이 날짜에 요약할 게시물이 없습니다.');
      } catch (err) { toast(err.message, 'err'); }
    }
    renderCalendar(root, ctx);
  };
}
