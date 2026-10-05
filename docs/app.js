/* AI 언급 인사이트 앱: docs/data/*.json 을 읽어 화면을 그린다. 빌드 도구 없음. */
(function () {
  'use strict';
  var params = new URLSearchParams(location.search);
  var BASE = params.has('demo') ? 'data-demo/' : 'data/';
  var state = { index: null, day: null, tab: 'insight', qFilter: 'all', qEngine: 'all', qText: '' };
  var app = document.getElementById('app');
  var tip = document.getElementById('tip');

  var SENT = { positive: '긍정', negative: '부정', mixed: '혼재', neutral: '중립' };
  var GROUPS = ['공식 홈페이지', '자사 앱·채널', '커뮤니티', '블로그', '언론/보도자료', '제3자 학원정보', '경쟁사 공식', '기타(영상·위키·무관)'];

  function h(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function bold(s) { return h(s).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>'); }
  function label(e) { return (state.day && state.day.engineLabels[e]) || e; }
  function pct(v) { return v == null ? '–' : v + '%'; }

  function getJSON(url) {
    return fetch(url, { cache: 'no-cache' }).then(function (r) {
      if (!r.ok) throw new Error(r.status);
      return r.json();
    });
  }

  // ---------- 공통 조각 ----------
  function bars(rows, max, cls) {
    max = max || 100;
    return rows.map(function (r) {
      var w = Math.max(0, Math.min(100, 100 * r.value / max));
      return '<div class="bar' + (cls ? ' ' + cls : '') + '" data-tip="' + h(r.name + ': ' + r.text) + '"><div class="nm">' + h(r.name) + '</div>' +
        '<div class="track"><div class="fill' + (r.target ? ' t' : '') + '" style="width:' + w.toFixed(1) + '%"></div></div>' +
        '<div class="num">' + h(r.text) + '</div></div>';
    }).join('');
  }
  function rateBars(list, nameFn) {
    return bars(list.map(function (r) {
      return { name: nameFn ? nameFn(r.key) : r.key, value: r.rate, text: r.rate + '% (' + r.hit + '/' + r.n + ')', target: true };
    }));
  }
  function stack(groups) {
    var total = groups.reduce(function (a, g) { return a + g[1]; }, 0) || 1;
    return '<div class="stack">' + groups.map(function (g, i) {
      if (!g[1]) return '';
      var p = 100 * g[1] / total;
      return '<span style="width:' + p.toFixed(2) + '%;background:var(--s' + (i + 1) + ')" data-tip="' +
        h(g[0] + ': ' + g[1] + '건 (' + p.toFixed(1) + '%)') + '"></span>';
    }).join('') + '</div>';
  }
  function legend(names, line) {
    return '<div class="legend">' + names.map(function (n, i) {
      return '<span class="' + (line ? 'line' : '') + '"><i style="background:var(--s' + (i + 1) + ')"></i>' + h(n) + '</span>';
    }).join('') + '</div>';
  }

  function trendChart(trend) {
    if (!trend || trend.length < 2) return '<p class="sub">추이는 2일 이상 측정이 쌓이면 표시됩니다.</p>';
    var engines = [];
    trend.forEach(function (t) { Object.keys(t.engines || {}).forEach(function (e) { if (engines.indexOf(e) < 0) engines.push(e); }); });
    engines.sort();
    var series = [{ name: '전체', get: function (t) { return t.rate; } }];
    if (engines.length > 1) engines.slice(0, 3).forEach(function (e) {
      series.push({ name: label(e), get: function (t) { return t.engines[e]; } });
    });
    var W = Math.max(300, Math.min(640, (app.clientWidth || 640) - 34)), H = 190, L = 34, R = 12, T = 12, B = 26;
    var x = function (i) { return L + i * (W - L - R) / (trend.length - 1); };
    var y = function (v) { return T + (1 - v / 100) * (H - T - B); };
    var out = '<svg viewBox="0 0 ' + W + ' ' + H + '" width="100%" role="img" aria-label="언급률 추이">';
    [0, 50, 100].forEach(function (g) {
      out += '<line x1="' + L + '" x2="' + (W - R) + '" y1="' + y(g) + '" y2="' + y(g) + '" stroke="var(--border)"/>' +
        '<text x="' + (L - 6) + '" y="' + (y(g) + 4) + '" text-anchor="end">' + g + '%</text>';
    });
    series.forEach(function (s, si) {
      var pts = [];
      trend.forEach(function (t, i) { var v = s.get(t); if (v != null) pts.push(x(i).toFixed(1) + ',' + y(v).toFixed(1)); });
      out += '<polyline points="' + pts.join(' ') + '" fill="none" stroke="var(--s' + (si + 1) + ')" stroke-width="2"' +
        (si ? ' stroke-opacity=".85"' : '') + '/>';
    });
    trend.forEach(function (t, i) {
      var v = t.rate;
      var lines = series.map(function (s) { var val = s.get(t); return s.name + ' ' + (val == null ? '–' : val + '%'); }).join(' · ');
      out += '<circle cx="' + x(i) + '" cy="' + y(v) + '" r="4" fill="var(--s1)" stroke="var(--surface)" stroke-width="2"/>' +
        '<rect x="' + (x(i) - 14) + '" y="' + T + '" width="28" height="' + (H - T - B) + '" fill="transparent" data-tip="' +
        h(t.date + ' — ' + lines) + '"/>';
    });
    out += '<text x="' + x(0) + '" y="' + (H - 6) + '">' + h(trend[0].date.slice(5)) + '</text>' +
      '<text x="' + x(trend.length - 1) + '" y="' + (H - 6) + '" text-anchor="end">' + h(trend[trend.length - 1].date.slice(5)) + '</text></svg>';
    return (series.length > 1 ? legend(series.map(function (s) { return s.name; }), true) : '') + out;
  }

  // ---------- 화면 ----------
  function viewInsight(d) {
    var k = d.kpi, out = '';
    var st = k.engine_status || {};
    Object.keys(st).forEach(function (e) {
      if (st[e].errors && !st[e].answered) out += '<div class="banner err">' + h(label(e)) + ': 오늘 응답 실패 ' + st[e].errors + '건 — ' + h(st[e].last_error) + '</div>';
    });
    out += '<div class="card brief"><h2 style="margin-top:0">오늘의 핵심</h2><ul>' +
      d.briefing.map(function (b) { return '<li>' + bold(b) + '</li>'; }).join('') + '</ul>';
    if (d.ai) out += '<div class="ai"><span class="tag">AI 해설 · ' + h(d.aiBy || 'AI') + '</span>' + mdToHtml(d.ai) + '</div>';
    out += '</div>';

    var delta = '';
    if (d.delta) {
      var df = d.delta.diff, cls = df > 0 ? 'up' : df < 0 ? 'down' : '';
      delta = '<div class="n"><span class="' + cls + '">' + (df > 0 ? '▲' : df < 0 ? '▼' : '–') + ' ' + Math.abs(df) + '%p</span> 전일 대비</div>';
    }
    out += '<div class="tiles">' +
      tile('오늘 언급률 (' + (k.today_basis || '오늘') + ')', pct(k.today_rate), delta + '<div class="n">' + k.today_hit + '/' + k.today_n + ' 답변</div>') +
      tile('누적 언급률 (최근 ' + k.window_days + '일)', pct(k.target_rate), '<div class="n">질문 ' + k.questions_covered + '개 · ' + k.target_mentions + '/' + k.core_responses + '</div>') +
      tile("'이투스247'만 언급", pct(k.brand_only_rate), '<div class="n">캠퍼스 혼동 신호 ' + k.campus_confusion + '건</div>') +
      tile('공식 홈페이지 인용률', pct(k.official_cited_rate), '<div class="n">기준선(9/29) 0%</div>') +
      '</div>';

    out += '<h2>언급률 추이 · 매일 같은 고정 질문</h2><div class="card">' + trendChart(d.trend) + '</div>';
    out += '<h2>AI별 · 질문 유형별 (누적)</h2><div class="card">' + rateBars(d.byEngine, label) +
      '<h3>질문 유형</h3>' + rateBars(d.byBranded) + '</div>';
    out += '<details class="card"><summary>엑셀 카테고리별 언급률</summary>' + rateBars(d.byCategory) + '</details>';
    if (d.actions.length) {
      var a = d.actions[0];
      out += '<h2>오늘 먼저 할 일</h2><div class="card act p0"><h3>' + h(a.title) + '</h3><div class="ev">' + h(a.reason) + ' · ' + a.count + '건</div>' +
        '<ul>' + a.detail.slice(0, 2).map(function (x) { return '<li>' + h(x) + '</li>'; }).join('') + '</ul>' +
        '<a href="#actions" data-go="actions">개선과제 전체 보기 →</a></div>';
    }
    out += '<div class="links">' +
      (d.files && d.files.html ? '<a href="' + h(d.files.html) + '">📊 전체 리포트</a>' : '') +
      (d.files && d.files.xlsx ? '<a href="' + h(d.files.xlsx) + '">📥 엑셀 다운로드</a>' : '') +
      '<a href="reports/">🗂 지난 리포트</a></div>';
    return out;
  }
  function tile(l, v, n) { return '<div class="tile"><div class="l">' + h(l) + '</div><div class="v">' + h(v) + '</div>' + n + '</div>'; }

  function mdToHtml(md) {
    var out = [], inList = false;
    md.split('\n').forEach(function (ln) {
      var s = ln.trim();
      if (!s) return;
      var isLi = /^([-*•]|\d+\.)\s+/.test(s);
      var body = bold(s.replace(/^([-*•]|\d+\.)\s+/, '').replace(/^#+\s*/, ''));
      if (isLi) { if (!inList) { out.push('<ul>'); inList = true; } out.push('<li>' + body + '</li>'); }
      else { if (inList) { out.push('</ul>'); inList = false; } out.push('<p>' + body + '</p>'); }
    });
    if (inList) out.push('</ul>');
    return out.join('');
  }

  function viewCompete(d) {
    var max = Math.max.apply(null, d.sov.map(function (s) { return s.rate; }).concat([1]));
    var out = '<h2>같은 소비자 질문에서 학원별 언급률</h2><div class="card">' +
      bars(d.sov.filter(function (s) { return s.mentions || s.is_target; }).map(function (s) {
        return { name: s.name, value: s.rate, text: s.rate + '%', target: s.is_target };
      }), max) + '<p class="sub">최근 ' + d.kpi.window_days + '일 동안 질문·AI별 최신 답변 기준</p></div>';
    out += '<div class="card scroll"><table><thead><tr><th>학원</th><th class="r">언급</th><th class="r">언급률</th><th class="r">점유율</th><th class="r">1순위</th><th class="r">평균순위</th></tr></thead><tbody>' +
      d.sov.map(function (s) {
        var n = s.is_target ? '<b>' + h(s.name) + '</b>' : h(s.name);
        return '<tr><td>' + n + '</td><td class="r">' + s.mentions + '</td><td class="r">' + s.rate + '%</td><td class="r">' + s.share +
          '%</td><td class="r">' + s.first + '</td><td class="r">' + (s.avg_rank == null ? '–' : s.avg_rank) + '</td></tr>';
      }).join('') + '</tbody></table></div>';
    if (d.templateCompare.length) {
      out += '<h2>학원명만 바꾼 같은 질문</h2><div class="card scroll"><table><thead><tr><th>학원</th><th class="r">언급률</th><th class="r">자사 사이트 인용</th><th>함께 언급</th></tr></thead><tbody>' +
        d.templateCompare.map(function (t) {
          return '<tr><td>' + (t.is_target ? '<b>' + h(t.name) + '</b>' : h(t.name)) + '</td><td class="r">' + t.self_rate + '%</td><td class="r">' +
            t.official_rate + '%</td><td>' + t.cross_mentions.map(function (c) { return h(c[0]) + ' ' + c[1]; }).join(', ') + '</td></tr>';
        }).join('') + '</tbody></table></div>';
    }
    out += '<h2>경쟁사만 언급될 때 AI가 본 출처</h2><div class="card">' + domTable(d.competitorDomains) + '</div>';
    return out;
  }

  function domTable(rows) {
    if (!rows || !rows.length) return '<p class="sub">해당 없음</p>';
    return '<table><thead><tr><th>도메인</th><th>유형</th><th class="r">건수</th></tr></thead><tbody>' + rows.map(function (r) {
      return '<tr><td>' + h(r[0]) + '</td><td>' + h(r[2]) + '</td><td class="r">' + r[1] + '</td></tr>';
    }).join('') + '</tbody></table>';
  }

  function viewSources(d) {
    var out = '<h2>AI는 어디를 보고 답하나</h2><div class="card">' + legend(GROUPS) +
      d.sourceMix.map(function (m) {
        var n = m.groups.reduce(function (a, g) { return a + g[1]; }, 0);
        return '<div class="bar"><div class="nm">' + h(m.name) + '</div>' + stack(m.groups) + '<div class="num">' + n + '건</div></div>';
      }).join('') +
      '<details><summary>표로 보기</summary><div class="scroll"><table><thead><tr><th>유형</th>' +
      d.sourceMix.map(function (m) { return '<th class="r">' + h(m.name) + '</th>'; }).join('') + '</tr></thead><tbody>' +
      GROUPS.map(function (g, i) {
        return '<tr><td>' + h(g) + '</td>' + d.sourceMix.map(function (m) { return '<td class="r">' + m.groups[i][1] + '</td>'; }).join('') + '</tr>';
      }).join('') + '</tbody></table></div></details>' +
      '<p class="sub">기준선은 엑셀(9/29) 웹검색 상위 노출 집계라 참고용입니다.</p></div>';
    out += '<h2>이천캠퍼스를 다룬 출처 (언급의 근거)</h2><div class="card">' + domTable(d.targetDomains) + '</div>';
    out += '<h2>가장 많이 인용된 도메인</h2><div class="card">' + domTable(d.topDomains) + '</div>';
    out += '<h2>왜 언급됐고, 왜 안 됐나</h2><div class="card"><h3>언급된 답변</h3>' + reasonTable(d.reasonsMentioned) +
      '<h3>미언급 답변</h3>' + reasonTable(d.reasonsNot) + '</div>';
    return out;
  }
  function reasonTable(rows) {
    if (!rows.length) return '<p class="sub">–</p>';
    var max = Math.max.apply(null, rows.map(function (r) { return r[1]; }));
    return bars(rows.map(function (r) { return { name: r[0], value: r[1], text: r[1] + '건', target: false }; }), max, 'long');
  }

  function viewQuestions(d) {
    var engines = [];
    d.questions.forEach(function (q) { Object.keys(q.engines).forEach(function (e) { if (engines.indexOf(e) < 0) engines.push(e); }); });
    engines.sort();
    var seg = function (key, opts) {
      return '<div class="seg" data-seg="' + key + '">' + opts.map(function (o) {
        return '<button aria-pressed="' + (state[key] === o[0]) + '" data-v="' + h(o[0]) + '">' + h(o[1]) + '</button>';
      }).join('') + '</div>';
    };
    var out = '<div class="filters"><input id="qsearch" type="search" placeholder="질문 검색" value="' + h(state.qText) + '">' +
      seg('qFilter', [['all', '전체'], ['no', '미언급'], ['yes', '언급']]) +
      seg('qEngine', [['all', '모든 AI']].concat(engines.map(function (e) { return [e, label(e)]; }))) + '</div>';
    var list = d.questions.filter(function (q) {
      if (state.qText && q.q.indexOf(state.qText) < 0) return false;
      var es = state.qEngine === 'all' ? Object.keys(q.engines) : [state.qEngine];
      var rs = es.map(function (e) { return q.engines[e]; }).filter(Boolean);
      if (!rs.length) return false;
      var any = rs.some(function (r) { return r.m; });
      return state.qFilter === 'all' || (state.qFilter === 'yes' ? any : !any);
    });
    out += '<p class="sub">' + list.length + '개 질문 · ● 언급(순위) ◐ 이투스247만 ○ 미언급</p>';
    out += list.map(function (q) {
      var es = state.qEngine === 'all' ? engines : [state.qEngine];
      return '<div class="card q"><div class="qt">' + h(q.q) + '</div><div>' +
        q.cat.map(function (c) { return '<span class="chip">' + h(c) + '</span>'; }).join('') +
        (q.branded ? '<span class="chip tg">브랜드 질문</span>' : '') + '</div><div class="eng">' +
        es.map(function (e) { return engineCell(d, e, q.engines[e]); }).join('') + '</div></div>';
    }).join('');
    return out;
  }
  function engineCell(d, e, r) {
    if (!r) return '<div class="e"><b>' + h(label(e)) + '</b><div class="sub">이번 기간 미측정</div></div>';
    var mark = r.err && !r.m && !r.src.length ? '<span class="sub">오류</span>'
      : r.m ? '<span class="ok">● ' + r.rank + '위</span>' + (r.sent ? ' <span class="sub">' + h(SENT[r.sent] || r.sent) + '</span>' : '')
        : r.brandOnly ? '<span class="half">◐ 이투스247만</span>' : '<span class="no">○ 미언급</span>';
    return '<div class="e"><b>' + h(label(e)) + '</b> ' + mark + '<div>' +
      r.comp.slice(0, 3).map(function (c) { return '<span class="chip">' + h(c) + '</span>'; }).join('') + '</div>' +
      '<details><summary>왜? · 출처 ' + r.src.length + '</summary><ul>' +
      r.reasons.map(function (c) { return '<li>' + h(d.reasonLabels[c] || c) + '</li>'; }).join('') + '</ul>' +
      (r.snippet ? '<div class="snip">“' + h(r.snippet) + '”</div>' : '') +
      (r.err ? '<div class="snip">' + h(r.err) + '</div>' : '') +
      r.src.map(function (s) {
        return '<div class="src"><a href="' + h(s.u) + '" target="_blank" rel="noopener">' + h(s.d) + '</a> <span class="chip' + (s.target ? ' tg' : '') + '">' + h(s.t) + '</span></div>';
      }).join('') + '</details></div>';
  }

  function viewActions(d) {
    if (!d.actions.length) return '<div class="empty">개선과제가 없습니다.</div>';
    return '<h2>AEO/GEO 개선과제 (우선순위)</h2>' + d.actions.map(function (a, i) {
      return '<div class="card act ' + (i < 2 ? 'p0' : i < 4 ? 'p1' : '') + '"><h3>[' + h(a.priority) + '] ' + h(a.title) +
        ' <span class="chip">' + h(a.area) + '</span></h3><div class="ev">근거: ' + h(a.reason) + ' — ' + a.count + '건 (답변의 ' + a.share + '%)</div>' +
        '<ul>' + a.detail.map(function (x) { return '<li>' + h(x) + '</li>'; }).join('') + '</ul>' +
        '<div class="ev">해당 질문 예: ' + a.examples.map(h).join(' / ') + '</div></div>';
    }).join('');
  }

  var VIEWS = { insight: viewInsight, compete: viewCompete, sources: viewSources, questions: viewQuestions, actions: viewActions };
  var TITLES = { insight: '오늘의 인사이트', compete: '경쟁 학원 비교', sources: '출처 분석', questions: '질문별 결과', actions: '개선과제' };

  function render() {
    var d = state.day;
    document.querySelectorAll('.tabs button').forEach(function (b) { b.setAttribute('aria-selected', b.dataset.tab === state.tab); });
    document.getElementById('title').textContent = TITLES[state.tab];
    if (!d) return;
    document.getElementById('target').textContent = d.target + ' · ' + d.date + ' 측정';
    var html = d.demo ? '<div class="banner demo">DEMO — 모의 데이터입니다. 실제 AI 측정값이 아닙니다.</div>' : '';
    app.innerHTML = html + VIEWS[state.tab](d) + '<p class="sub" style="margin-top:20px">업데이트 ' + h(d.generatedAt.replace('T', ' ')) + ' · AI: ' + h(d.engines.join(', ')) + '</p>';
    if (state.tab === 'questions') {
      var inp = document.getElementById('qsearch');
      inp.addEventListener('input', function () { state.qText = inp.value; var pos = inp.selectionStart; render(); var n = document.getElementById('qsearch'); n.focus(); n.setSelectionRange(pos, pos); });
    }
  }

  function loadDay(date) {
    app.innerHTML = '<div class="loading">불러오는 중…</div>';
    return getJSON(BASE + 'days/' + date + '.json').then(function (d) { state.day = d; render(); })
      .catch(function () { app.innerHTML = '<div class="empty">' + h(date) + ' 데이터를 불러오지 못했습니다.</div>'; });
  }

  function init() {
    getJSON(BASE + 'index.json').then(function (idx) {
      state.index = idx;
      var sel = document.getElementById('date');
      var days = idx.days.slice().reverse();
      sel.innerHTML = days.map(function (d) {
        return '<option value="' + h(d.date) + '">' + h(d.date) + (d.todayRate != null ? ' · ' + d.todayRate + '%' : '') + '</option>';
      }).join('');
      var want = params.get('date');
      var date = want && days.some(function (d) { return d.date === want; }) ? want : idx.latest;
      sel.value = date;
      sel.addEventListener('change', function () { loadDay(sel.value); });
      return loadDay(date);
    }).catch(function () {
      app.innerHTML = '<div class="empty"><p><b>아직 측정 데이터가 없습니다.</b></p><p>GitHub 저장소의 Actions → Daily AI mention check → Run workflow 로 첫 측정을 실행하세요.<br>매일 07:30(KST)에 자동으로 갱신됩니다.</p></div>';
    });
  }

  // 탭, 링크, 필터
  document.addEventListener('click', function (ev) {
    var t = ev.target.closest('[data-tab],[data-go],[data-seg] button');
    if (!t) return;
    if (t.dataset.tab || t.dataset.go) {
      ev.preventDefault();
      state.tab = t.dataset.tab || t.dataset.go;
      try { history.replaceState(null, '', '#' + state.tab); } catch (e) {}
      render();
      window.scrollTo(0, 0);
    } else {
      state[t.parentNode.dataset.seg] = t.dataset.v;
      render();
    }
  });
  // 툴팁 (마우스 오버 / 터치)
  function showTip(ev) {
    var el = ev.target.closest && ev.target.closest('[data-tip]');
    if (!el) { tip.hidden = true; return; }
    tip.textContent = el.getAttribute('data-tip');
    tip.hidden = false;
    var x = (ev.touches ? ev.touches[0].clientX : ev.clientX) + 12, y = (ev.touches ? ev.touches[0].clientY : ev.clientY) + 14;
    tip.style.left = Math.min(x, window.innerWidth - tip.offsetWidth - 8) + 'px';
    tip.style.top = Math.min(y, window.innerHeight - tip.offsetHeight - 80) + 'px';
  }
  document.addEventListener('mousemove', showTip);
  document.addEventListener('touchstart', showTip, { passive: true });
  document.addEventListener('scroll', function () { tip.hidden = true; }, { passive: true });

  document.getElementById('theme').addEventListener('click', function () {
    var r = document.documentElement;
    var cur = r.getAttribute('data-theme') || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
    var n = cur === 'dark' ? 'light' : 'dark';
    r.setAttribute('data-theme', n);
    try { localStorage.setItem('aeo-theme', n); } catch (e) {}
  });

  var hash = location.hash.replace('#', '');
  if (VIEWS[hash]) state.tab = hash;
  if ('serviceWorker' in navigator) navigator.serviceWorker.register('sw.js').catch(function () {});
  init();
})();
