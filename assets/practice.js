/* JLPT 官方问题集答题卡，试卷与听力从官方站打开。 */
(function () {
  'use strict';

  const root = document.querySelector('#practice');
  if (!root) return;
  const keys = JSON.parse(document.querySelector('#data').textContent).practice;
  const official = 'https://www.jlpt.jp/samples/';
  const bookletMirrors = {
    'n4-2012-G': 'https://ftp.jlpt.jp/samples/sample2012/pdf/N4G.pdf',
    'n4-2012-L': 'https://ns2.jlpt.jp/samples/sample2012/pdf/N4L.pdf'
  };
  const storage = 'jlpt-practice-v1';
  const timings = {n1: [110, 60], n2: [105, 50], n3: [30, 70, 40], n4: [30, 60, 35], n5: [25, 50, 30]};
  const text = (zh, ja) => '<span class="t-zh">' + zh + '</span><span class="t-ja" lang="ja">' + ja + '</span>';
  const language = () => document.documentElement.dataset.ui === 'ja' ? 1 : 0;
  const button = (action, label, ghost) => '<button type="button" class="btn' + (ghost ? ' ghost' : '') +
    '" data-action="' + action + '">' + label + '</button>';
  const names = {
    v: text('文字・词汇', '文字・語彙'), g: text('语法', '文法'), r: text('阅读', '読解'),
    gr: text('语法・阅读', '文法・読解'), vgr: text('语言知识・阅读', '言語知識・読解'),
    l: text('听力', '聴解')
  };

  function external(url, label) {
    return '<a class="btn ghost" href="' + url + '" target="_blank" rel="noopener">' + label +
      '<span aria-hidden="true"> ↗</span></a>';
  }

  function paper(id) {
    if (!Object.prototype.hasOwnProperty.call(keys, id)) return null;
    const [level, year] = id.split('-');
    const title = level.toUpperCase() + ' · ' + year;
    const base = official + 'sample' + year + '/';
    const pdf = suffix => bookletMirrors[id + '-' + suffix] || base + 'pdf/' + level.toUpperCase() + suffix + '.pdf';
    const combined = timings[level].length === 2;
    const data = keys[id];
    const labels = [
      ['文字・词汇题册', '文字・語彙の問題冊子'], ['语法题册', '文法の問題冊子'], ['阅读题册', '読解の問題冊子']
    ];
    const parts = ['v', 'g', 'r'].map((kind, i) => {
      const first = i === 0 ? 1 : 1 + (combined ? data.v.length : 0) + (i === 2 ? data.g.length : 0);
      return {title: names[kind], keys: data[kind], choices: 4,
        numbers: Array.from(data[kind], (_, n) => first + n),
        link: external(pdf(kind.toUpperCase()), text(...labels[i]))};
    });
    const listening = data.l.map((answers, i) => {
      const group = i + 1;
      const integrated = combined && group === 5;
      const choices = (level === 'n4' || level === 'n5' ? group > 2 : !integrated && group > 3) ? 3 : 4;
      // 官方第一辑的第二大题音频由 sample2017 目录提供。
      const audioBase = year === '2012' && group === 2 ? official + 'sample2017/' : base;
      return {title: text('大题 ' + group, '問題 ' + group), keys: answers, choices,
        numbers: integrated ? [1, 2, '3 (1)', '3 (2)'] : Array.from(answers, (_, n) => n + 1),
        link: external(audioBase + 'mp3/' + level.toUpperCase() + 'Q' + group + '.mp3',
          text('大题 ' + group + ' 音频', '問題 ' + group + ' の音声'))};
    });
    const blocks = combined ? [['vgr', parts], ['l', listening]] : [['v', parts.slice(0, 1)], ['gr', parts.slice(1)], ['l', listening]];
    const sections = blocks.map(([kind, groups], i) => ({
      title: names[kind], minutes: timings[level][i], groups,
      size: groups.reduce((sum, group) => sum + group.keys.length, 0),
      links: (kind === 'l' ? external(pdf('L'), text('听力题册', '聴解の問題冊子')) : '') +
        groups.map(group => group.link).join(''),
      listening: kind === 'l'
    }));
    return {id, title, sections, answerLink: external(pdf('answer'), text('官方正答表', '公式正答表'))};
  }

  let run, exam, clock;
  const openLevel = new URLSearchParams(location.search).get('level');
  let level = /^n[1-5]$/.test(openLevel) ? openLevel : 'n5';
  let year = '2018';

  function save() {
    try {
      if (run) sessionStorage.setItem(storage, JSON.stringify(run));
      else sessionStorage.removeItem(storage);
    } catch (error) { /* 浏览器禁用存储时，仍可完成当前演练。 */ }
  }

  function restore() {
    try {
      const saved = JSON.parse(sessionStorage.getItem(storage));
      const book = saved && paper(saved.id);
      if (!book || !Array.isArray(saved.sections) || !Array.isArray(saved.answers)) return;
      const full = book.sections.map((_, i) => i).join(',');
      if (!(saved.sections.join(',') === full || (saved.sections.length === 1 && book.sections[saved.sections[0]]))) return;
      if (!Number.isInteger(saved.step) || saved.step < 0 || saved.step > saved.sections.length ||
          !Number.isFinite(saved.deadline) || saved.deadline < 0 || saved.answers.length !== saved.sections.length) return;
      if (!saved.sections.every((index, i) => {
        const groups = book.sections[index].groups, answers = saved.answers[i];
        return Array.isArray(answers) && answers.length === groups.length && groups.every((group, g) =>
          Array.isArray(answers[g]) && answers[g].length === group.keys.length &&
          answers[g].every(n => Number.isInteger(n) && n >= 0 && n <= group.choices));
      })) return;
      run = saved;
      exam = book;
      [level, year] = exam.id.split('-');
    } catch (error) { /* 损坏的或不可读的会话从题库重新开始。 */ }
  }

  function card(title, content) {
    return '<div class="q-card"><h2 class="practice-title" tabindex="-1">' + title + '</h2>' + content + '</div>';
  }

  function show(markup, focus) {
    root.innerHTML = markup;
    if (focus) root.querySelector('.practice-title').focus();
  }

  function options(values, selected, display) {
    return values.map(value => '<option value="' + value + '"' + (value === selected ? ' selected' : '') + '>' +
      display(value) + '</option>').join('');
  }

  function bank(focus) {
    clearInterval(clock);
    show(card(text('选择试卷', '問題集を選ぶ'),
      '<div class="practice-fields"><label>' + text('级别', 'レベル') + '<select name="level">' +
      options(['n5', 'n4', 'n3', 'n2', 'n1'], level, value => value.toUpperCase()) + '</select></label><label>' +
      text('问题集版本', '問題集の版') + '<select name="year">' + options(['2018', '2012'], year, value => value) +
      '</select></label></div><div id="practice-sets"></div>'), focus);
    updateBank();
  }

  function sectionStats(section) {
    return text(section.size + ' 题 · ' + section.minutes + ' 分钟', section.size + ' 問 · ' + section.minutes + ' 分');
  }

  function updateBank() {
    const book = paper(level + '-' + year);
    root.querySelector('#practice-sets').innerHTML =
      '<p class="q-sub">' + text('按题册出版时的考试时长计时。', '問題集の刊行当時の試験時間で計時します。') + '</p>' +
      '<ul class="practice-sections">' + book.sections.map((section, i) =>
        '<li><div><strong>' + section.title + '</strong><p>' + sectionStats(section) + '</p></div>' +
        button('section-' + i, text('练此科', 'この科目を練習'), true) + '</li>').join('') + '</ul>' +
      button('full', text('演练整套', '全科目を練習'));
  }

  function begin(index) {
    exam = paper(level + '-' + year);
    const sections = index == null ? exam.sections.map((_, i) => i) : [index];
    run = {id: exam.id, sections, step: 0, deadline: 0, answers: sections.map(i =>
      exam.sections[i].groups.map(group => Array(group.keys.length).fill(0)))};
    save();
    render(true);
  }

  function section() { return exam.sections[run.sections[run.step]]; }
  function ready(expired, focus) {
    const s = section();
    const message = s.listening
      ? text('音频会在新标签页打开。开始计时后，按大题顺序播放并回到这里作答。',
        '音声は新しいタブで開きます。計時を始めてから、問題順に再生してこの画面で解答してください。')
      : text('题册会在新标签页打开。准备好后开始计时，按题册的题号作答。',
        '問題冊子は新しいタブで開きます。準備ができたら計時を始め、冊子の番号に従って解答してください。');
    show(card(s.title,
      '<p class="q-lab">' + exam.title + ' · ' + (run.step + 1) + ' / ' + run.sections.length + '</p>' +
      (expired ? '<p role="status">' + text('上一科时间到，已自动交卷。', '前の科目は時間終了で提出しました。') + '</p>' : '') +
      '<p>' + sectionStats(s) + '</p><p class="q-sub">' + message + '</p><div class="practice-links">' + s.links +
      '</div><div class="today-go">' + button('start', text('开始计时', '計時を開始')) +
      button('leave', text('返回题库', '問題集へ戻る'), true) + '</div>'), focus);
  }

  function rows(group, gi) {
    return '<fieldset class="practice-group"><legend>' + group.title + '</legend>' +
      group.numbers.map((num, i) => {
        const id = 'p-' + gi + '-' + i;
        return '<div class="practice-row"><span id="' + id + '">' + num +
          '</span><div class="practice-picks" role="group" aria-labelledby="' + id + '">' +
          Array.from({length: group.choices}, (_, j) => {
            const value = j + 1;
            return '<label><input type="radio" name="' + id + '" data-group="' + gi + '" data-item="' + i +
              '" value="' + value + '"' + (run.answers[run.step][gi][i] === value ? ' checked' : '') +
              '><span>' + value + '</span></label>';
          }).join('') + '</div></div>';
      }).join('') + '</fieldset>';
  }

  function answerSheet(focus) {
    const s = section();
    show('<div class="q-prog practice-progress"><span>' + text('剩余 ', '残り ') + '<time></time></span>' +
      '<div class="prog-bar"><i></i></div><span class="practice-answered"></span></div>' +
      card(s.title, '<p class="q-lab">' + exam.title + ' · ' + (run.step + 1) + ' / ' + run.sections.length + '</p>' +
      '<div class="practice-links">' + s.links + '</div>' + s.groups.map(rows).join('') +
      '<div class="today-go practice-actions">' + button('submit', text('交本场答题卡', 'この科目を提出')) +
      button('leave', text('返回题库', '問題集へ戻る'), true) + '</div>'), focus);
    updateAnswered();
    tick();
    if (run.deadline) clock = setInterval(tick, 1000);
  }

  function updateAnswered() {
    const answered = run.answers[run.step].reduce((sum, group) => sum + group.filter(Boolean).length, 0);
    root.querySelector('.practice-answered').textContent = answered + ' / ' + section().size;
    root.querySelector('.practice-progress i').style.width = (100 * answered / section().size) + '%';
  }

  function tick() {
    if (!run || !run.deadline) return;
    const seconds = Math.ceil((run.deadline - Date.now()) / 1000);
    if (seconds <= 0) { submit(true); return; }
    const time = root.querySelector('time');
    time.textContent = Math.floor(seconds / 60) + ':' + String(seconds % 60).padStart(2, '0');
  }

  function submit(expired) {
    run.step++;
    run.deadline = 0;
    save();
    render(true, expired);
  }

  function result(focus, expired) {
    let total = 0, correct = 0;
    const reports = run.sections.map((index, step) => {
      const s = exam.sections[index];
      let score = 0, blank = 0;
      const miss = s.groups.map((group, gi) => {
        const wrong = group.numbers.map((num, i) => {
          const picked = run.answers[step][gi][i], key = +group.keys[i];
          if (picked === key) { score++; return ''; }
          if (!picked) blank++;
          return '<li>' + num + ' · ' + text('作答 ', '解答 ') + (picked || '—') +
            ' · <span class="ans">' + text('正确 ', '正解 ') + key + '</span></li>';
        }).join('');
        return wrong ? '<h3>' + group.title + '</h3><ul class="q-miss">' + wrong + '</ul>' : '';
      }).join('');
      total += s.size;
      correct += score;
      return '<details class="gd practice-report"><summary><strong>' + s.title + '</strong><span>' + score + ' / ' + s.size +
        ' · ' + text('未答 ', '未解答 ') + blank + '</span></summary><div class="gd-body">' +
        (miss || '<p>' + text('本场全对。', '全問正解です。') + '</p>') + '</div></details>';
    }).join('');
    show(card(text('演练结果', '演習結果'), '<div class="q-result"><p class="q-lab">' + exam.title + '</p>' +
      (expired ? '<p role="status">' + text('时间到，已自动交卷。', '時間終了で提出しました。') + '</p>' : '') +
      '<p class="q-score">' + correct + '<small> / ' + total + '</small></p><p>' +
      text('按答对题数计分。展开各科查看错题和未答题。', '正解数を表示します。科目を開くと誤答と未解答を確認できます。') +
      '</p>' + reports + '<div class="today-go">' + button('bank', text('返回题库', '問題集へ戻る')) +
      exam.answerLink + '</div></div>'), focus);
  }

  function render(focus, expired) {
    clearInterval(clock);
    if (!run) bank(focus);
    else if (run.step === run.sections.length) result(focus, expired);
    else if (run.deadline) answerSheet(focus);
    else ready(expired, focus);
  }

  root.addEventListener('change', event => {
    const field = event.target;
    if (field.name === 'level' || field.name === 'year') {
      if (field.name === 'level') level = field.value;
      else year = field.value;
      updateBank();
    } else if (run && run.deadline && field.type === 'radio') {
      if (Date.now() >= run.deadline) { submit(true); return; }
      run.answers[run.step][field.dataset.group][field.dataset.item] = +field.value;
      save();
      updateAnswered();
    }
  });

  root.addEventListener('click', event => {
    const action = event.target.closest('button[data-action]')?.dataset.action;
    if (!action) return;
    if (action === 'full') begin();
    else if (action.startsWith('section-')) begin(+action.slice(8));
    else if (action === 'start') {
      run.deadline = Date.now() + section().minutes * 60 * 1000;
      save();
      render(true);
    } else if (action === 'submit') submit(Date.now() >= run.deadline);
    else if (action === 'bank' || (action === 'leave' && confirm(
      ['结束这次演练并返回题库？当前作答将清除。', '今回の演習を終了しますか。解答は消去されます。'][language()]))) {
      run = null;
      save();
      render(true);
    }
  });

  document.addEventListener('visibilitychange', tick);
  window.addEventListener('pageshow', tick);
  restore();
  render(false);
})();
