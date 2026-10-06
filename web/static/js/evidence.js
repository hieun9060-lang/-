import { api } from './api.js';
import { esc, link, PLATFORM, colorVar, ICON, shortDate } from './util.js';

const PAGE = 50;

export async function renderEvidence(root, ctx) {
  const st = ctx.state.evidence;
  const companies = ctx.boot.companies;
  const cmap = Object.fromEntries(companies.map((c) => [c.id, c]));
  root.innerHTML = '<div class="loading">불러오는 중…</div>';
  let d;
  try { d = await api('/evidence', { params: { company: st.company, topic: st.topic, days: st.days, q: st.q, limit: PAGE, offset: 0 } }); }
  catch (e) { root.innerHTML = `<div class="empty"><b>불러오지 못했습니다</b>${esc(e.message)}</div>`; return; }
  const withCh = companies.filter((c) => c.channels.length);
  const qs = new URLSearchParams({ company: st.company || '', topic: st.topic || '', days: st.days, q: st.q || '' });
  const row = (p) => {
    const c = cmap[p.company_id] || { color: 7 };
    const u = link(p.url);
    return `<div class="ev" style="--cc:${colorVar(c.color)}"><div style="min-width:0">
      <div class="row" style="gap:6px;font-size:12px"><span class="sq" style="background:${colorVar(c.color)}"></span><b>${esc(p.company)}</b>
        <span class="badge gray">${esc(p.topic)}</span><span class="muted">${esc(PLATFORM[p.platform] || p.platform)} · ${esc(p.date)}</span></div>
      <div class="tt">${esc(p.title)}</div>${p.snippet ? `<div class="sn">${esc(p.snippet.slice(0, 200))}</div>` : ''}</div>
      ${u ? `<a class="plink" href="${esc(u)}" target="_blank" rel="noopener noreferrer">${ICON.out} 원문 열기</a>` : ''}</div>`;
  };
  root.innerHTML = `
    <div class="section"><div class="row between"><div><div class="eyebrow">판단의 출처</div><h2>근거 자료</h2><div class="sub">수집한 원문을 회사와 주제별로 묶어 정리했습니다.</div></div>
      <div class="row"><b id="evtotal">${d.total}건</b><a class="btn sm" href="/api/evidence.csv?${esc(qs.toString())}" download>CSV 내려받기</a></div></div></div>
    <div class="filters">
      <label class="field">회사<select data-f="company"><option value="">전체 회사</option>${withCh.map((c) => `<option value="${esc(c.id)}" ${st.company === c.id ? 'selected' : ''}>${esc(c.name)}</option>`).join('')}</select></label>
      <label class="field">주제<select data-f="topic"><option value="">전체 주제</option>${d.topics.map((t) => `<option ${st.topic === t ? 'selected' : ''}>${esc(t)}</option>`).join('')}</select></label>
      <label class="field">기간<select data-f="days">${[['all', '전체 기간'], ['7', '최근 7일'], ['30', '최근 30일'], ['90', '최근 90일']].map(([v, n]) => `<option value="${v}" ${st.days === v ? 'selected' : ''}>${n}</option>`).join('')}</select></label>
      <label class="field" style="flex:1;min-width:180px">검색<input type="search" data-f="q" value="${esc(st.q || '')}" placeholder="제목·내용 검색"></label></div>
    <div id="evlist">${d.items.map(row).join('') || '<div class="empty">조건에 맞는 게시물이 없습니다.</div>'}</div>
    ${d.total > d.items.length ? `<div class="section" style="text-align:center"><button class="btn" id="more">더 보기 (${d.items.length}/${d.total})</button></div>` : ''}`;
  root.querySelectorAll('select[data-f]').forEach((s) => s.addEventListener('change', () => { st[s.dataset.f] = s.value; renderEvidence(root, ctx); }));
  const q = root.querySelector('input[data-f="q"]');
  let timer;
  q.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(() => { st.q = q.value; renderEvidence(root, ctx).then(() => { const n = root.querySelector('input[data-f="q"]'); n.focus(); n.setSelectionRange(n.value.length, n.value.length); }); }, 350); });
  const more = root.querySelector('#more');
  if (more) {
    let loaded = d.items.length;
    more.addEventListener('click', async () => {
      more.disabled = true;
      const r = await api('/evidence', { params: { company: st.company, topic: st.topic, days: st.days, q: st.q, limit: PAGE, offset: loaded } });
      loaded += r.items.length;
      root.querySelector('#evlist').insertAdjacentHTML('beforeend', r.items.map(row).join(''));
      more.textContent = `더 보기 (${loaded}/${r.total})`;
      more.disabled = false;
      if (loaded >= r.total) more.remove();
    });
  }
}
