/* JLPT 学习站：界面切换、间隔重复卡片、测验。无依赖；学习记录存在 localStorage。 */
(function () {
  'use strict';
  var d = document, H = d.documentElement;

  function get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
  function put(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* 隐私模式下可能写不进去 */ } }
  function del(k) { try { localStorage.removeItem(k); } catch (e) { /* 同上 */ } }
  function load(k) { try { var v = JSON.parse(get(k)); return v && typeof v === 'object' ? v : {}; } catch (e) { return {}; } }
  function $(s, r) { return (r || d).querySelector(s); }
  function $$(s, r) { return Array.prototype.slice.call((r || d).querySelectorAll(s)); }
  function t(zh, ja) { return '<span class="t-zh">' + zh + '</span><span class="t-ja" lang="ja">' + ja + '</span>'; }
  function J(s) { return '<span lang="ja">' + s + '</span>'; }
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
  function shuffle(a) {
    a = a.slice();
    for (var i = a.length - 1; i > 0; i--) { var j = Math.floor(Math.random() * (i + 1)), x = a[i]; a[i] = a[j]; a[j] = x; }
    return a;
  }
  function typing(e) { var n = e.target && e.target.tagName; return n === 'INPUT' || n === 'TEXTAREA' || n === 'SELECT' || e.metaKey || e.ctrlKey || e.altKey; }

  /* ---------- 界面：语言、注音、主题 ---------- */
  var TITLE_ZH = d.title, TITLE_JA = H.getAttribute('data-title-ja') || d.title;
  function applyUi() { d.title = H.getAttribute('data-ui') === 'ja' ? TITLE_JA : TITLE_ZH; }
  applyUi();
  var bUi = $('#ui'), bFuri = $('#furi'), bTheme = $('#theme');
  if (bUi) bUi.addEventListener('click', function () {
    var v = H.getAttribute('data-ui') === 'ja' ? 'zh' : 'ja';
    H.setAttribute('data-ui', v); put('jlpt-ui', v); applyUi();
  });
  if (bFuri) {
    bFuri.setAttribute('aria-pressed', String(H.getAttribute('data-furi') !== 'off'));
    bFuri.addEventListener('click', function () {
      var on = H.getAttribute('data-furi') === 'off';
      H.setAttribute('data-furi', on ? 'on' : 'off'); put('jlpt-furi', on ? 'on' : 'off');
      bFuri.setAttribute('aria-pressed', String(on));
    });
  }
  if (bTheme) bTheme.addEventListener('click', function () {
    var v = H.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    H.setAttribute('data-theme', v); put('jlpt-theme', v);
  });

  /* ---------- 间隔重复 ----------
     每张卡记 [盒子 0–5, 到期日]。认识 → 升一盒，间隔 1/3/7/14/30 天；模糊 → 明天再看；不认识 → 回到 0，本轮稍后重出。 */
  var INT = [0, 1, 3, 7, 14, 30];
  var srs = load('jlpt-srs');
  function today() { var n = new Date(); return Math.floor((n.getTime() - n.getTimezoneOffset() * 60000) / 86400000); }
  function status(id) {
    var s = srs[id];
    if (!s) return 'new';
    if (s[1] <= today()) return 'due';
    return s[0] >= 4 ? 'known' : 'learning';
  }
  function saveSrs() { put('jlpt-srs', JSON.stringify(srs)); }
  var ST = {
    'new': ['未学', '未学習'], due: ['待复习', '復習'], learning: ['学习中', '学習中'], known: ['已掌握', '定着']
  };

  /* ---------- 首页与级别概览的进度 ---------- */
  function paintProgress() {
    var td = today();
    $$('[data-prog]').forEach(function (el) {
      var lv = el.getAttribute('data-prog') + ':', total = +el.getAttribute('data-total') || 1, n = 0;
      for (var id in srs) if (id.indexOf(lv) === 0 && srs[id][0] >= 1) n++;
      $('i', el).style.width = Math.min(100, Math.round(100 * n / total)) + '%';
      $('.prog-t', el).innerHTML = t('已学 ', '学習済み ') + n + ' / ' + total;
    });
    $$('[data-today]').forEach(function (el) {
      var lv = el.getAttribute('data-today') + ':', total = (+el.getAttribute('data-v')) + (+el.getAttribute('data-k'));
      var seen = 0, due = 0, known = 0;
      for (var id in srs) if (id.indexOf(lv) === 0) {
        seen++;
        if (srs[id][1] <= td) due++; else if (srs[id][0] >= 4) known++;
      }
      var fresh = Math.max(0, total - seen);
      $('.today-t', el).innerHTML = t('待复习 ' + due + ' 张 · 未学 ' + fresh + ' 张 · 已掌握 ' + known + ' 张',
        '復習 ' + due + ' 枚 · 未学習 ' + fresh + ' 枚 · 定着 ' + known + ' 枚');
    });
  }
  paintProgress();

  var bReset = $('#reset');
  if (bReset) {
    var armed = false, label = bReset.innerHTML, timer;
    bReset.addEventListener('click', function () {
      if (!armed) {
        armed = true; bReset.innerHTML = t('再点一次，确认清除', 'もう一度押すと消去します');
        timer = setTimeout(function () { armed = false; bReset.innerHTML = label; }, 5000);
        return;
      }
      clearTimeout(timer); armed = false;
      del('jlpt-srs'); del('jlpt-quiz'); srs = {};
      paintProgress(); bReset.innerHTML = t('已清除', '消去しました');
      setTimeout(function () { bReset.innerHTML = label; }, 2500);
    });
  }

  var DATA = null, dataEl = $('#data');
  if (dataEl) { try { DATA = JSON.parse(dataEl.textContent); } catch (e) { DATA = null; } }

  /* ---------- 列表 + 卡片（单词、汉字共用） ---------- */
  function initDeck(data) {
    var root = $('#deck'), list = $('#list'), search = $('#search'), empty = $('#empty');
    if (!root || !list || !data || !data.items) return;
    var NEW = 10, items = data.items, kind = data.kind;
    var rows = {};
    $$('[data-id]', list).forEach(function (li) { rows[li.getAttribute('data-id')] = li; });
    function paintRow(id) {
      var li = rows[id]; if (!li) return;
      var s = status(id); li.setAttribute('data-st', s);
      var dot = $('.st', li); if (dot) dot.title = ST[s][0] + ' / ' + ST[s][1];
    }
    items.forEach(function (it) { paintRow(it.id); });

    if (search) search.addEventListener('input', function () {
      var q = search.value.trim().toLowerCase(), n = 0;
      $$('[data-k]', list).forEach(function (li) {
        var hit = !q || li.getAttribute('data-k').indexOf(q) >= 0;
        li.hidden = !hit; if (hit) n++;
      });
      if (empty) empty.hidden = n > 0;
    });

    var queue = [], cur = null, flipped = false, started = false;
    function tally() { var n = { 'new': 0, due: 0, learning: 0, known: 0 }; items.forEach(function (it) { n[status(it.id)]++; }); return n; }
    function start() {
      var due = [], fresh = [];
      items.forEach(function (it) { var s = status(it.id); if (s === 'due') due.push(it); else if (s === 'new') fresh.push(it); });
      queue = shuffle(due).concat(fresh.slice(0, NEW)); started = true; next();
    }
    function cram() { queue = shuffle(items); next(); }
    function next() { cur = queue.shift() || null; flipped = false; render(); }

    function back(it) {
      if (kind === 'k') {
        return '<p class="c-m">' + esc(it.m) + '</p>' +
          '<dl class="k-yomi"><dt>' + t('音读', '音読み') + '</dt><dd lang="ja">' + esc(it.on) +
          '</dd><dt>' + t('训读', '訓読み') + '</dt><dd lang="ja">' + esc(it.kun) + '</dd></dl>' +
          '<ul class="c-ws">' + it.ws.map(function (w) {
            return '<li><span class="k-w" lang="ja">' + esc(w[0]) + '</span><span class="kana" lang="ja">' + esc(w[1]) + '</span><span class="k-wz">' + esc(w[2]) + '</span></li>';
          }).join('') + '</ul>';
      }
      return (it.r !== it.w ? '<p class="c-r" lang="ja">' + esc(it.r) + '</p>' : '') +
        '<p class="c-m"><span class="pos">' + t(it.pos[0], it.pos[1]) + '</span>' + esc(it.m) + '</p>' +
        '<p class="c-x" lang="ja">' + it.x + '</p><span class="ex-zh">' + esc(it.xz) + '</span>';
    }
    function render() {
      var n = tally();
      var head = '<div class="deck-top"><span>' + t('本轮剩余', '残り') + ' <b>' + (queue.length + (cur ? 1 : 0)) + '</b></span><span>' +
        t('未学', '未学習') + ' ' + n['new'] + ' · ' + t('待复习', '復習') + ' ' + n.due + ' · ' + t('学习中', '学習中') + ' ' + n.learning + ' · ' + t('已掌握', '定着') + ' ' + n.known + '</span></div>';
      if (!cur) {
        var more = n['new'] > 0 || n.due > 0;
        root.innerHTML = head + '<div class="deck-done"><h2>' + t('这一轮完成了', 'このセットは終了です') + '</h2><p>' +
          (more ? t('还有没学过或到期的卡片，可以继续。', 'まだ未学習・復習待ちのカードがあります。')
            : t('今天没有到期的卡片了。已掌握的卡片到期后会再出现。', '今日の復習はもうありません。定着したカードも期限が来るとまた出題されます。')) +
          '</p><div class="today-go">' + (more ? '<button type="button" class="btn" data-act="more">' + t('继续学习', '続ける') + '</button>' : '') +
          '<button type="button" class="btn ghost" data-act="cram">' + t('全部过一遍', '全部もう一度') + '</button></div></div>';
        return;
      }
      root.innerHTML = head +
        '<div class="card' + (kind === 'k' ? ' k' : '') + '" role="button" tabindex="0" aria-label="' + (flipped ? '' : '翻面 / めくる') + '">' +
        '<div class="card-front" lang="ja">' + esc(cur.w) + '</div>' +
        (flipped ? '<div class="card-back">' + back(cur) + '</div>' : '<p class="card-tip">' + t('先回想读音和意思，再点卡片翻面', '読みと意味を思い出してから、カードをめくる') + '</p>') +
        '</div>' +
        (flipped ? '<div class="rate">' +
          '<button type="button" class="r0" data-g="0">' + t('不认识', 'まだ') + '<small>' + t('本轮再出现', 'あとでもう一度') + '</small></button>' +
          '<button type="button" class="r1" data-g="1">' + t('模糊', 'あいまい') + '<small>' + t('明天', '明日') + '</small></button>' +
          '<button type="button" class="r2" data-g="2">' + t('认识', 'わかる') + '<small>' + gap(cur) + '</small></button></div>' : '') +
        '<p class="hint"><kbd>Space</kbd> ' + t('翻面', 'めくる') + ' · <kbd>1</kbd> <kbd>2</kbd> <kbd>3</kbd> ' + t('评分', '評価') + '</p>';
    }
    function gap(it) {
      var s = srs[it.id], b = Math.min(5, (s ? s[0] : 0) + 1);
      return t(INT[b] + ' 天后', INT[b] + ' 日後');
    }
    function flip() { if (cur && !flipped) { flipped = true; render(); var b = $('.r2', root); if (b) b.focus(); } }
    function rate(g) {
      if (!cur || !flipped) return;
      var td = today(), s = srs[cur.id], b = s ? s[0] : 0;
      if (g === 0) { srs[cur.id] = [0, td]; queue.splice(Math.min(queue.length, 3), 0, cur); }
      else if (g === 1) { srs[cur.id] = [Math.max(1, b), td + 1]; }
      else { b = Math.min(5, b + 1); srs[cur.id] = [b, td + INT[b]]; }
      saveSrs(); paintRow(cur.id); next();
      var c = $('.card', root); if (c) c.focus();
    }
    root.addEventListener('click', function (e) {
      var b = e.target.closest('button');
      if (b && b.hasAttribute('data-g')) return rate(+b.getAttribute('data-g'));
      if (b && b.getAttribute('data-act') === 'more') return start();
      if (b && b.getAttribute('data-act') === 'cram') return cram();
      if (e.target.closest('.card')) flip();
    });
    d.addEventListener('keydown', function (e) {
      if (root.hidden || typing(e)) return;
      var onBtn = e.target && e.target.tagName === 'BUTTON';
      if ((e.key === ' ' || e.key === 'Enter') && !onBtn && cur && !flipped) { e.preventDefault(); flip(); }
      else if (flipped && (e.key === '1' || e.key === '2' || e.key === '3')) { e.preventDefault(); rate(+e.key - 1); }
    });

    var segs = $$('.seg button');
    function setMode(m, quiet) {
      var cards = m === 'cards';
      root.hidden = !cards; list.hidden = cards;
      if (search) search.hidden = cards;
      if (empty && cards) empty.hidden = true;
      segs.forEach(function (b) { b.setAttribute('aria-pressed', String(b.getAttribute('data-mode') === m)); });
      if (cards && !started) start();
      if (!quiet && window.history && history.replaceState) {
        try { history.replaceState(null, '', cards ? '#cards' : location.pathname + location.search); } catch (e) { /* file:// 下忽略 */ }
      }
    }
    segs.forEach(function (b) { b.addEventListener('click', function () { setMode(b.getAttribute('data-mode')); }); });
    if (location.hash === '#cards') setMode('cards', true);
    window.addEventListener('hashchange', function () { setMode(location.hash === '#cards' ? 'cards' : 'list', true); });
  }

  /* ---------- 测验 ---------- */
  function initQuiz(data) {
    var root = $('#quiz');
    if (!root || !data) return;
    var N = 10;
    var V = data.v.map(function (x) { return { w: x[0], r: x[1], m: x[2], x: x[3], xz: x[4] }; });
    var KW = data.kw.map(function (x) { return { w: x[0], r: x[1], m: x[2] }; });
    var seen = {}, READ = [];
    V.concat(KW).forEach(function (o) { if (o.w !== o.r && !seen[o.w]) { seen[o.w] = 1; READ.push(o); } });
    var KAN = KW.filter(function (o) { return o.w !== o.r; });
    var TYPES = [
      ['mix', t('综合', '総合'), t('词义、读音、汉字、语法各出几题。', '意味・読み・表記・文法から少しずつ出題。')],
      ['mean', t('词义', '意味'), t('看日语单词，选中文意思。', '日本語の単語を見て、中国語の意味を選ぶ。')],
      ['read', t('读音', '読み'), t('看汉字写法，选正确的读音。', '漢字を見て、正しい読みを選ぶ。')],
      ['kanji', t('汉字', '表記'), t('看读音和意思，选正确的汉字写法。', '読みと意味を見て、正しい表記を選ぶ。')],
      ['gram', t('语法', '文法'), t('选出填入括号的正确说法，带解说。', '（　）に入る正しい表現を選ぶ。解説付き。')]
    ];
    var type = 'mix', qs = [], i = 0, score = 0, miss = [], done = false;

    function pick(pool, n) { return shuffle(pool).slice(0, n); }
    function others(pool, item, key, n) {  // 取 n 个干扰项：值不同、互不重复，优先长度接近的
      var L = item[key].length, used = {}, c = [];
      used[item[key]] = 1;
      shuffle(pool).forEach(function (o) { if (!used[o[key]]) { used[o[key]] = 1; c.push(o); } });
      c.sort(function (a, b) { return Math.abs(a[key].length - L) - Math.abs(b[key].length - L); });
      return shuffle(c.slice(0, Math.max(n, 6))).slice(0, n);
    }
    function word(o) { return J(esc(o.w)) + (o.r !== o.w ? '（' + J(esc(o.r)) + '）' : '') + ' ' + esc(o.m); }
    function wordEx(o) { return word(o) + (o.x ? '<br>' + J(o.x) + '<span class="ex-zh">' + esc(o.xz) + '</span>' : ''); }
    function mk(lab, body, right, wrongs, expl) {
      var opts = shuffle([right].concat(wrongs));
      return { lab: lab, body: body, opts: opts, ans: opts.indexOf(right), expl: expl };
    }
    function qMean(o) {
      return mk(t('这个词是什么意思？', 'この言葉の意味は？'),
        '<p class="q-big" lang="ja">' + (o.r !== o.w ? '<ruby>' + esc(o.w) + '<rt>' + esc(o.r) + '</rt></ruby>' : esc(o.w)) + '</p>',
        esc(o.m), others(V, o, 'm', 3).map(function (x) { return esc(x.m); }), wordEx(o));
    }
    function qRead(o) {
      return mk(t('这个词怎么读？', 'この言葉の読み方は？'), '<p class="q-big" lang="ja">' + esc(o.w) + '</p>',
        J(esc(o.r)), others(READ, o, 'r', 3).map(function (x) { return J(esc(x.r)); }), wordEx(o));
    }
    function qKanji(o) {
      return mk(t('用汉字怎么写？', '漢字でどう書く？'), '<p class="q-big" lang="ja">' + esc(o.r) + '</p><p class="q-sub">' + esc(o.m) + '</p>',
        J(esc(o.w)), others(KAN, o, 'w', 3).map(function (x) { return J(esc(x.w)); }), word(o));
    }
    function qGram(g) {
      return mk(t('选出填入（　）的正确说法', '（　）に入る最もよいものを選ぶ'), '<p class="q-text" lang="ja">' + g[0] + '</p>',
        J(g[1][0]), g[1].slice(1).map(J), esc(g[2]));
    }
    function make() {
      var q;
      if (type === 'mean') q = pick(V, N).map(qMean);
      else if (type === 'read') q = pick(READ, N).map(qRead);
      else if (type === 'kanji') q = pick(KAN, N).map(qKanji);
      else if (type === 'gram') q = pick(data.g, N).map(qGram);
      else q = shuffle(pick(V, 3).map(qMean).concat(pick(READ, 2).map(qRead), pick(KAN, 2).map(qKanji), pick(data.g, 3).map(qGram)));
      return q;
    }
    function best() { var b = load('jlpt-quiz')[data.level + ':' + type]; return b ? b[0] + ' / ' + b[1] : null; }

    function setup() {
      done = false;
      var cur = TYPES.filter(function (x) { return x[0] === type; })[0], b = best();
      root.innerHTML = '<div class="q-setup"><h2>' + t('选择题型', '出題タイプを選ぶ') + '</h2><div class="chips" role="group">' +
        TYPES.map(function (x) { return '<button type="button" class="chip" data-type="' + x[0] + '" aria-pressed="' + (x[0] === type) + '">' + x[1] + '</button>'; }).join('') +
        '</div><p class="q-desc">' + cur[2] + (b ? '<br>' + t('最好成绩 ', 'ベスト ') + b : '') + '</p>' +
        '<button type="button" class="btn" data-act="start">' + t('开始', 'スタート') + '</button></div>';
    }
    function begin() { qs = make(); i = 0; score = 0; miss = []; done = false; show(); }
    function show() {
      var q = qs[i];
      root.innerHTML = '<div class="q-prog"><span>' + (i + 1) + ' / ' + qs.length + '</span><div class="prog-bar"><i style="width:' + Math.round(100 * i / qs.length) + '%"></i></div><span>' +
        t('答对 ', '正解 ') + score + '</span></div><div class="q-card"><p class="q-lab">' + q.lab + '</p>' + q.body +
        '<ol class="opts">' + q.opts.map(function (o, k) {
          return '<li><button type="button" class="opt" data-i="' + k + '"><span class="opt-n">' + (k + 1) + '</span><span>' + o + '</span></button></li>';
        }).join('') + '</ol><div class="q-expl" hidden></div>' +
        '<button type="button" class="btn q-next" data-act="next" hidden>' + (i + 1 < qs.length ? t('下一题', '次へ') : t('看结果', '結果を見る')) + '</button></div>';
    }
    function answer(k) {
      var q = qs[i];
      if (q.picked != null) return;
      q.picked = k;
      var ok = k === q.ans;
      if (ok) score++; else miss.push(q);
      $$('.opt', root).forEach(function (b, n) {
        b.disabled = true;
        if (n === q.ans) b.classList.add('ok'); else if (n === k) b.classList.add('no');
      });
      var ex = $('.q-expl', root);
      ex.className = 'q-expl' + (ok ? '' : ' miss');
      ex.innerHTML = '<b>' + (ok ? t('答对了', '正解') : t('答错了', '不正解')) + '</b>' + q.expl;
      ex.hidden = false;
      var nx = $('.q-next', root); nx.hidden = false; nx.focus();
    }
    function result() {
      done = true;
      var all = load('jlpt-quiz'), key = data.level + ':' + type, b = all[key];
      if (!b || score / qs.length > b[0] / b[1]) { all[key] = [score, qs.length]; put('jlpt-quiz', JSON.stringify(all)); }
      var rate = score / qs.length;
      var msg = rate === 1 ? t('全对！', '全問正解！') : rate >= 0.7 ? t('不错，把错的再看一遍就更稳了。', 'いい調子です。間違えた問題を見直しましょう。')
        : t('先回去看看讲解和卡片，再来一组。', '解説とカードを見直してから、もう一度挑戦しましょう。');
      root.innerHTML = '<div class="q-result"><p class="q-score">' + score + '<small> / ' + qs.length + '</small></p><p>' + msg + '</p>' +
        '<div class="today-go"><button type="button" class="btn" data-act="start">' + t('再来一组', 'もう1セット') + '</button>' +
        '<button type="button" class="btn ghost" data-act="setup">' + t('换题型', 'タイプを変える') + '</button></div>' +
        (miss.length ? '<h3>' + t('错题回顾', '間違えた問題') + '</h3><ol class="q-miss">' + miss.map(function (q) {
          return '<li>' + q.body.replace('q-big', 'q-text') + '<p class="ans">' + t('正确答案：', '正解：') + q.opts[q.ans] + '</p><p>' + q.expl + '</p></li>';
        }).join('') + '</ol>' : '') + '</div>';
    }
    root.addEventListener('click', function (e) {
      var b = e.target.closest('button'); if (!b) return;
      if (b.hasAttribute('data-type')) { type = b.getAttribute('data-type'); setup(); var c = $('.chip[aria-pressed="true"]', root); if (c) c.focus(); return; }
      if (b.hasAttribute('data-i')) return answer(+b.getAttribute('data-i'));
      var act = b.getAttribute('data-act');
      if (act === 'start') begin();
      else if (act === 'setup') setup();
      else if (act === 'next') { i++; if (i < qs.length) show(); else result(); }
    });
    d.addEventListener('keydown', function (e) {
      if (typing(e) || done || !qs.length || !$('.q-card', root)) return;
      var q = qs[i];
      if (q.picked == null && /^[1-4]$/.test(e.key) && +e.key <= q.opts.length) { e.preventDefault(); answer(+e.key - 1); }
    });
    setup();
  }

  /* ---------- 辞典 / 语法词典：搜索与筛选 ---------- */
  function initLex() {
    var box = $('[data-lex]'); if (!box) return;
    var q = $('#q', box), count = $('#lx-count', box), empty = $('#empty', box);
    var items = $$('[data-k]', box), groups = $$('.lx-group', box), total = items.length;
    var f = { lv: '', ty: '' };
    function norm(s) {  // 小写；片假名转平假名
      return s.toLowerCase().replace(/[ァ-ヶ]/g, function (c) { return String.fromCharCode(c.charCodeAt(0) - 0x60); });
    }
    function apply(push) {
      var toks = norm(q.value).split(/\s+/).filter(Boolean), n = 0;
      items.forEach(function (el) {
        var k = el.getAttribute('data-k');
        var ok = (!f.lv || (' ' + el.getAttribute('data-lv') + ' ').indexOf(' ' + f.lv + ' ') >= 0) &&
          (!f.ty || el.getAttribute('data-ty') === f.ty) && toks.every(function (x) { return k.indexOf(x) >= 0; });
        el.hidden = !ok; if (ok) n++;
      });
      groups.forEach(function (g) {
        var has = !!$('[data-k]:not([hidden])', g);
        g.hidden = !has;
        var a = $('.jump a[href="#' + g.id + '"]', box); if (a) a.setAttribute('aria-disabled', String(!has));
      });
      if (toks.length) $$('details[data-k]', box).forEach(function (el) { el.open = !el.hidden && n <= 3; });
      if (count) count.innerHTML = t('显示 ' + n + ' / ' + total + ' 条', n + ' / ' + total + ' 件を表示');
      if (empty) empty.hidden = n > 0;
      if (push && window.history && history.replaceState) {
        var v = q.value.trim();
        try { history.replaceState(null, '', location.pathname + (v ? '?q=' + encodeURIComponent(v) : '')); } catch (e) { /* 忽略 */ }
      }
    }
    $$('.chips[data-f]', box).forEach(function (grp) {
      var key = grp.getAttribute('data-f');
      grp.addEventListener('click', function (e) {
        var b = e.target.closest('.chip'); if (!b) return;
        f[key] = b.getAttribute('data-v');
        $$('.chip', grp).forEach(function (c) { c.setAttribute('aria-pressed', String(c === b)); });
        apply(false);
      });
    });
    q.addEventListener('input', function () { apply(true); });
    try { var init = new URLSearchParams(location.search).get('q'); if (init) q.value = init; } catch (e) { /* 旧浏览器忽略 */ }
    apply(false);
  }

  initLex();
  if (DATA && DATA.items) initDeck(DATA);
  if (DATA && DATA.g) initQuiz(DATA);
})();
