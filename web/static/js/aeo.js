import { api } from './api.js';
import { esc, bold, hbars, link, ICON, toast } from './util.js';

const SENT = { positive: '긍정', negative: '부정', mixed: '혼재', neutral: '중립' };
const GROUPS = ['공식 홈페이지', '자사 앱·채널', '커뮤니티', '블로그', '언론/보도자료', '제3자 학원정보', '경쟁사 공식', '기타(영상·위키·무관)'];
const SUBS = [['insight', '인사이트'], ['compete', '경쟁 비교'], ['sources', '출처'], ['questions', '질문별 결과'], ['actions', '개선과제']];
const pct = (v) => (v == null ? '–' : v + '%');

function mdToHtml(md) {
  const out = []; let inList = false;
  md.split('\n').forEach((ln) => {
    const s = ln.trim();
    if (!s) return;
    const li = /^([-*•]|\d+\.)\s+/.test(s);
    const body = bold(s.replace(/^([-*•]|\d+\.)\s+/, '').replace(/^#+\s*/, ''));
    if (li) { if (!inList) { out.push('<ul>'); inList = true; } out.push(`<li>${body}</li>`); }
    else { if (inList) { out.push('</ul>'); inList = false; } out.push(`<p>${body}</p>`); }
  });
  if (inList) out.push('</ul>');
  return out.join('');
}
const rateBars = (list, nameFn) => hbars(list.map((r) => ({ name: nameFn ? nameFn(r.key) : r.key, value: r.rate, text: `${r.rate}% (${r.hit}/${r.n})`, target: true })));
const legend = (names, line) => `<div class="legend2">${names.map((n, i) => `<span><i style="background:var(--c${i})${line ? ';height:2px;width:14px;vertical-align:3px' : ''}"></i>${esc(n)}</span>`).join('')}</div>`;
const stack = (groups) => {
  const total = groups.reduce((a, g) => a + g[1], 0) || 1;
  return `<div class="stack">${groups.map((g, i) => (g[1] ? `<span style="width:${(100 * g[1] / total).toFixed(2)}%;background:var(--c${i})" title="${esc(g[0])}: ${g[1]}건 (${(100 * g[1] / total).toFixed(1)}%)"></span>` : '')).join('')}</div>`;
};

function trend(d) {
  const tr = d.trend;
  if (!tr || tr.length < 2) return '<p class="sub">추이는 2일 이상 측정이 쌓이면 표시됩니다.</p>';
  const engines = [...new Set(tr.flatMap((t) => Object.keys(t.engines || {})))].sort();
  const lab = (e) => d.engineLabels[e] || e;
  const series = [{ name: '전체', get: (t) => t.rate }, ...(engines.length > 1 ? engines.slice(0, 3).map((e) => ({ name: lab(e), get: (t) => t.engines[e] })) : [])];
  const W = Math.max(300, Math.min(640, (document.getElementById('view')?.clientWidth || 640) - 60)), H = 190, L = 34, R = 12, T = 12, B = 26;
  const x = (i) => L + (i * (W - L - R)) / (tr.length - 1), y = (v) => T + (1 - v / 100) * (H - T - B);
  let o = `<svg viewBox="0 0 ${W} ${H}" width="100%" style="max-width:820px" role="img" aria-label="언급률 추이">`;
  [0, 50, 100].forEach((g) => { o += `<line x1="${L}" x2="${W - R}" y1="${y(g)}" y2="${y(g)}" stroke="var(--border)"/><text x="${L - 6}" y="${y(g) + 4}" text-anchor="end">${g}%</text>`; });
  series.forEach((s, si) => {
    const pts = tr.map((t, i) => (s.get(t) == null ? null : `${x(i).toFixed(1)},${y(s.get(t)).toFixed(1)}`)).filter(Boolean);
    o += `<polyline points="${pts.join(' ')}" fill="none" stroke="var(--c${si})" stroke-width="2"/>`;
  });
  tr.forEach((t, i) => {
    const tip = `${t.date} — ${series.map((s) => `${s.name} ${s.get(t) == null ? '–' : s.get(t) + '%'}`).join(' · ')}`;
    o += `<circle cx="${x(i)}" cy="${y(t.rate)}" r="4" fill="var(--c0)" stroke="var(--surface)" stroke-width="2"/><rect x="${x(i) - 14}" y="${T}" width="28" height="${H - T - B}" fill="transparent"><title>${esc(tip)}</title></rect>`;
  });
  o += `<text x="${x(0)}" y="${H - 6}">${esc(tr[0].date.slice(5))}</text><text x="${x(tr.length - 1)}" y="${H - 6}" text-anchor="end">${esc(tr[tr.length - 1].date.slice(5))}</text></svg>`;
  return (series.length > 1 ? legend(series.map((s) => s.name), true) : '') + o;
}

const tile = (l, v, n) => `<div class="kpi"><div class="eyebrow" style="text-transform:none;letter-spacing:0;font-weight:600">${esc(l)}</div><div class="v">${esc(v)}</div>${n}</div>`;
function domTable(rows) {
  if (!rows || !rows.length) return '<p class="sub">해당 없음</p>';
  return `<div class="scroll"><table><thead><tr><th>도메인</th><th>유형</th><th class="r">건수</th></tr></thead><tbody>${rows.map((r) => `<tr><td>${esc(r[0])}</td><td>${esc(r[2])}</td><td class="r">${r[1]}</td></tr>`).join('')}</tbody></table></div>`;
}
function reasonBars(rows) {
  if (!rows.length) return '<p class="sub">–</p>';
  const max = Math.max(...rows.map((r) => r[1]));
  return hbars(rows.map((r) => ({ name: r[0], value: r[1], text: `${r[1]}건` })), { max, cls: 'long' });
}

function viewInsight(d) {
  const k = d.kpi; let o = '';
  Object.entries(k.engine_status || {}).forEach(([e, s]) => {
    if (s.errors && !s.answered) o += `<div class="jobbar err">${esc(d.engineLabels[e] || e)}: 오늘 응답 실패 ${s.errors}건 — ${esc(s.last_error)}</div>`;
  });
  o += `<div class="card pad brief" style="margin:12px 0"><h3>오늘의 핵심</h3><ul style="margin:8px 0 0">${d.briefing.map((b) => `<li>${bold(b)}</li>`).join('')}</ul>
    ${d.ai ? `<div class="aibox"><span class="badge">AI 해설 · ${esc(d.aiBy || 'AI')}</span>${mdToHtml(d.ai)}</div>` : ''}</div>`;
  let delta = '';
  if (d.delta) { const df = d.delta.diff; delta = `<div class="sub"><span class="${df > 0 ? 'up' : df < 0 ? 'down' : ''}">${df > 0 ? '▲' : df < 0 ? '▼' : '–'} ${Math.abs(df)}%p</span> 전일 대비</div>`; }
  o += `<div class="kpis">${tile(`오늘 언급률 (${k.today_basis || '오늘'})`, pct(k.today_rate), `${delta}<div class="sub">${k.today_hit}/${k.today_n} 답변</div>`)}
    ${tile(`누적 언급률 (최근 ${k.window_days}일)`, pct(k.target_rate), `<div class="sub">질문 ${k.questions_covered}개 · ${k.target_mentions}/${k.core_responses}</div>`)}
    ${tile("'이투스247'만 언급", pct(k.brand_only_rate), `<div class="sub">캠퍼스 혼동 신호 ${k.campus_confusion}건</div>`)}
    ${tile('공식 홈페이지 인용률', pct(k.official_cited_rate), '<div class="sub">기준선(9/29) 0%</div>')}</div>`;
  o += `<h3 style="margin-top:20px">언급률 추이 · 매일 같은 고정 질문</h3><div class="card pad" style="margin-top:8px">${trend(d)}</div>
    <h3 style="margin-top:20px">AI별 · 질문 유형별 (누적)</h3><div class="card pad" style="margin-top:8px">${rateBars(d.byEngine, (e) => d.engineLabels[e] || e)}<h3 style="margin-top:12px">질문 유형</h3>${rateBars(d.byBranded)}</div>
    <details class="card pad" style="margin-top:10px"><summary>엑셀 카테고리별 언급률</summary>${rateBars(d.byCategory)}</details>`;
  if (d.actions.length) {
    const a = d.actions[0];
    o += `<h3 style="margin-top:20px">오늘 먼저 할 일</h3><div class="act p0"><h3>${esc(a.title)}</h3><div class="sub">${esc(a.reason)} · ${a.count}건</div><ul>${a.detail.slice(0, 2).map((x) => `<li>${esc(x)}</li>`).join('')}</ul></div>`;
  }
  return o;
}
function viewCompete(d) {
  const max = Math.max(1, ...d.sov.map((s) => s.rate));
  let o = `<h3>같은 소비자 질문에서 학원별 언급률</h3><div class="card pad" style="margin:8px 0">${hbars(d.sov.filter((s) => s.mentions || s.is_target).map((s) => ({ name: s.name, value: s.rate, text: s.rate + '%', target: s.is_target })), { max })}
    <p class="sub">최근 ${d.kpi.window_days}일 동안 질문·AI별 최신 답변 기준</p></div>
    <div class="card pad scroll"><table><thead><tr><th>학원</th><th class="r">언급</th><th class="r">언급률</th><th class="r">점유율</th><th class="r">1순위</th><th class="r">평균순위</th></tr></thead><tbody>${d.sov.map((s) =>
    `<tr><td>${s.is_target ? `<b>${esc(s.name)}</b>` : esc(s.name)}</td><td class="r">${s.mentions}</td><td class="r">${s.rate}%</td><td class="r">${s.share}%</td><td class="r">${s.first}</td><td class="r">${s.avg_rank ?? '–'}</td></tr>`).join('')}</tbody></table></div>`;
  if (d.templateCompare.length) {
    o += `<h3 style="margin-top:20px">학원명만 바꾼 같은 질문</h3><div class="card pad scroll"><table><thead><tr><th>학원</th><th class="r">언급률</th><th class="r">자사 사이트 인용</th><th>함께 언급</th></tr></thead><tbody>${d.templateCompare.map((t) =>
      `<tr><td>${t.is_target ? `<b>${esc(t.name)}</b>` : esc(t.name)}</td><td class="r">${t.self_rate}%</td><td class="r">${t.official_rate}%</td><td>${t.cross_mentions.map((c) => `${esc(c[0])} ${c[1]}`).join(', ')}</td></tr>`).join('')}</tbody></table></div>`;
  }
  return o + `<h3 style="margin-top:20px">경쟁사만 언급될 때 AI가 본 출처</h3><div class="card pad">${domTable(d.competitorDomains)}</div>`;
}
function viewSources(d) {
  let o = `<h3>AI는 어디를 보고 답하나</h3><div class="card pad" style="margin:8px 0">${legend(GROUPS)}${d.sourceMix.map((m) => {
    const n = m.groups.reduce((a, g) => a + g[1], 0);
    return `<div class="hbar"><div class="nm">${esc(m.name)}</div>${stack(m.groups)}<div class="num">${n}건</div></div>`;
  }).join('')}<details><summary>표로 보기</summary><div class="scroll"><table><thead><tr><th>유형</th>${d.sourceMix.map((m) => `<th class="r">${esc(m.name)}</th>`).join('')}</tr></thead><tbody>${GROUPS.map((g, i) =>
    `<tr><td>${esc(g)}</td>${d.sourceMix.map((m) => `<td class="r">${m.groups[i][1]}</td>`).join('')}</tr>`).join('')}</tbody></table></div></details>
    <p class="sub">기준선은 엑셀(9/29) 웹검색 상위 노출 집계라 참고용입니다.</p></div>`;
  o += `<h3 style="margin-top:20px">이천캠퍼스를 다룬 출처 (언급의 근거)</h3><div class="card pad">${domTable(d.targetDomains)}</div>
    <h3 style="margin-top:20px">가장 많이 인용된 도메인</h3><div class="card pad">${domTable(d.topDomains)}</div>
    <h3 style="margin-top:20px">왜 언급됐고, 왜 안 됐나</h3><div class="card pad"><h3>언급된 답변</h3>${reasonBars(d.reasonsMentioned)}<h3 style="margin-top:12px">미언급 답변</h3>${reasonBars(d.reasonsNot)}</div>`;
  return o;
}
function engineCell(d, e, r) {
  const lab = d.engineLabels[e] || e;
  if (!r) return `<div class="e"><b>${esc(lab)}</b><div class="sub">이번 기간 미측정</div></div>`;
  const mark = r.err && !r.m && !r.src.length ? '<span class="sub">오류</span>'
    : r.m ? `<span class="ok">● ${r.rank}위</span>${r.sent ? ` <span class="sub">${esc(SENT[r.sent] || r.sent)}</span>` : ''}`
      : r.brandOnly ? '<span class="half">◐ 이투스247만</span>' : '<span class="no">○ 미언급</span>';
  return `<div class="e"><b>${esc(lab)}</b> ${mark}<div>${r.comp.slice(0, 3).map((c) => `<span class="tag">${esc(c)}</span>`).join('')}</div>
    <details><summary>왜? · 출처 ${r.src.length}</summary><ul>${r.reasons.map((c) => `<li>${esc(d.reasonLabels[c] || c)}</li>`).join('')}</ul>
    ${r.snippet ? `<div class="sub">“${esc(r.snippet)}”</div>` : ''}${r.err ? `<div class="sub">${esc(r.err)}</div>` : ''}
    ${r.src.map((s) => { const u = link(s.u); return `<div class="sub" style="word-break:break-all">${u ? `<a href="${esc(u)}" target="_blank" rel="noopener noreferrer">${esc(s.d)}</a>` : esc(s.d)} <span class="tag${s.target ? ' t' : ''}">${esc(s.t)}</span></div>`; }).join('')}</details></div>`;
}
function viewQuestions(d, st) {
  const engines = [...new Set(d.questions.flatMap((q) => Object.keys(q.engines)))].sort();
  const seg = (key, opts) => `<div class="seg" data-seg="${key}">${opts.map(([v, n]) => `<button aria-pressed="${st[key] === v}" data-v="${esc(v)}">${esc(n)}</button>`).join('')}</div>`;
  const list = d.questions.filter((q) => {
    if (st.qText && !q.q.includes(st.qText)) return false;
    const rs = (st.qEngine === 'all' ? Object.keys(q.engines) : [st.qEngine]).map((e) => q.engines[e]).filter(Boolean);
    if (!rs.length) return false;
    const any = rs.some((r) => r.m);
    return st.qFilter === 'all' || (st.qFilter === 'yes' ? any : !any);
  });
  return `<div class="row" style="margin-bottom:10px"><input type="search" id="aqs" placeholder="질문 검색" value="${esc(st.qText)}" style="flex:1;min-width:160px">
    ${seg('qFilter', [['all', '전체'], ['no', '미언급'], ['yes', '언급']])}${seg('qEngine', [['all', '모든 AI'], ...engines.map((e) => [e, d.engineLabels[e] || e])])}</div>
    <p class="sub">${list.length}개 질문 · ● 언급(순위) ◐ 이투스247만 ○ 미언급</p>
    ${list.map((q) => `<div class="q"><b>${esc(q.q)}</b><div>${q.cat.map((c) => `<span class="tag">${esc(c)}</span>`).join('')}${q.branded ? '<span class="tag t">브랜드 질문</span>' : ''}</div>
      <div class="eng">${(st.qEngine === 'all' ? engines : [st.qEngine]).map((e) => engineCell(d, e, q.engines[e])).join('')}</div></div>`).join('')}`;
}
function viewActions(d) {
  if (!d.actions.length) return '<div class="empty">개선과제가 없습니다.</div>';
  return `<h3>AEO/GEO 개선과제 (우선순위)</h3>${d.actions.map((a, i) => `<div class="act ${i < 2 ? 'p0' : i < 4 ? 'p1' : ''}">
    <h3>[${esc(a.priority)}] ${esc(a.title)} <span class="tag">${esc(a.area)}</span></h3><div class="sub">근거: ${esc(a.reason)} — ${a.count}건 (답변의 ${a.share}%)</div>
    <ul>${a.detail.map((x) => `<li>${esc(x)}</li>`).join('')}</ul><div class="sub">해당 질문 예: ${a.examples.map(esc).join(' / ')}</div></div>`).join('')}`;
}
const VIEWS = { insight: viewInsight, compete: viewCompete, sources: viewSources, questions: viewQuestions, actions: viewActions };

export async function renderAeo(root, ctx) {
  const st = ctx.state.aeo;
  root.innerHTML = '<div class="loading">불러오는 중…</div>';
  let idx;
  try { idx = await api('/aeo/index'); } catch (e) { root.innerHTML = `<div class="empty"><b>불러오지 못했습니다</b>${esc(e.message)}</div>`; return; }
  if (!idx.latest) {
    root.innerHTML = `<div class="empty"><b>아직 AI 챗봇 언급 측정 결과가 없습니다</b>Gemini · ChatGPT · Claude 답변에서 우리 학원이 얼마나, 왜 언급되는지 매일 측정합니다.<br>
      운영 설정에서 사용할 AI의 API 키가 등록되어 있는지 확인한 뒤 '지금 실행'을 눌러 첫 측정을 시작하세요.<br><br>
      <button class="btn primary" data-act="run-ai">AI 언급만 지금 측정</button></div>`;
    root.onclick = (e) => { if (e.target.closest('[data-act="run-ai"]')) ctx.runNow('ai'); };
    return;
  }
  if (!st.date || !idx.days.some((d) => d.date === st.date)) st.date = idx.latest;
  let d;
  try { d = await api(`/aeo/day/${st.date}`); } catch (e) { root.innerHTML = `<div class="empty"><b>불러오지 못했습니다</b>${esc(e.message)}</div>`; return; }
  root.innerHTML = `
    <div class="toolbar"><div><div class="eyebrow">AI 챗봇 답변 속 언급</div><h2>${esc(d.target)}</h2></div><div class="grow"></div>
      <select id="adate" aria-label="측정일">${[...idx.days].reverse().map((x) => `<option value="${esc(x.date)}" ${x.date === st.date ? 'selected' : ''}>${esc(x.date)}${x.todayRate != null ? ' · ' + x.todayRate + '%' : ''}</option>`).join('')}</select>
      <a class="btn sm" href="${esc(d.files.xlsx)}" download>엑셀</a></div>
    <div class="subtabs" role="tablist">${SUBS.map(([k, n]) => `<button role="tab" data-sub="${k}" aria-selected="${st.sub === k}">${n}</button>`).join('')}</div>
    <div class="section" style="border-top:0">${st.sub === 'questions' ? viewQuestions(d, st) : VIEWS[st.sub](d)}
      <p class="sub" style="margin-top:20px">측정 ${esc(d.generatedAt.replace('T', ' '))} · AI: ${esc(d.engines.join(', '))} · 언급 판정은 등록된 표기 기준 자동 판정이며 AI 답변은 실행마다 달라질 수 있습니다.</p></div>`;
  root.querySelector('#adate').onchange = (e) => { st.date = e.target.value; renderAeo(root, ctx); };
  root.onclick = (e) => {
    const s = e.target.closest('[data-sub]');
    if (s) { st.sub = s.dataset.sub; return renderAeo(root, ctx); }
    const g = e.target.closest('[data-seg] button');
    if (g) { st[g.parentNode.dataset.seg] = g.dataset.v; renderAeo(root, ctx); }
  };
  const q = root.querySelector('#aqs');
  if (q) q.oninput = () => { st.qText = q.value; const pos = q.selectionStart; renderAeo(root, ctx).then(() => { const n = root.querySelector('#aqs'); n?.focus(); n?.setSelectionRange(pos, pos); }); };
}
