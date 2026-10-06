import { api } from './api.js';
import { $, esc, ICON } from './util.js';

let panel = null;
const history = [];
const SUGGEST = ['이번 주 경쟁사 동향을 요약해줘', '우리 학원이 AI 답변에서 언급되려면 뭐부터 해야 해?', '경쟁사가 가장 많이 올리는 주제는?'];

export function openChat() {
  if (panel) { panel.remove(); panel = null; return; }
  panel = document.createElement('aside');
  panel.className = 'chat';
  panel.setAttribute('aria-label', 'AI 챗봇');
  panel.innerHTML = `<div class="dlg-h"><h3>AI 챗봇</h3><button class="btn sm" id="cx">닫기</button></div>
    <div class="msgs" id="msgs" aria-live="polite"><div class="msg ai">수집된 게시물과 AI 언급 결과를 바탕으로 답합니다. 무엇이 궁금하세요?</div>
      <div class="row">${SUGGEST.map((s) => `<button class="btn sm" data-s="${esc(s)}">${esc(s)}</button>`).join('')}</div></div>
    <form id="cf"><input type="text" id="ci" maxlength="1000" placeholder="질문을 입력하세요" autocomplete="off" aria-label="질문"><button class="btn primary" type="submit">보내기</button></form>`;
  document.body.appendChild(panel);
  const msgs = $('#msgs', panel);
  const add = (cls, text) => { const m = document.createElement('div'); m.className = 'msg ' + cls; m.textContent = text; msgs.appendChild(m); msgs.scrollTop = msgs.scrollHeight; return m; };
  history.forEach((m) => add(m.role === 'user' ? 'user' : 'ai', m.content));
  const send = async (text) => {
    if (!text.trim()) return;
    add('user', text);
    history.push({ role: 'user', content: text });
    const wait = add('ai', '생각하는 중…');
    try {
      const r = await api('/chat', { method: 'POST', body: { messages: history.slice(-10) } });
      wait.textContent = r.answer + (r.by ? `\n\n— ${r.by}` : '');
      history.push({ role: 'assistant', content: r.answer });
    } catch (e) { wait.textContent = '답변을 가져오지 못했습니다: ' + e.message; history.pop(); }
    msgs.scrollTop = msgs.scrollHeight;
  };
  $('#cf', panel).onsubmit = (e) => { e.preventDefault(); const i = $('#ci', panel); const t = i.value; i.value = ''; send(t); };
  msgs.onclick = (e) => { const b = e.target.closest('[data-s]'); if (b) send(b.dataset.s); };
  $('#cx', panel).onclick = () => { panel.remove(); panel = null; };
  $('#ci', panel).focus();
}
