/* 按指定级别和题型加载一组模拟题。 */
(function () {
  'use strict';

  const root = document.querySelector('#mock');
  if (!root) return;
  const types = JSON.parse(document.querySelector('#data').textContent).mock;
  const levels = ['n5', 'n4', 'n3', 'n2', 'n1'];
  const query = new URLSearchParams(location.search);
  let level = levels.includes(query.get('level')) ? query.get('level') : 'n5';
  let type = query.get('type');
  let set = 0, index = 0, answers = [], questions = [], loading = false;
  const t = (zh, ja) => '<span class="t-zh">' + zh + '</span><span class="t-ja" lang="ja">' + ja + '</span>';
  const esc = value => String(value).replace(/[&<>"]/g, char => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'})[char]);
  const jp = value => esc(value).replace(/【([^】]+)】/g, '<mark>$1</mark>');
  const button = (action, label, ghost) => '<button type="button" data-act="' + action + '" class="btn' +
    (ghost ? ' ghost' : '') + '">' + label + '</button>';

  function bank() { return types[type].levels[level]; }

  function selector(name, label, options) {
    return '<label>' + label + '<select name="' + name + '">' + options + '</select></label>';
  }

  function option(value, label, selected) {
    return '<option value="' + value + '"' + (selected ? ' selected' : '') + '>' + esc(label) + '</option>';
  }

  function setup(focus) {
    const applicable = Object.keys(types).filter(key => types[key].levels[level]);
    if (!applicable.includes(type)) type = applicable[0];
    if (set >= bank().files.length) set = 0;
    const levelOptions = levels.map(id => option(id, id.toUpperCase(), id === level)).join('');
    const typeOptions = locale => applicable.map(id => option(id, types[id].label[locale], id === type)).join('');
    const setOptions = locale => bank().files.map((_, i) => option(i, locale === 0 ? '第 ' + (i + 1) + ' 组' : 'セット ' + (i + 1), i === set)).join('');
    root.innerHTML = '<div class="q-card"><h2 class="practice-title" tabindex="-1">' +
      t('选择练习', '練習する問題を選ぶ') + '</h2><div class="practice-fields">' +
      selector('level', t('级别', 'レベル'), levelOptions) +
      t(selector('type', '题型', typeOptions(0)), selector('type', '出題形式', typeOptions(1))) +
      t(selector('set', '组别', setOptions(0)), selector('set', 'セット', setOptions(1))) +
      '</div><p class="q-sub">' +
      t('本级别 · 此题型 ' + bank().count + ' 道，每组 10 道。', 'このレベル・出題形式は全' + bank().count + '問、各セット10問です。') +
      '</p><div class="mock-links">' + button('start', t('开始练习', '練習開始')) +
      '</div><p class="mock-error" role="status"></p></div>';
    if (focus) root.querySelector(focus).focus();
  }

  async function start() {
    if (loading) return;
    loading = true;
    root.querySelectorAll('select, button').forEach(node => { node.disabled = true; });
    root.querySelector('.mock-error').innerHTML = t('正在加载本组题目…', '問題を読み込んでいます…');
    try {
      const response = await fetch(bank().files[set]);
      if (!response.ok) throw new Error('questions unavailable');
      const data = await response.json();
      if (!Array.isArray(data) || !data.length) throw new Error('empty set');
      questions = data;
      answers = [];
      index = 0;
      show();
    } catch (error) {
      setup();
      root.querySelector('.mock-error').innerHTML = t('加载失败，请再试一次。', '読み込めませんでした。もう一度お試しください。');
      root.querySelector('button[data-act="start"]').focus();
    } finally {
      loading = false;
    }
  }

  function source(item) {
    return item.src ? '<p class="practice-source"><a href="https://tatoeba.org/sentences/show/' + Number(item.src) +
      '" target="_blank" rel="noopener">' + t('例句来源 · Tatoeba', '例文の出典 · Tatoeba') + '</a></p>' : '';
  }

  function show() {
    const item = questions[index];
    const label = types[type].label;
    root.innerHTML = '<div class="q-prog"><span>' + (index + 1) + ' / ' + questions.length +
      '</span><div class="prog-bar"><i style="width:' + Math.round(index * 100 / questions.length) +
      '%"></i></div><span>' + level.toUpperCase() + '</span></div><div class="q-card">' +
      '<h2 class="practice-title" tabindex="-1">' + t(esc(label[0]), esc(label[1])) + '</h2>' +
      (item.p ? '<div class="mock-passage" lang="ja">' + jp(item.p) + '</div>' : '') +
      '<p class="q-text" lang="ja">' + jp(item.q) + '</p><ol class="opts mock-opts">' + item.opts.map((value, i) =>
        '<li><button type="button" class="opt" data-choice="' + i + '"><span class="opt-n">' + (i + 1) +
        '</span><span lang="ja">' + jp(value) + '</span></button></li>').join('') + '</ol>' +
      '<div class="q-expl" hidden></div>' + source(item) +
      '<div class="today-go mock-links"><button type="button" class="btn" data-act="next" hidden>' +
      (index + 1 === questions.length ? t('查看结果', '結果を見る') : t('下一题', '次へ')) + '</button>' +
      button('setup', t('返回选题', '問題選択に戻る'), true) + '</div></div>';
    root.querySelector('.practice-title').focus();
  }

  function choose(value) {
    if (answers.length > index) return;
    const item = questions[index];
    const correct = value === item.a;
    answers.push(value);
    root.querySelectorAll('[data-choice]').forEach((node, i) => {
      node.disabled = true;
      if (i === item.a) node.classList.add('ok');
      else if (i === value) node.classList.add('no');
    });
    const explanation = root.querySelector('.q-expl');
    explanation.hidden = false;
    explanation.classList.toggle('miss', !correct);
    explanation.innerHTML = '<b>' + (correct ? t('答对了', '正解') : t('答错了', '不正解')) +
      '</b><span lang="zh-Hans">' + esc(item.why) + '</span>';
    const next = root.querySelector('[data-act="next"]');
    next.hidden = false;
    next.focus();
  }

  function finish() {
    const missed = questions.flatMap((q, i) => answers[i] === q.a ? [] : [{q, i}]);
    const more = set + 1 < bank().files.length;
    root.innerHTML = '<div class="q-card q-result"><h2 class="practice-title" tabindex="-1">' +
      t('本组结果', 'このセットの結果') + '</h2><p class="q-score">' + (questions.length - missed.length) + '<small> / ' +
      questions.length + '</small></p><div class="today-go">' +
      (more ? button('more', t('练下一组', '次のセット')) : '') +
      button('setup', t('返回选题', '問題選択に戻る'), more) + '</div>' +
      missed.map(({q, i}) => '<details class="gd practice-report"><summary><strong>' +
        t('第 ' + (i + 1) + ' 题', '第' + (i + 1) + '問') + '</strong><span lang="ja">' + jp(q.q) + '</span></summary>' +
        '<div class="gd-body">' + (q.p ? '<div class="mock-passage" lang="ja">' + jp(q.p) + '</div>' : '') +
        '<p>' + t('你的选择 ', 'あなたの解答 ') + '<span lang="ja">' + jp(q.opts[answers[i]]) + '</span></p>' +
        '<p>' + t('正确答案 ', '正解 ') + '<strong lang="ja">' + jp(q.opts[q.a]) + '</strong></p>' +
        '<p lang="zh-Hans">' + esc(q.why) + '</p>' + source(q) + '</div></details>').join('') + '</div>';
    root.querySelector('.practice-title').focus();
  }

  root.addEventListener('change', event => {
    const field = event.target;
    if (field.name === 'level') { level = field.value; set = 0; }
    else if (field.name === 'type') { type = field.value; set = 0; }
    else if (field.name === 'set') { set = +field.value; }
    else return;
    const language = document.documentElement.dataset.ui === 'ja' ? '.t-ja ' : '.t-zh ';
    setup((field.name === 'level' ? '' : language) + 'select[name="' + field.name + '"]');
  });

  root.addEventListener('click', event => {
    const node = event.target.closest('button');
    if (!node || loading) return;
    if (node.hasAttribute('data-choice')) { choose(+node.dataset.choice); return; }
    const action = node.dataset.act;
    if (action === 'start') start();
    else if (action === 'setup') { questions = []; setup('button[data-act="start"]'); }
    else if (action === 'more') { set++; setup(); start(); }
    else if (action === 'next' && answers.length > index) {
      index++;
      if (index < questions.length) show();
      else finish();
    }
  });

  setup();
})();
