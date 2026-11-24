#!/usr/bin/env python3
"""内容与构建检查：python3 verify.py（有问题时退出码为 1）。

- 例句、题目里的每个汉字都要有注音（漢字[かんじ]）
- 读音只能是假名；同一级别内单词、汉字不重复
- 测验题的 4 个选项互不相同
- dist/ 里的站内链接都指向存在的文件
"""
import html
import json
import os
import re
import subprocess
import sys
from urllib.parse import urlsplit

import build
from content.mock_yomi import hira as reading_hira, plausible as plausible_reading

KANJI = re.compile(r'[一-鿿々]')
KANA = re.compile(r'^[ぁ-ゖァ-ー・（）]+$')
errors = []


def err(*a):
    errors.append(' '.join(str(x) for x in a))


def check_ruby(where, s):
    rest = build.RUBY.sub('', s)
    left = KANJI.findall(rest)
    if left:
        err(where, '有未注音的汉字', ''.join(left), '→', s)


levels = build.build()
for lv in levels:
    L = lv['name']
    seen = set()
    for w, r, pos, zh, ex, exzh in lv['vocab']:
        if w in seen:
            err(L, '单词重复', w)
        seen.add(w)
        if not KANA.match(r):
            err(L, '读音含非假名', w, r)
        if pos not in build.POS:
            err(L, '未知词性', w, pos)
        check_ruby('%s 单词 %s' % (L, w), ex)
        if not (zh and exzh):
            err(L, '缺中文', w)
    seen = set()
    for ch, on, kun, zh, ws in lv['kanji']:
        if ch in seen:
            err(L, '汉字重复', ch)
        seen.add(ch)
        if len(ws) < 2:
            err(L, '汉字例词不足 2 个', ch)
        for w, r, z in ws:
            if ch not in w:
                err(L, '例词不含该字', ch, w)
            if not KANA.match(r):
                err(L, '例词读音含非假名', w, r)
    rd = {}
    for _, _, _, _, ws in lv['kanji']:
        for w, r, z in ws:
            if w != r and rd.setdefault(r, w) != w:
                err(L, '汉字例词同音，表记题会有歧义', r, rd[r], w)
    for g in lv['grammar']:
        for k in ('p', 'conn', 'zh', 'ja', 'ex'):
            if not g.get(k):
                err(L, '语法缺字段', g.get('p'), k)
        for a, b in g['ex']:
            check_ruby('%s 语法 %s' % (L, g['p']), a)
        if KANJI.search(g['p']) and not g.get('yomi'):
            err(L, '句型含汉字，需要加 yomi（假名读法）', g['p'])
        if g.get('yomi') and not KANA.match(g['yomi']):
            err(L, 'yomi 含非假名', g['p'], g['yomi'])
        for quoted in re.findall(r'「([^」]*)」', g.get('note', '')):  # 补充说明是中文，只查「」里的日文
            check_ruby('%s 语法补充 %s' % (L, g['p']), quoted)
    for q, a, wrong, expl in lv['quiz']:
        check_ruby('%s 测验' % L, q)
        opts = [a] + list(wrong)
        if len(wrong) != 3 or len(set(build.plain(o) for o in opts)) != 4:
            err(L, '选项应为互不相同的 4 个', q)
        for o in opts:
            check_ruby('%s 测验选项' % L, o)
        if '（　）' not in q:
            err(L, '题干缺少（　）', q)

for name, want in (('たべる', 'taberu'), ('がっこう', 'gakkou'), ('しゃしん', 'shashin'), ('きょういく', 'kyouiku'), ('じゅんび', 'junbi'), ('ニチ', 'nichi')):
    if build.romaji(name) != want:
        err('罗马字转换', name, build.romaji(name), '≠', want)
# 站内链接
OUT = build.OUT
n_links = 0


def check_links(path, text, base):
    global n_links
    for m in re.finditer(r'(?:href|src)="([^"#]+)(?:#[^"]*)?"', text):
        link = urlsplit(m.group(1))
        if link.scheme or link.netloc or not link.path:
            continue
        u = link.path
        target = os.path.join(OUT, u.lstrip('/')) if u.startswith('/') else os.path.normpath(os.path.join(base, u))
        if u.endswith('/') or os.path.isdir(target):
            target = os.path.join(target, 'index.html')
        n_links += 1
        if not os.path.isfile(target):
            err('死链', os.path.relpath(path, OUT), '→', u)


def check_listing(section, expected=None, cards=None):
    base = os.path.join(OUT, section)
    with open(os.path.join(base, 'index.html'), encoding='utf-8') as page:
        markup = page.read()
    path = re.search(r'data-index-url="([^"]+)"', markup).group(1)
    directory = os.path.dirname(os.path.join(base, path))
    with open(os.path.join(base, path), encoding='utf-8') as index:
        metadata = json.load(index)
    if expected is not None and metadata != expected:
        err(section, '级别分类与辞典标签不一致')
    total = len(metadata)
    study_ids = []
    for offset in range(0, total, build.LEX_PAGE_SIZE):
        batch_path = os.path.join(directory, '%d.json' % (offset // build.LEX_PAGE_SIZE))
        with open(batch_path, encoding='utf-8') as batch:
            entries = json.load(batch)
        if len(entries) != min(build.LEX_PAGE_SIZE, total - offset):
            err('批次大小与索引不一致', batch_path)
        batch_markup = ''.join(entries)
        check_links(batch_path, batch_markup, base)
        for anchor in re.findall(r'href="#(g\d+)"', batch_markup):
            if 'id="%s"' % anchor not in markup:
                err(section, '找不到语法锚点', anchor)
        study_ids.extend(html.unescape(value) for value in re.findall(r'data-id="([^"]+)"', batch_markup))
    if cards is not None:
        deck = json.loads(re.search(r'<script[^>]*id="data"[^>]*>(.*?)</script>', markup, re.S).group(1))
        if set(study_ids) != cards or len(study_ids) != len(cards) or {item['id'] for item in deck['items']} != cards:
            err(section, '精选卡片与列表标记不一致')
    return metadata


lexical_rows = check_listing('dict')
grammar_rows = check_listing('grammar')
for lv in levels:
    lid = lv['id']
    for kind, section, source in (('w', 'vocab', lexical_rows), ('k', 'kanji', lexical_rows), ('g', 'grammar', grammar_rows)):
        expected = [row for row in source if kind == row[2] and lid in row[1].split()]
        card_kind = {'w': 'v', 'k': 'k'}.get(kind)
        cards = {'%s:%s:%s' % (lid, card_kind, row[0]) for row in lv[section]} if card_kind else None
        check_listing('%s/%s' % (lid, section), expected, cards)

for base, _, files in os.walk(OUT):
    for f in files:
        if not f.endswith('.html'):
            continue
        p = os.path.join(base, f)
        with open(p, encoding='utf-8') as page:
            check_links(p, page.read(), base)

with open(os.path.join(OUT, 'practice', 'index.html'), encoding='utf-8') as page:
    markup = page.read()
keys = json.loads(re.search(r'<script type="application/json" id="data">(.*?)</script>', markup, re.S).group(1))['practice']
if set(keys) != {'n%d-%d' % (n, year) for n in range(1, 6) for year in (2012, 2018)}:
    err('真题题库应包含 N1–N5 两辑官方问题集')
for paper, answers in keys.items():
    for part in ('v', 'g', 'r'):
        if not re.fullmatch(r'[1-4]+', answers[part]):
            err(paper, part, '缺少有效的答案选项')
    limit = {'n1': [4, 4, 4, 3, 4], 'n2': [4, 4, 4, 3, 4], 'n3': [4, 4, 4, 3, 3]}.get(paper[:2], [4, 4, 3, 3])
    if (len(answers['l']) != len(limit) or
        any(not re.fullmatch(r'[1-%d]+' % n, group) for n, group in zip(limit, answers['l']))):
        err(paper, '听力大题或答案选项异常')
    if paper[:2] in ('n1', 'n2') and len(answers['l'][-1]) != 4:
        err(paper, '听力综合理解应有 4 个答题位置')

mock_root = os.path.join(OUT, 'practice', 'mock')
with open(os.path.join(mock_root, 'index.html'), encoding='utf-8') as page:
    mock = json.loads(re.search(r'<script type="application/json" id="data">(.*?)</script>', page.read(), re.S).group(1))['mock']
if set(mock) != {kind for kind, *_ in build.mock_bank.TYPES}:
    err('模拟题型覆盖不全')

reading_choices = build.ReadingChoices(levels, build.dictionary_data(levels))


def check_reading_options(where, word, correct, wrong):
    choices = {reading_hira(value) for value in wrong}
    valid = reading_choices.known(word) | {reading_hira(correct)}
    if len(choices) != 3 or choices & valid or not all(plausible_reading(value) for value in choices):
        err(where, word, '无效或多解的读音选项', correct, wrong)


for lv in levels:
    path = os.path.join(OUT, lv['id'], 'quiz', 'index.html')
    with open(path, encoding='utf-8') as page:
        quiz = json.loads(re.search(r'<script type="application/json" id="data">(.*?)</script>', page.read(), re.S).group(1))
    primary = {}
    for word, reading, *_ in quiz['v'] + quiz['kw']:
        primary.setdefault(word, reading)
    if len(quiz['reading']) < 10:
        err(lv['id'], '小测验缺少足够的汉字读音题')
    for word, wrong in quiz['reading'].items():
        check_reading_options(lv['id'], word, primary[word], wrong)

for word, reading, expected in (
    ('学校', 'がっこう', ['がくこう', 'がっこ', 'がっきょう']),
    ('鉛筆', 'えんぴつ', ['えんひつ', 'えんびつ', 'えいぴつ']),
    ('大げさ', 'おおげさ', ['だいげさ', 'たいげさ', 'おげさ']),
    ('明日', 'あした', []),
):
    if reading_choices.wrong(word, reading) != expected:
        err('读音干扰项回归', word)

for kind, _, _, applicable in build.mock_bank.TYPES:
    seen = set()
    by_level = mock[kind]['levels']
    if set(by_level) != {'n' + n for n in applicable}:
        err(kind, '模拟题级别和适用题型不一致')
    for lid, data in by_level.items():
        count = 0
        for file in data['files']:
            with open(os.path.join(mock_root, file), encoding='utf-8') as stream:
                items = json.load(stream)
            count += len(items)
            if len(items) != build.mock_bank.SET_SIZE:
                err(lid, kind, '组别题数不正确', file)
            for item in items:
                answers = item['opts']
                if len(answers) != 4 or len(set(answers)) != 4 or not 0 <= item['a'] < 4 or not item['why']:
                    err(lid, kind, '选项或解析无效', item['q'])
                    continue
                key = build.mock_bank.fingerprint(kind, item, answers[item['a']])
                if kind == 'reading':
                    word = re.search(r'【([^】]+)】', item['p']).group(1)
                    check_reading_options(lid, word, answers[item['a']],
                                          [value for i, value in enumerate(answers) if i != item['a']])
                if key in seen:
                    err(lid, kind, '题干重复', item['q'])
                seen.add(key)
        if count != data['count']:
            err(lid, kind, '清单题数不正确')
    if len(seen) != build.mock_bank.QUESTIONS_PER_TYPE:
        err(kind, '独立题目数不正确', len(seen))

for script in ('app.js', 'practice.js', 'mock.js'):
    r = subprocess.run(['node', '--check', os.path.join(build.ROOT, 'assets', script)], capture_output=True, text=True)
    if r.returncode:
        err(script, '语法错误', r.stderr.strip())

for e in errors:
    print('FAIL', e)
print('%d 个站内链接已检查，%d 个问题' % (n_links, len(errors)))
sys.exit(1 if errors else 0)
