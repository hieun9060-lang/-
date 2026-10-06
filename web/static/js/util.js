export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

const ESC = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
export const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ESC[c]);
export const link = (u) => (/^https?:\/\//i.test(u || '') ? u : '');
export const bold = (s) => esc(s).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>');

export const PLATFORM = { blog: '블로그', youtube: '유튜브', homepage: '홈페이지', rss: 'RSS' };
export const ROLE = { ours: '우리 학원', competitor: '직접 경쟁사' };
export const colorVar = (i) => `var(--c${(i ?? 0) % 8})`;
export const DOW = ['월', '화', '수', '목', '금', '토', '일'];

export function ymd(d) {
  const p = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}
export const parse = (s) => { const [y, m, d] = s.split('-').map(Number); return new Date(y, m - 1, d); };
export const addDays = (s, n) => { const d = parse(s); d.setDate(d.getDate() + n); return ymd(d); };
export const korDate = (s) => { const d = parse(s); return `${d.getFullYear()}년 ${d.getMonth() + 1}월 ${d.getDate()}일`; };
export const shortDate = (s) => { const d = parse(s); return `${d.getMonth() + 1}월 ${d.getDate()}일`; };
export const korMonth = (s) => { const d = parse(s); return `${d.getFullYear()}년 ${d.getMonth() + 1}월`; };
export function weekStart(s) { const d = parse(s); const k = (d.getDay() + 6) % 7; d.setDate(d.getDate() - k); return ymd(d); }

export function shift(kind, anchor, step) {
  const d = parse(anchor);
  if (kind === 'day') d.setDate(d.getDate() + step);
  else if (kind === 'week') d.setDate(d.getDate() + 7 * step);
  else if (kind === 'month') { d.setDate(1); d.setMonth(d.getMonth() + step); }
  else if (kind === 'year') { d.setMonth(0, 1); d.setFullYear(d.getFullYear() + step); }
  return ymd(d);
}
export function rangeLabel(kind, start, end, anchor) {
  if (kind === 'day') return korDate(anchor);
  if (kind === 'week') return `${shortDate(start)} - ${shortDate(end)}`;
  if (kind === 'month') return korMonth(anchor);
  return `${parse(anchor).getFullYear()}년`;
}

export function toast(msg, kind = '') {
  let box = $('.toasts');
  if (!box) { box = document.createElement('div'); box.className = 'toasts'; document.body.appendChild(box); }
  const t = document.createElement('div');
  t.className = 'toast ' + kind;
  t.textContent = msg;
  t.setAttribute('role', 'status');
  box.appendChild(t);
  setTimeout(() => t.remove(), kind === 'err' ? 6000 : 3200);
}

export function dialog(html, { onBind, onClose } = {}) {
  const dlg = document.createElement('dialog');
  dlg.innerHTML = html;
  document.body.appendChild(dlg);
  dlg.addEventListener('close', () => { onClose?.(); dlg.remove(); });
  dlg.addEventListener('click', (e) => { if (e.target === dlg) dlg.close(); });
  $$('[data-close]', dlg).forEach((b) => b.addEventListener('click', () => dlg.close()));
  onBind?.(dlg);
  dlg.showModal();
  return dlg;
}

export function hbars(rows, { max = 100, cls = '' } = {}) {
  return rows.map((r) => {
    const w = Math.max(0, Math.min(100, max ? (100 * r.value) / max : 0));
    return `<div class="hbar ${cls}" title="${esc(r.name)}: ${esc(r.text)}"><div class="nm">${esc(r.name)}</div>
      <div class="track"><div class="fill${r.target ? ' t' : ''}" style="width:${w.toFixed(1)}%"></div></div>
      <div class="num">${esc(r.text)}</div></div>`;
  }).join('');
}
export const spinner = '<span class="spin" aria-hidden="true"></span>';
export const ICON = {
  chat: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z"/></svg>',
  play: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M7 4l13 8-13 8z"/></svg>',
  out: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/></svg>',
  left: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4"><path d="M15 5l-7 7 7 7"/></svg>',
  right: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4"><path d="M9 5l7 7-7 7"/></svg>',
  spark: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8zM19 16l.8 2.2L22 19l-2.2.8L19 22l-.8-2.2L16 19l2.2-.8z"/></svg>',
  logout: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 4H5a1 1 0 0 0-1 1v14a1 1 0 0 0 1 1h4M16 8l4 4-4 4M20 12H9"/></svg>',
  chev: '<svg class="chev" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4"><path d="M6 9l6 6 6-6"/></svg>',
  gear: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3h0a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5h0a1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8v0a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/></svg>',
};

export function periodRange(kind, anchor) {
  const d = parse(anchor);
  if (kind === 'day') return [anchor, anchor];
  if (kind === 'week') { const s = weekStart(anchor); return [s, addDays(s, 6)]; }
  if (kind === 'month') return [ymd(new Date(d.getFullYear(), d.getMonth(), 1)), ymd(new Date(d.getFullYear(), d.getMonth() + 1, 0))];
  return [ymd(new Date(d.getFullYear(), 0, 1)), ymd(new Date(d.getFullYear(), 11, 31))];
}
