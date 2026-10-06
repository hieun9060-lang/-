import { api } from './api.js';
import { esc, link, ROLE, PLATFORM, colorVar, rangeLabel, shift, ICON, toast, spinner, bold } from './util.js';

export async function renderAnalysis(root, ctx) {
  const st = ctx.state.analysis;
  root.innerHTML = `<div class="section"><div class="row">${spinner}<div><b>AI 분석을 불러오고 있습니다.</b><div class="sub">선택한 기간의 저장된 보고서를 확인합니다.</div></div></div></div>`;
  let d;
  try { d = await api('/analysis', { params: { kind: st.kind, anchor: st.anchor } }); }
  catch (e) { root.innerHTML = `<div class="empty"><b>불러오지 못했습니다</b>${esc(e.message)}</div>`; return; }
  const r = d.report;
  const toolbar = `<div class="toolbar" style="border-bottom:1px solid var(--border)">
    <div class="seg">${[['week', '주간'], ['month', '월간']].map(([k, n]) => `<button data-act="kind" data-v="${k}" aria-pressed="${st.kind === k}">${n}</button>`).join('')}</div>
    <button class="btn icon" data-act="prev" aria-label="이전">${ICON.left}</button><b style="min-width:130px;text-align:center">${esc(rangeLabel(st.kind, d.start, d.end, d.anchor))}</b>
    <button class="btn icon" data-act="next" aria-label="다음">${ICON.right}</button><button class="btn sm" data-act="today">오늘</button><div class="grow"></div>
    <button class="btn primary" data-act="regen">${ICON.spark} ${r ? '다시 분석' : '분석 만들기'}</button></div>`;
  let body;
  if (!r) {
    body = `<div class="empty"><b>이 기간의 AI 분석이 아직 없습니다</b>'분석 만들기'를 누르면 수집된 게시물과 AI 언급 결과로 보고서를 만듭니다.
      ${d.ai ? '' : '<br><span class="sub">AI 모델 키가 없어 규칙 기반으로 작성됩니다.</span>'}</div>`;
  } else {
    const stats = r.stats;
    body = `<div class="section report"><div class="eyebrow">${st.kind === 'week' ? '주간' : '월간'} 분석</div><div class="headline">${esc(r.headline)}</div>
      ${r.sections.map((s) => `<h3>${esc(s.title)}</h3><ul>${s.bullets.map((b) => `<li>${bold(b)}</li>`).join('')}</ul>`).join('')}
      <p class="sub" style="margin-top:14px">생성: ${esc(r.model)} · ${esc((r.generatedAt || '').replace('T', ' ').slice(0, 16))} — 아래 숫자는 수집 데이터에서 직접 계산한 값입니다.</p></div>
      <div class="section"><h3>회사별 게시물</h3><div class="scroll"><table><thead><tr><th>회사</th><th class="r">건수</th><th class="r">직전 기간</th><th class="r">증감</th><th>주제</th><th>대표 게시물</th></tr></thead><tbody>
      ${stats.companies.map((c) => {
        const df = c.total - c.prev;
        const tops = c.top.slice(0, 2).map((t) => { const u = link(t.url); return u ? `<a href="${esc(u)}" target="_blank" rel="noopener noreferrer">${esc(t.title.slice(0, 36))}</a>` : esc(t.title.slice(0, 36)); }).join('<br>');
        return `<tr><td><span class="sq" style="background:${colorVar(c.color)}"></span> <b>${esc(c.name)}</b><div class="mini">${esc(ROLE[c.role])}</div></td><td class="r">${c.total}</td><td class="r">${c.prev}</td>
          <td class="r ${df > 0 ? 'up' : df < 0 ? 'down' : ''}">${df > 0 ? '+' : ''}${df}</td><td>${Object.entries(c.byTopic).sort((a, b) => b[1] - a[1]).slice(0, 3).map(([t, n]) => `<span class="tag">${esc(t)} ${n}</span>`).join('')}</td><td>${tops || '–'}</td></tr>`;
      }).join('')}</tbody></table></div></div>`;
  }
  root.innerHTML = toolbar + body;
  root.onclick = async (e) => {
    const b = e.target.closest('[data-act]');
    if (!b) return;
    const a = b.dataset.act;
    if (a === 'kind') st.kind = b.dataset.v;
    else if (a === 'prev') st.anchor = shift(st.kind, st.anchor, -1);
    else if (a === 'next') st.anchor = shift(st.kind, st.anchor, 1);
    else if (a === 'today') st.anchor = ctx.boot.today;
    else if (a === 'regen') {
      b.disabled = true; b.innerHTML = `${spinner} 분석 중…`;
      try { await api('/analysis', { method: 'POST', body: { kind: st.kind, anchor: st.anchor } }); toast('분석을 만들었습니다.'); } catch (err) { toast(err.message, 'err'); }
    }
    renderAnalysis(root, ctx);
  };
}
