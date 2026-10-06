import { api } from './api.js';
import { $, $$, esc, toast, spinner, ICON } from './util.js';

const ENG = { gemini: 'Gemini', chatgpt: 'ChatGPT', claude: 'Claude', perplexity: 'Perplexity' };

export async function renderSettings(root, ctx) {
  root.innerHTML = '<div class="loading">불러오는 중…</div>';
  let s;
  try { s = await api('/settings'); } catch (e) { root.innerHTML = `<div class="empty">${esc(e.message)}</div>`; return; }
  const k = s.keys, a = s.aeo, sc = s.schedule;
  const key = (n, ok) => `<span>${ok ? '<span class="badge ok">연결됨</span>' : '<span class="badge gray">키 없음</span>'} ${esc(n)}</span>`;
  root.innerHTML = `
    <div class="section"><div class="eyebrow">리서치 기준</div><h2>확정 리서치</h2><div class="sub">원장이 실제로 판단에 사용할 한 문장을 확정합니다. AI 요약·분석의 기준이 됩니다.</div>
      <div class="field" style="margin-top:12px">확정 리서치<input type="text" id="gt" maxlength="60" value="${esc(s.goal.title || '')}"></div>
      <div class="field" style="margin-top:8px">설명<textarea id="gd" maxlength="200" style="min-height:56px">${esc(s.goal.desc || '')}</textarea></div>
      <div class="row" style="margin-top:10px"><button class="btn primary" id="gsave">✓ 확정 저장</button><button class="btn" id="gsug">${ICON.spark} 리서치 추천 받기</button></div>
      <div id="sugs" class="row" style="margin-top:10px;align-items:stretch"></div></div>
    <div class="section"><div class="setgrid">
      <div><h3>자동 실행 시각 (한국 시간)</h3><div class="sub">서버가 켜져 있으면 매일 이 시각에 채널 수집 → 업체 동향 요약 → AI 언급 측정을 실행합니다.</div>
        <div class="row" style="margin-top:10px"><label class="field">수집·측정 시작<input type="time" id="rt" value="${esc(sc.run_time || '07:00')}"></label>
        <label class="field">요약 알림 발송<input type="time" id="nt" value="${esc(sc.notify_time || '09:00')}"></label></div>
        <label class="row" style="margin-top:10px"><input type="checkbox" id="aa" ${sc.auto_analysis !== false ? 'checked' : ''}> 월요일·1일에 주간·월간 분석 자동 생성</label>
        <div class="sub" style="margin-top:8px">알림 채널: ${key('Slack', k.slack)} ${key('이메일', k.email)}</div></div>
      <div><h3>AI 챗봇 언급 측정</h3><div class="sub">무료/체험 한도에 맞춰 하루 질문 수를 정합니다 (고정 질문 + 순환).</div>
        <div class="row" style="margin-top:10px">${s.allEngines.map((e) => `<label class="row"><input type="checkbox" data-eng="${e}" ${(a.engines || []).includes(e) ? 'checked' : ''} ${k[e] ? '' : 'disabled'}> ${ENG[e] || e} ${k[e] ? '' : '<span class="sub">(키 없음)</span>'}</label>`).join('')}</div>
        <div class="row" style="margin-top:10px"><label class="field">하루 질문 수<input type="number" id="dq" min="1" max="150" value="${esc(a.daily_questions || 10)}" style="width:90px"></label>
        <label class="field">요약·해설 작성 AI<select id="ie">${['gemini', 'claude', 'chatgpt'].map((e) => `<option value="${e}" ${a.insight_engine === e ? 'selected' : ''}>${ENG[e]}</option>`).join('')}</select></label></div>
        <label class="row" style="margin-top:10px"><input type="checkbox" id="it" ${a.include_templates ? 'checked' : ''}> 학원명만 바꾼 같은 질문도 측정 (호출 수 크게 증가)</label></div></div>
      <div class="row" style="margin-top:14px"><button class="btn primary" id="ssave">설정 저장</button></div>
      <p class="sub" style="margin-top:10px">API 키·비밀번호는 서버 환경변수로만 관리하며 화면에 표시하지 않습니다.</p></div>`;
  $('#gsave', root).onclick = async () => {
    try {
      const r = await api('/settings', { method: 'PUT', body: { goalTitle: $('#gt', root).value, goalDesc: $('#gd', root).value } });
      ctx.boot.goal = r.goal;
      $('.goal h2').textContent = r.goal.title; $('.goal p').textContent = r.goal.desc;
      toast('확정 리서치를 저장했습니다.');
    } catch (e) { toast(e.message, 'err'); }
  };
  $('#gsug', root).onclick = async (ev) => {
    const b = ev.currentTarget; b.disabled = true; b.innerHTML = `${spinner} 추천 중…`;
    try {
      const r = await api('/goal/suggest', { method: 'POST' });
      $('#sugs', root).innerHTML = r.suggestions.map((g, i) => `<button class="card pad" data-sug="${i}" style="text-align:left;cursor:pointer;flex:1;min-width:200px"><b>${esc(g.title)}</b><div class="sub">${esc(g.desc)}</div></button>`).join('');
      $$('[data-sug]', root).forEach((x) => x.onclick = () => { const g = r.suggestions[x.dataset.sug]; $('#gt', root).value = g.title; $('#gd', root).value = g.desc; });
    } catch (e) { toast(e.message, 'err'); }
    b.disabled = false; b.innerHTML = `${ICON.spark} 리서치 추천 받기`;
  };
  $('#ssave', root).onclick = async () => {
    try {
      await api('/settings', { method: 'PUT', body: {
        runTime: $('#rt', root).value, notifyTime: $('#nt', root).value, autoAnalysis: $('#aa', root).checked,
        engines: $$('[data-eng]', root).filter((c) => c.checked).map((c) => c.dataset.eng), dailyQuestions: Number($('#dq', root).value),
        includeTemplates: $('#it', root).checked, insightEngine: $('#ie', root).value } });
      toast('설정을 저장했습니다. 다음 실행부터 적용됩니다.');
    } catch (e) { toast(e.message, 'err'); }
  };
}
