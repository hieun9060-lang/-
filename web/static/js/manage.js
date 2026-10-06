import { api } from './api.js';
import { STATIC, META } from './mode.js';
import { $, $$, esc, link, ROLE, PLATFORM, colorVar, dialog, toast, spinner, ICON } from './util.js';

const STATUS = {
  ok: ['정상', 'ok', '✓'], warn: ['확인 필요', 'warn', '!'], login: ['로그인 필요', 'warn', '!'],
  error: ['오류', 'bad', '!'], pending: ['대기', 'gray', '…'],
};
const lines = (s) => s.split('\n').map((x) => x.trim()).filter(Boolean);

function swatches(sel) {
  return `<div class="swatches" role="group" aria-label="색상">${[0, 1, 2, 3, 4, 5, 6, 7].map((i) =>
    `<button type="button" data-color="${i}" style="--cc:${colorVar(i)}" aria-pressed="${i === sel}" aria-label="색상 ${i + 1}"></button>`).join('')}</div>`;
}

function companyDialog(ctx, c, done) {
  const isNew = !c;
  const cur = c || { name: '', role: 'competitor', color: [0, 1, 2, 3, 4, 5, 6, 7].find((i) => !ctx.boot.companies.some((x) => x.color === i && x.channels.length)) ?? 0, aliases: [], domains: [], trackAi: true, channels: [] };
  let color = cur.color;
  const html = `
    <div class="dlg-h"><h3>${isNew ? '회사 추가' : '회사 수정'}</h3><button class="btn sm" data-close type="button">닫기</button></div>
    <form class="dlg-b" id="cf" autocomplete="off">
      <label class="field">회사(학원) 이름<input type="text" name="name" required maxlength="60" value="${esc(cur.name)}" placeholder="예: 강남대성 기숙학원"></label>
      <div class="field">구분<div class="row"><label><input type="radio" name="role" value="competitor" ${cur.role !== 'ours' ? 'checked' : ''}> 직접 경쟁사</label>
        <label><input type="radio" name="role" value="ours" ${cur.role === 'ours' ? 'checked' : ''}> 우리 학원 (하나만 지정됩니다)</label></div></div>
      <div class="field">화면 색상<div id="sw">${swatches(color)}</div></div>
      ${cur.channels.length ? `<div class="field">등록된 채널<div id="chs">${cur.channels.map((ch) => `
        <div class="row between" style="padding:4px 0;font-weight:500"><span style="min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap"><span class="badge gray">${esc(PLATFORM[ch.type] || ch.type)}</span> ${esc(ch.url)}</span>
        <button class="btn sm danger" type="button" data-delch="${ch.id}">삭제</button></div>`).join('')}</div></div>` : ''}
      <label class="field">채널 주소 추가 (한 줄에 하나)<textarea name="urls" placeholder="https://blog.naver.com/아이디&#10;https://www.youtube.com/@채널&#10;https://학원홈페이지.co.kr"></textarea>
        <span class="sub" style="font-weight:400">블로그·유튜브·RSS는 새 글을 자동으로 읽고, 그 밖의 홈페이지는 페이지 링크의 변화를 추적합니다.</span></label>
      <label class="field">AI 답변에서 이 학원으로 인정할 표기 (한 줄에 하나)<textarea name="aliases" placeholder="이투스247이천&#10;이천이투스">${esc(cur.aliases.join('\n'))}</textarea></label>
      <label class="field">공식 사이트 도메인 조각 (한 줄에 하나, AI 답변의 출처 분류용)<textarea name="domains" placeholder="etoos247icheon">${esc(cur.domains.join('\n'))}</textarea></label>
      <label class="row"><input type="checkbox" name="trackAi" ${cur.trackAi ? 'checked' : ''}> AI 챗봇 언급 측정에 포함</label>
      <div class="err-msg" id="cferr" role="alert"></div>
    </form>
    <div class="dlg-f"><div>${!isNew && cur.role !== 'ours' ? '<button class="btn danger" type="button" id="delco">회사 삭제</button>' : ''}</div>
      <div class="row"><button class="btn" data-close type="button">취소</button><button class="btn primary" type="button" id="save">저장</button></div></div>`;
  dialog(html, {
    onBind(dlg) {
      $('#sw', dlg).onclick = (e) => {
        const b = e.target.closest('[data-color]');
        if (!b) return;
        color = Number(b.dataset.color);
        $$('#sw button', dlg).forEach((x) => x.setAttribute('aria-pressed', x === b));
      };
      $$('[data-delch]', dlg).forEach((b) => b.onclick = async () => {
        if (!confirm('이 채널과 채널에서 수집한 게시물 연결을 삭제할까요?')) return;
        try { await api(`/channels/${b.dataset.delch}`, { method: 'DELETE' }); b.closest('.row').remove(); done(); } catch (e) { toast(e.message, 'err'); }
      });
      const del = $('#delco', dlg);
      if (del) del.onclick = async () => {
        if (!confirm(`'${cur.name}'과 수집된 게시물을 모두 삭제합니다. 계속할까요?`)) return;
        try { await api(`/companies/${cur.id}`, { method: 'DELETE' }); dlg.close(); toast('삭제했습니다.'); done(); } catch (e) { $('#cferr', dlg).textContent = e.message; }
      };
      $('#save', dlg).onclick = async (ev) => {
        const f = $('#cf', dlg), btn = ev.currentTarget, err = $('#cferr', dlg);
        err.textContent = '';
        if (!f.name.value.trim()) { err.textContent = '회사 이름을 입력하세요.'; return; }
        const body = { name: f.name.value.trim(), role: f.role.value, color, aliases: lines(f.aliases.value), domains: lines(f.domains.value), trackAi: f.trackAi.checked };
        btn.disabled = true; btn.innerHTML = `${spinner} 저장·수집 중…`;
        try {
          if (isNew) {
            const r = await api('/companies', { method: 'POST', body: { ...body, channels: lines(f.urls.value).map((url) => ({ url })) } });
            if (r.errors.length) toast('일부 채널을 추가하지 못했습니다: ' + r.errors.join(' / '), 'err');
          } else {
            await api(`/companies/${cur.id}`, { method: 'PATCH', body });
            for (const url of lines(f.urls.value)) {
              try { await api(`/companies/${cur.id}/channels`, { method: 'POST', body: { url } }); } catch (e) { toast(`${url}: ${e.message}`, 'err'); }
            }
          }
          dlg.close(); toast('저장했습니다.'); done();
        } catch (e) { err.textContent = e.message; btn.disabled = false; btn.textContent = '저장'; }
      };
    },
  });
}

function addUrlDialog(ctx, done) {
  const cs = ctx.boot.companies;
  dialog(`<div class="dlg-h"><h3>URL 추가</h3><button class="btn sm" data-close type="button">닫기</button></div>
    <form class="dlg-b" id="uf" autocomplete="off">
      <label class="field">회사<select name="company">${cs.map((c) => `<option value="${esc(c.id)}">${esc(c.name)}</option>`).join('')}</select></label>
      <label class="field">주소<input type="url" name="url" required placeholder="https://blog.naver.com/아이디" maxlength="500"></label>
      <label class="field">유형<select name="type"><option value="auto">자동 판별</option><option value="blog">블로그</option><option value="youtube">유튜브</option><option value="homepage">홈페이지</option><option value="rss">RSS</option></select></label>
      <div class="err-msg" id="uerr" role="alert"></div></form>
    <div class="dlg-f"><span></span><div class="row"><button class="btn" data-close type="button">취소</button><button class="btn primary" id="usave" type="button">추가하고 수집</button></div></div>`, {
    onBind(dlg) {
      $('#usave', dlg).onclick = async (ev) => {
        const f = $('#uf', dlg), btn = ev.currentTarget;
        if (!f.url.value.trim()) { $('#uerr', dlg).textContent = '주소를 입력하세요.'; return; }
        btn.disabled = true; btn.innerHTML = `${spinner} 수집 중…`;
        try {
          const ch = await api(`/companies/${f.company.value}/channels`, { method: 'POST', body: { url: f.url.value, type: f.type.value } });
          dlg.close(); toast(`${STATUS[ch.status]?.[0] || ''}: ${ch.status_msg}`, ch.status === 'ok' ? '' : 'err'); done();
        } catch (e) { $('#uerr', dlg).textContent = e.message; btn.disabled = false; btn.textContent = '추가하고 수집'; }
      };
    },
  });
}

function channelDialog(ch, done) {
  dialog(`<div class="dlg-h"><h3>채널 수정</h3><button class="btn sm" data-close type="button">닫기</button></div>
    <form class="dlg-b" id="chf" autocomplete="off">
      <label class="field">주소<input type="url" name="url" value="${esc(ch.url)}" maxlength="500"></label>
      <label class="field">유형<select name="type">${Object.entries(PLATFORM).map(([k, n]) => `<option value="${k}" ${ch.type === k ? 'selected' : ''}>${n}</option>`).join('')}</select></label>
      <label class="field">이름(선택)<input type="text" name="label" value="${esc(ch.label || '')}" maxlength="60"></label>
      <label class="row"><input type="checkbox" name="active" ${ch.active ? 'checked' : ''}> 수집 사용</label>
      <div class="err-msg" id="cherr" role="alert"></div></form>
    <div class="dlg-f"><button class="btn danger" id="chdel" type="button">채널 삭제</button><div class="row"><button class="btn" data-close type="button">취소</button><button class="btn primary" id="chsave" type="button">저장</button></div></div>`, {
    onBind(dlg) {
      $('#chdel', dlg).onclick = async () => {
        if (!confirm('이 채널을 삭제할까요? (이미 수집한 게시물은 남습니다)')) return;
        try { await api(`/channels/${ch.id}`, { method: 'DELETE' }); dlg.close(); done(); } catch (e) { $('#cherr', dlg).textContent = e.message; }
      };
      $('#chsave', dlg).onclick = async () => {
        const f = $('#chf', dlg);
        try {
          await api(`/channels/${ch.id}`, { method: 'PATCH', body: { url: f.url.value, type: f.type.value, label: f.label.value, active: f.active.checked } });
          dlg.close(); toast('저장했습니다. 주소를 바꿨다면 재시도로 확인하세요.'); done();
        } catch (e) { $('#cherr', dlg).textContent = e.message; }
      };
    },
  });
}

export async function renderManage(root, ctx) {
  if (STATIC) return renderManageStatic(root, ctx);
  root.innerHTML = '<div class="loading">불러오는 중…</div>';
  let qdata;
  try { await ctx.reloadBoot(); qdata = await api('/questions'); }
  catch (e) { root.innerHTML = `<div class="empty"><b>불러오지 못했습니다</b>${esc(e.message)}</div>`; return; }
  const cs = ctx.boot.companies;
  const cname = Object.fromEntries(cs.map((c) => [c.id, c.name]));
  const chans = cs.flatMap((c) => c.channels.map((ch) => ({ ...ch, company: c.name })));
  const refresh = () => renderManage(root, ctx);
  const active = cs.filter((c) => c.channels.length || c.role === 'ours');
  const others = cs.filter((c) => !active.includes(c));
  const coRow = (c) => `<div class="mgrow"><div><b>${esc(c.name)}</b> ${c.role === 'ours' ? '<span class="badge">우리 학원</span>' : ''}
        <div class="sub">${esc(ROLE[c.role])} · 수집된 게시물 ${c.posts}건${c.trackAi ? ' · AI 언급 측정' : ''}</div></div>
        <div class="row"><span class="sub">${c.channels.length}개 URL</span><button class="btn sm" data-act="edit-co" data-id="${esc(c.id)}">수정하기</button></div></div>`;
  const sortKey = (ch) => ({ login: 0, error: 0, warn: 1, pending: 2, ok: 3 }[ch.status] ?? 3);
  chans.sort((a, b) => sortKey(a) - sortKey(b) || a.company.localeCompare(b.company));
  const bad = chans.filter((c) => ['login', 'error', 'warn'].includes(c.status)).length;
  const daily = qdata.daily, panelN = qdata.questions.filter((q) => q.panel && q.enabled).length;
  const enabledN = qdata.questions.filter((q) => q.enabled).length;

  root.innerHTML = `
    <div class="section"><div class="row between"><div><div class="eyebrow">모니터링 범위</div><h2>회사와 URL</h2>
      <div class="sub">${active.length}개 회사의 ${chans.length}개 URL을 확인하고 있습니다.</div></div>
      <div class="row"><button class="btn" data-act="add-url">URL 추가</button><button class="btn primary" data-act="add-co">회사 추가</button></div></div>
      <div style="margin-top:10px">${active.map(coRow).join('') || '<div class="sub">채널이 등록된 회사가 없습니다. 회사 추가로 시작하세요.</div>'}</div>
      ${others.length ? `<details style="margin-top:10px"><summary>AI 언급 측정만 하는 학원 ${others.length}개 (채널 미등록)</summary>${others.map(coRow).join('')}</details>` : ''}</div>
    <div class="section"><div class="row between"><div><div class="eyebrow">수집 상태와 복구</div><h2>채널 관리</h2>
      <div class="sub">문제가 있는 채널을 먼저 보여드립니다. 주소를 고친 뒤 같은 자리에서 다시 시험할 수 있습니다.</div></div>
      <div class="row">${bad ? `<span class="badge warn">${bad}개 확인 필요</span>` : '<span class="badge ok">모두 정상</span>'}</div></div>
      <div style="margin-top:10px;border:1px solid var(--border);border-radius:10px;overflow:hidden">${chans.length ? chans.map((ch) => {
        const [lab, cls, ic] = STATUS[ch.status] || STATUS.pending;
        const u = link(ch.url);
        return `<div class="chrow ${['login', 'error', 'warn'].includes(ch.status) ? 'bad' : ''}"><div class="ic">${ic}</div>
          <div class="info"><div><b>${esc(PLATFORM[ch.type] || ch.type)}</b> <span class="badge ${cls}">${lab}</span> ${ch.active ? '' : '<span class="badge gray">사용 안 함</span>'}</div>
            <div class="sub">${esc(ch.company)} · ${esc(ch.status_msg || '아직 수집 전입니다.')}</div>
            <div class="u">${esc(ch.url)}</div>${ch.last_checked_at ? `<div class="sub">마지막 확인 ${esc(ch.last_checked_at.replace('T', ' ').slice(0, 16))} · 수집 ${ch.item_count || 0}건</div>` : ''}</div>
          <div class="row">${u ? `<a class="btn sm icon" href="${esc(u)}" target="_blank" rel="noopener noreferrer" aria-label="열기" title="열기">${ICON.out}</a>` : ''}
            <button class="btn sm" data-act="ch-edit" data-id="${ch.id}">수정</button><button class="btn sm" data-act="ch-retry" data-id="${ch.id}">재시도</button></div></div>`;
      }).join('') : '<div class="empty">등록된 채널이 없습니다. 위에서 회사를 수정하거나 URL을 추가하세요.</div>'}</div></div>
    <div class="section"><div class="row between"><div><div class="eyebrow">AI 챗봇 언급 측정</div><h2>AI 질문 관리</h2>
      <div class="sub">소비자가 AI 챗봇에 실제로 하는 질문입니다. 하루 ${daily}개(고정 ${panelN}개 + 나머지 순환)를 측정하고, 켜진 질문 ${enabledN}개가 순환합니다.</div></div></div>
      <form class="row" id="qf" style="margin:12px 0" autocomplete="off"><input type="text" id="qtext" maxlength="200" placeholder="새 질문 (예: 이천 기숙학원 어디가 좋아요?)" style="flex:1;min-width:220px">
        <label class="row"><input type="checkbox" id="qpanel"> 매일 고정</label><button class="btn primary" type="submit">질문 추가</button></form>
      <div style="border:1px solid var(--border);border-radius:10px;overflow:hidden;max-height:420px;overflow-y:auto">${qdata.questions.map((q) => `
        <div class="list-row" style="padding:8px 12px"><input type="checkbox" data-q="${esc(q.id)}" data-k="enabled" ${q.enabled ? 'checked' : ''} aria-label="측정 사용">
          <button class="btn sm" data-act="q-panel" data-id="${esc(q.id)}" data-on="${q.panel ? 1 : 0}" title="매일 고정 질문 여부" style="${q.panel ? 'color:var(--c3);border-color:var(--c3)' : ''}">${q.panel ? '★ 고정' : '☆'}</button>
          <div class="grow" style="min-width:0;${q.enabled ? '' : 'opacity:.5'}">${esc(q.text)}<div>${q.categories.map((c) => `<span class="tag">${esc(c)}</span>`).join('')}</div></div>
          <button class="btn sm danger" data-act="q-del" data-id="${esc(q.id)}" aria-label="삭제">삭제</button></div>`).join('')}</div></div>`;

  root.onclick = async (e) => {
    const b = e.target.closest('[data-act]');
    if (!b) return;
    const act = b.dataset.act;
    try {
      if (act === 'add-co') companyDialog(ctx, null, refresh);
      else if (act === 'edit-co') companyDialog(ctx, cs.find((c) => c.id === b.dataset.id), refresh);
      else if (act === 'add-url') { if (!cs.length) return toast('먼저 회사를 추가하세요.', 'err'); addUrlDialog(ctx, refresh); }
      else if (act === 'ch-edit') channelDialog(chans.find((c) => String(c.id) === b.dataset.id), refresh);
      else if (act === 'ch-retry') {
        b.disabled = true; b.innerHTML = spinner;
        const r = await api(`/channels/${b.dataset.id}/retry`, { method: 'POST' });
        toast(`${r.result.message}${r.result.new ? ` (새 게시물 ${r.result.new}건)` : ''}`, r.result.status === 'ok' ? '' : 'err');
        refresh();
      } else if (act === 'q-del') { await api(`/questions/${b.dataset.id}`, { method: 'DELETE' }); refresh(); }
      else if (act === 'q-panel') { await api(`/questions/${b.dataset.id}`, { method: 'PATCH', body: { panel: b.dataset.on !== '1' } }); refresh(); }
    } catch (err) { toast(err.message, 'err'); refresh(); }
  };
  root.onchange = async (e) => {
    const c = e.target.closest('[data-q]');
    if (!c) return;
    try { await api(`/questions/${c.dataset.q}`, { method: 'PATCH', body: { [c.dataset.k]: c.checked } }); refresh(); } catch (err) { toast(err.message, 'err'); }
  };
  $('#qf', root).onsubmit = async (e) => {
    e.preventDefault();
    const t = $('#qtext', root).value.trim();
    if (t.length < 2) return;
    try { await api('/questions', { method: 'POST', body: { text: t, panel: $('#qpanel', root).checked } }); toast('질문을 추가했습니다.'); refresh(); } catch (err) { toast(err.message, 'err'); }
  };
}

/* ---------- 정적 모드: 보기 전용 + GitHub 설정 파일 안내 ---------- */
async function renderManageStatic(root, ctx) {
  root.innerHTML = '<div class="loading">불러오는 중…</div>';
  const q = await api('/questions');
  const cs = ctx.boot.companies.filter((c) => c.channels.length || c.role === 'ours');
  const chans = cs.flatMap((c) => c.channels.map((ch) => ({ ...ch, company: c.name })));
  const sortKey = (ch) => ({ login: 0, error: 0, warn: 1, pending: 2, ok: 3 }[ch.status] ?? 3);
  chans.sort((a, b) => sortKey(a) - sortKey(b) || a.company.localeCompare(b.company));
  const edit = (f) => (META.repo ? `https://github.com/${META.repo}/edit/${META.branch}/config/${f}` : '');
  const bad = chans.filter((c) => ['login', 'error', 'warn'].includes(c.status)).length;
  const btn = (href, label, cls = '') => (href ? `<a class="btn ${cls}" href="${esc(href)}" target="_blank" rel="noopener noreferrer">${label}</a>` : '');
  root.innerHTML = `
    <div class="section"><div class="eyebrow">설정 방법</div><h2>수집 설정은 GitHub 파일로 관리합니다</h2>
      <p class="sub" style="font-size:13px;margin:6px 0 10px">이 화면은 보기 전용입니다. 아래 버튼으로 설정 파일을 열어 고친 뒤 <b>Commit changes</b>를 누르면, 몇 분 안에 자동으로 다시 수집해 이 화면에 반영됩니다.</p>
      <div class="row">${btn(edit('monitor.yaml'), '채널 주소·질문 추가 (monitor.yaml)', 'primary')}${btn(edit('brands.yaml'), '학원 목록·AI 표기 (brands.yaml)')}
        ${META.repo ? btn(`https://github.com/${META.repo}/actions`, '실행 상태 보기 (Actions)') : ''}</div></div>
    <div class="section"><div class="eyebrow">모니터링 범위</div><h2>회사와 URL</h2><div class="sub">${cs.length}개 회사의 ${chans.length}개 URL을 확인하고 있습니다.</div>
      <div style="margin-top:10px">${cs.map((c) => `<div class="mgrow"><div><b>${esc(c.name)}</b> ${c.role === 'ours' ? '<span class="badge">우리 학원</span>' : ''}
        <div class="sub">${esc(ROLE[c.role])} · 수집된 게시물 ${c.posts}건</div></div><span class="sub">${c.channels.length}개 URL</span></div>`).join('')}</div></div>
    <div class="section"><div class="row between"><div><div class="eyebrow">수집 상태</div><h2>채널 관리</h2>
      <div class="sub">문제가 있는 채널을 먼저 보여드립니다. 주소는 monitor.yaml 에서 고칩니다.</div></div>
      ${bad ? `<span class="badge warn">${bad}개 확인 필요</span>` : chans.length ? '<span class="badge ok">모두 정상</span>' : ''}</div>
      <div style="margin-top:10px;border:1px solid var(--border);border-radius:10px;overflow:hidden">${chans.length ? chans.map((ch) => {
        const [lab, cls, ic] = STATUS[ch.status] || STATUS.pending;
        const u = link(ch.url);
        return `<div class="chrow ${['login', 'error', 'warn'].includes(ch.status) ? 'bad' : ''}"><div class="ic">${ic}</div>
          <div class="info"><div><b>${esc(PLATFORM[ch.type] || ch.type)}</b> <span class="badge ${cls}">${lab}</span></div>
            <div class="sub">${esc(ch.company)} · ${esc(ch.status_msg || '아직 수집 전입니다.')}</div><div class="u">${esc(ch.url)}</div>
            ${ch.last_checked_at ? `<div class="sub">마지막 확인 ${esc(ch.last_checked_at.replace('T', ' ').slice(0, 16))} · 수집 ${ch.item_count || 0}건</div>` : ''}</div>
          ${u ? `<a class="btn sm icon" href="${esc(u)}" target="_blank" rel="noopener noreferrer" aria-label="열기">${ICON.out}</a>` : ''}</div>`;
      }).join('') : '<div class="empty"><b>등록된 채널이 없습니다</b>위의 <b>monitor.yaml</b> 버튼을 눌러 channels 항목에 우리 학원과 경쟁 학원의 블로그·유튜브·홈페이지 주소를 넣으세요.</div>'}</div></div>
    <div class="section"><div class="eyebrow">AI 챗봇 언급 측정</div><h2>AI 질문</h2>
      <div class="sub">하루 ${q.daily}개(고정 + 순환)를 측정합니다. 질문 추가·제외는 monitor.yaml 의 extra_questions / disable_questions 에서 합니다.</div>
      <div style="margin-top:10px;border:1px solid var(--border);border-radius:10px;overflow:hidden;max-height:420px;overflow-y:auto">${q.questions.map((x) => `
        <div class="list-row" style="padding:8px 12px"><span class="badge ${x.enabled ? 'ok' : 'gray'}">${x.enabled ? '사용' : '제외'}</span>${x.panel ? '<span class="badge warn">★ 고정</span>' : ''}
          <div class="grow" style="min-width:0;${x.enabled ? '' : 'opacity:.5'}">${esc(x.text)}<span class="sub"> ${esc(x.id)}</span></div></div>`).join('')}</div></div>`;
}
