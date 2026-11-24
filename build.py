#!/usr/bin/env python3
"""JLPT 学习站构建脚本：content/n*.py + assets/ → dist/（纯静态）。

只用标准库，Python 3.8+ 即可运行：  python3 build.py
内容写在 content/n5.py … n1.py，改完重新构建；dist/ 就是要部署的目录。
"""
import glob
import hashlib
import html
import importlib.util
import json
import os
import re
import shutil
import unicodedata
from collections import Counter
from itertools import groupby

import mock_bank
from content.mock_yomi import ReadingChoices

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, 'dist')
esc = html.escape

# 漢字[かんじ] → <ruby>
RUBY = re.compile(r'([一-鿿々]+)\[([ぁ-ゖァ-ー]+)\]')
POS = {  # 词性标签：中文界面 / 日文界面
    '名': ('名词', '名詞'), '动1': ('动词Ⅰ', '動詞Ⅰ'), '动2': ('动词Ⅱ', '動詞Ⅱ'), '动3': ('动词Ⅲ', '動詞Ⅲ'),
    'い形': ('い形容词', 'い形容詞'), 'な形': ('な形容词', 'な形容詞'), '副': ('副词', '副詞'), '连体': ('连体词', '連体詞'),
    '连': ('接续词', '接続詞'), '助': ('助词', '助詞'), '叹': ('感叹词', '感動詞'), '代': ('代词', '代名詞'),
}
CONN_JA = [  # 接续说明里的术语，中文 → 日文
    ('动词', '動詞'), ('形容词', '形容詞'), ('名词', '名詞'), ('辞书形', '辞書形'), ('词干', '語幹'), ('的被动形', 'の受身形'),
    ('的ば形', 'のば形'), ('（去ます）', '（ますを取る）'), ('（去ない）', '（ないを取る）'), ('句子', '文'), ('场所', '場所'), ('工具', '道具'),
    ('移动', '移動'), ('他動詞', '他動詞'), ('他动词', '他動詞'), ('可能形', '可能形'),
]
SECTIONS = [  # (目录, 中文, 日文)
    ('', '概览', '概要'), ('vocab/', '单词', '語彙'), ('kanji/', '汉字', '漢字'), ('grammar/', '语法', '文法'), ('quiz/', '测验', 'クイズ'),
]


def load_levels():
    levels = []
    for f in sorted(glob.glob(os.path.join(ROOT, 'content', 'n[0-9].py')), reverse=True):  # N5 → N1
        spec = importlib.util.spec_from_file_location(os.path.basename(f)[:-3], f)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        lv = dict(m.LEVEL)
        lv.update(name=lv['id'].upper(), vocab=m.VOCAB, kanji=m.KANJI, grammar=m.GRAMMAR, quiz=m.QUIZ)
        levels.append(lv)
    return levels


def ruby(s):
    return RUBY.sub(lambda m: '<ruby>%s<rp>(</rp><rt>%s</rt><rp>)</rp></ruby>' % (m.group(1), m.group(2)), esc(s))


def plain(s):
    return RUBY.sub(lambda m: m.group(1), s)


def T(zh, ja):
    """界面文字的中日两个版本，由 <html data-ui> 决定显示哪一个。"""
    return '<span class="t-zh">%s</span><span class="t-ja" lang="ja">%s</span>' % (zh, ja)


def J(s):
    return '<span lang="ja">%s</span>' % s


def conn_ja(s):
    for a, b in CONN_JA:
        s = s.replace(a, b)
    return s


def embed(data):
    return '<script type="application/json" id="data">%s</script>' % json.dumps(data, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')


HEADJS = ("<script>(function(){var d=document.documentElement,g=function(k){try{return localStorage.getItem(k)}catch(e){return null}},"
          "t=g('jlpt-theme');if(t!=='light'&&t!=='dark')t=window.matchMedia&&matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light';"
          "d.setAttribute('data-theme',t);d.setAttribute('data-ui',g('jlpt-ui')==='ja'?'ja':'zh');d.setAttribute('data-furi',g('jlpt-furi')==='off'?'off':'on')})()</script>")


def shell(title_zh, title_ja, desc, depth, body, level=None, data=None, nav=None, script=None):
    root = '../' * depth
    home = root or './'
    sitenav = '<nav class="site-nav" aria-label="学习工具">%s</nav>' % ''.join(
        '<a href="%s%s"%s>%s</a>' % (root, h, ' aria-current="page"' if nav == k else '', T(zh, ja))
        for h, zh, ja, k in [('dict/', '辞典', '辞書', 'dict'), ('grammar/', '语法词典', '文法辞典', 'grammar'),
                             ('practice/', '题库', '問題集', 'practice')])
    sources = ' <a href="%sdictionary-sources.txt">%s</a>' % (root, T('辞典来源与许可', '辞書の出典・ライセンス')) if nav in ('dict', 'grammar') else ''
    extra_script = '<script src="%sassets/%s"></script>\n' % (root, script) if script else ''
    tools = ('<div class="tools">'
             '<button type="button" id="ui" class="tool-btn"><span class="t-zh" lang="ja">日本語</span><span class="t-ja" lang="zh-Hans">中文</span></button>'
             '<button type="button" id="furi" class="tool-btn" aria-pressed="true" lang="ja">ふりがな</button>'
             '<button type="button" id="theme" class="tool-btn"><span class="on-light">%s</span><span class="on-dark">%s</span></button>'
             '</div>') % (T('深色', 'ダーク'), T('浅色', 'ライト'))
    return ('<!doctype html>\n<html lang="zh-Hans"%s data-title-ja="%s">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">\n'
            '<meta name="color-scheme" content="light dark">\n%s\n<title>%s</title>\n<meta name="description" content="%s">\n'
            '<link rel="icon" href="%sassets/lingyu-mark.svg" type="image/svg+xml">\n<link rel="stylesheet" href="%sassets/site.css">\n</head>\n<body>\n'
            '<a class="skip" href="#main">%s</a>\n<div class="sheet">\n'
            '<header class="mast"><a class="brand" href="%s"><img class="brand-mark" src="%sassets/lingyu-mark.svg" alt="" width="38" height="38"> feather0<span>%s</span></a>%s%s</header>\n'
            '<main id="main">\n%s\n</main>\n'
            '<footer><span>feather0 · %s</span><span>%s</span></footer>\n</div>\n%s\n<script src="%sassets/app.js"></script>\n%s</body>\n</html>\n') % (
        ' data-level="%s"' % level if level else '', esc(title_ja), HEADJS, esc(title_zh), esc(desc), root, root,
        T('跳到正文', '本文へ'), home, root, T('JLPT 学习站', 'JLPT 学習サイト'), sitenav, tools, body,
        T('JLPT 学习站', 'JLPT 学習サイト'),
        T('个人整理的备考资料，与 JLPT 主办机构无关。学习记录只保存在这台设备的浏览器里。',
          '個人で作成した学習資料で、JLPT の主催団体とは関係ありません。学習記録はこの端末のブラウザにのみ保存されます。') + sources,
        embed(data) if data is not None else '', root, extra_script)


def write(path, text):
    full = os.path.join(OUT, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, 'w', encoding='utf-8') as f:
        f.write(text)


def counts(rows):
    return '%d %s · %d %s · %d %s' % (len(rows['w']), T('词', '語'), len(rows['k']), T('字', '字'), len(rows['g']), T('语法', '文法'))


# ---------- 首页 ----------
def home(levels, stats, level_rows):
    books = ''
    for lv in levels:
        books += ('<article class="book" data-level="{id}">'
                  '<a class="course" href="{id}/" aria-label="{name}">'
                  '<div class="plate"><span class="plate-n">{name}</span><span class="plate-w" lang="ja" aria-hidden="true">{plate}</span></div>'
                  '<div class="title"><h3>{name}<small>{sub}</small></h3><span aria-hidden="true">↗</span></div>'
                  '<p>{lead}</p></a>'
                  '<p class="stats">{counts}</p>'
                  '<div class="prog" data-prog="{id}" data-total="{total}"><div class="prog-bar"><i></i></div><span class="prog-t"></span></div>'
                  '<a class="tool" href="{id}/quiz/">{quiz}<span aria-hidden="true"> →</span></a>'
                  '</article>').format(id=lv['id'], name=lv['name'], plate=esc(lv['plate']), sub=T(lv['zh'], lv['ja']),
                                       lead=T(lv['lead_zh'], lv['lead_ja']), counts=counts(level_rows[lv['id']]), total=len(lv['vocab']) + len(lv['kanji']),
                                       quiz=T('做一组测验', 'クイズに挑戦'))
    how = [
        ('01', T('单词与汉字卡片', '語彙・漢字カード'),
         T('先看正面回想读音和意思，再翻面核对，按“不认识／模糊／认识”自评。认识的卡片隔得越来越久才再出现。',
           '表を見て読みと意味を思い出し、裏で確認して「まだ／あいまい／わかる」で自己評価。覚えたカードほど出題の間隔が長くなります。')),
        ('02', T('语法讲解', '文法解説'),
         T('每个句型给出接续方式、中文和日文两种说明，以及带注音的例句。右上角可以随时关掉注音。',
           '文型ごとに接続、中国語と日本語の説明、ふりがな付きの例文を掲載。ふりがなは右上のボタンで消せます。')),
        ('03', T('小测验', 'ミニクイズ'),
         T('词义、读音、汉字写法从词表自动出题，语法题带解说。十题一组，做完可以回看错题。',
           '意味・読み・表記は単語リストから自動で出題、文法問題は解説付き。10問1セットで、間違えた問題を見直せます。')),
    ]
    how_html = ''.join('<div class="how-it"><span class="how-no">%s</span><h3>%s</h3><p>%s</p></div>' % h for h in how)
    ref = ('<section class="ref" aria-labelledby="ref-h"><div class="rule"><h2 id="ref-h">{h}</h2><span lang="ja">辞書・文法辞典</span></div>'
           '<form class="lookup" action="dict/" method="get" role="search"><input class="search big" name="q" type="search" '
           'placeholder="漢字 / かな / romaji / 中文" aria-label="查词 / 検索" autocomplete="off" autocapitalize="off" spellcheck="false">'
           '<button type="submit" class="btn">{go}</button></form><div class="entries two">'
           '<a class="entry" href="dict/"><span class="entry-ja" lang="ja" aria-hidden="true">辞書</span><span class="entry-t">{d}</span>'
           '<span class="entry-n">{nw}</span><span class="entry-d">{dd}</span></a>'
           '<a class="entry" href="grammar/"><span class="entry-ja" lang="ja" aria-hidden="true">文法</span><span class="entry-t">{g}</span>'
           '<span class="entry-n">{ng}</span><span class="entry-d">{gd}</span></a></div></section>').format(
        h=T('工具书', '辞書'), go=T('查词', '検索'), d=T('辞典', '辞書'), nw=stats[0] + stats[1], g=T('语法词典', '文法辞典'), ng=stats[2],
        dd=T('全站单词和汉字按五十音排列，可用汉字、假名、罗马字或中文查。', '全レベルの語彙と漢字を五十音順に。漢字・かな・ローマ字・中国語で検索。'),
        gd=T('全部句型按五十音排列，点开看接续和例句。', '全レベルの文型を五十音順に。開くと接続と例文が見られます。'))
    body = ('<div class="intro"><div class="eyebrow"><span></span>{eyebrow}</div>'
            '<h1><i>JLPT</i>{h1}</h1><p>{intro}</p></div>'
            '<section id="levels" aria-labelledby="catalogue"><div class="rule"><h2 id="catalogue">{cat}</h2><span lang="ja">レベル別インデックス</span></div>'
            '<div class="shelf">{books}</div></section>'
            '{ref}'
            '<section class="how" aria-labelledby="how-h"><div class="rule"><h2 id="how-h">{how_h}</h2><span lang="ja">学習の進め方</span></div>'
            '<div class="how-grid">{how}</div>'
            '<p class="reset-row"><button type="button" class="link-btn" id="reset">{reset}</button></p></section>').format(
        eyebrow=T('日本语能力考试备考', '日本語能力試験 対策'), h1=T('学习站', '学習サイト'),
        intro=T('按 N5 到 N1 五个级别整理单词、汉字和语法，配合间隔重复卡片和小测验，每天学一点。',
                'N5 から N1 まで、語彙・漢字・文法をレベル別に整理。間隔反復カードとミニクイズで、毎日少しずつ学べます。'),
        cat=T('级别目录', 'レベル一覧'), books=books, how_h=T('怎么用', '使い方'), how=how_html, ref=ref,
        reset=T('清除这台设备上的学习记录', 'この端末の学習記録を消去'))
    write('index.html', shell('JLPT 学习站 · N5–N1 单词、汉字、语法与测验', 'JLPT 学習サイト · N5–N1 語彙・漢字・文法・クイズ',
                              'JLPT N5 到 N1 的单词卡片、汉字、语法讲解和小测验，中日双语界面，学习进度保存在浏览器本地。', 0, body))


# ---------- 级别页公用 ----------
def lv_head(lv, levels, sec, depth):
    """级别标题 + 级别切换 + 栏目标签。sec 是 SECTIONS 里的目录名。"""
    root = '../' * depth
    here = '../' * (depth - 1)  # 回到本级别目录
    switch = ''.join('<a href="%s%s/%s"%s>%s</a>' % (root, o['id'], sec, ' aria-current="true"' if o is lv else '', o['name']) for o in levels)
    tabs = ''.join('<a href="%s%s"%s>%s</a>' % (here or './', s, ' aria-current="page"' if s == sec else '', T(zh, ja)) for s, zh, ja in SECTIONS)
    return ('<header class="lv-head{cls}"><div class="lv-title"><p class="eyebrow"><span></span>JLPT · {sub}</p><h1>{name}</h1></div>'
            '<nav class="lv-switch" aria-label="{sw}">{switch}</nav></header>'
            '<nav class="tabs" aria-label="{tb}">{tabs}</nav>').format(
        cls=' sub' if sec else '', sub=T(lv['zh'], lv['ja']), name=lv['name'], sw='级别', switch=switch, tb='栏目', tabs=tabs)


def seg(kind):
    return ('<div class="bar"><div class="seg" role="group"><button type="button" data-mode="list" aria-pressed="true">%s</button>'
            '<button type="button" data-mode="cards" aria-pressed="false">%s</button></div></div>'
            '<section class="deck" id="deck" data-kind="%s" hidden></section>') % (
        T('完整列表', '全項目'), T('精选卡片', '厳選カード'), kind)


def page(lv, levels, sec, title_zh, title_ja, desc, body, data=None):
    depth = 1 if sec == '' else 2
    name = lv['name']
    write('%s/%sindex.html' % (lv['id'], sec),
          shell('%s %s · JLPT 学习站' % (name, title_zh), '%s %s · JLPT 学習サイト' % (name, title_ja), desc, depth,
                lv_head(lv, levels, sec, depth) + body, level=lv['id'], data=data))


def hub(lv, levels, rows):
    ents = [
        ('vocab/', '単語', T('单词', '語彙'), len(rows['w']), T('查找本级单词，或用精选卡片练习。', 'このレベルの語彙を検索。厳選カードでも練習できます。')),
        ('kanji/', '漢字', T('汉字', '漢字'), len(rows['k']), T('查找本级汉字的音训和例词。', 'このレベルの漢字の読みと例語を検索。')),
        ('grammar/', '文法', T('语法', '文法'), len(rows['g']), T('查找本级句型的接续、说明和例句。', 'このレベルの文型の接続・解説・例文を検索。')),
        ('quiz/', '問題', T('测验', 'クイズ'), len(lv['quiz']), T('词义、读音、汉字、语法，十题一组。', '意味・読み・表記・文法を10問1セットで。')),
    ]
    cards = ''.join('<a class="entry" href="%s"><span class="entry-ja" lang="ja" aria-hidden="true">%s</span><span class="entry-t">%s</span>'
                    '<span class="entry-n">%d</span><span class="entry-d">%s</span></a>' % e for e in ents)
    body = ('<p class="lead">{lead}</p>'
            '<div class="today" data-today="{id}" data-v="{v}" data-k="{k}"><div><h2>{today}</h2><p class="today-t">{nojs}</p></div>'
            '<div class="today-go"><a class="btn" href="vocab/#cards">{gov}</a><a class="btn ghost" href="kanji/#cards">{gok}</a></div></div>'
            '<div class="entries">{cards}</div>').format(
        lead=T(lv['lead_zh'], lv['lead_ja']), id=lv['id'], v=len(lv['vocab']), k=len(lv['kanji']), today=T('今天的卡片复习', '今日のカード復習'),
        nojs=T('开启 JavaScript 后可以记录学习进度。', 'JavaScript を有効にすると学習の進み具合を記録できます。'),
        gov=T('单词卡片', '語彙カード'), gok=T('汉字卡片', '漢字カード'), cards=cards)
    page(lv, levels, '', '概览', '概要', lv['lead_zh'], body)


def vocab(lv, levels, rows):
    items = []
    for w, r, pos, zh, ex, exzh in lv['vocab']:
        cid = '%s:v:%s' % (lv['id'], w)
        pz, pj = POS[pos]
        items.append(dict(id=cid, w=w, r=r, pos=[pz, pj], m=zh, x=ruby(ex), xz=exzh))
    listing = lex_listing(lv['id'] + '/vocab', rows, '漢字 / かな / romaji / 中文', show_level_filter=False)
    body = seg('v') + '<div id="list">' + listing + '</div>'
    page(lv, levels, 'vocab/', '单词', '語彙', '%s 单词表与间隔重复卡片，附读音、词性、中文释义和例句。' % lv['name'], body,
         dict(kind='v', level=lv['id'], items=items))


def kanji(lv, levels, rows):
    items = []
    for ch, on, kun, zh, ws in lv['kanji']:
        cid = '%s:k:%s' % (lv['id'], ch)
        items.append(dict(id=cid, w=ch, on=on, kun=kun, m=zh, ws=[list(x) for x in ws]))
    listing = lex_listing(lv['id'] + '/kanji', rows, '漢字 / かな / romaji / 中文', show_level_filter=False)
    body = seg('k') + '<div id="list">' + listing + '</div>'
    page(lv, levels, 'kanji/', '汉字', '漢字', '%s 汉字：音读、训读、常用词和记忆卡片。' % lv['name'], body,
         dict(kind='k', level=lv['id'], items=items))


def grammar(lv, levels, rows):
    arts = ''
    for i, g in enumerate(lv['grammar'], 1):
        exs = ''.join('<li><span lang="ja">%s</span><span class="ex-zh">%s</span></li>' % (ruby(a), esc(b)) for a, b in g['ex'])
        note = '<p class="note"><b>%s</b>%s</p>' % (T('补充', '補足'), ruby(g['note'])) if g.get('note') else ''
        arts += ('<article class="gp" id="g{i}"><header><span class="gp-no">{no}</span><h2 lang="ja">{p}</h2></header>'
                 '<p class="gp-conn"><b>{cl}</b>{conn}</p><p class="gp-mean">{mean}</p><ul class="gp-ex">{exs}</ul>{note}</article>').format(
            i=i, no='%02d' % i, p=esc(g['p']), cl=T('接续', '接続'), conn=T(esc(g['conn']), esc(conn_ja(g['conn']))),
            mean=T(esc(g['zh']), esc(g['ja'])), exs=exs, note=note)
    listing = lex_listing(lv['id'] + '/grammar', rows, '文型 / かな / romaji / 中文', show_level_filter=False)
    body = '<div class="gp-linked">%s</div>%s' % (arts, listing)
    page(lv, levels, 'grammar/', '语法', '文法', '%s 语法：句型的接续、中日文说明和带注音的例句。' % lv['name'], body)


def quiz(lv, levels, reading_choices):
    kw, seen = [], set()
    for _, _, _, _, ws in lv['kanji']:
        for w, r, z in ws:
            if w not in seen:
                seen.add(w)
                kw.append([w, r, z])
    data = dict(level=lv['id'],
                v=[[w, r, zh, ruby(ex), exzh] for w, r, _, zh, ex, exzh in lv['vocab']],
                kw=kw,
                g=[[ruby(q), [ruby(a)] + [ruby(x) for x in wrong], expl] for q, a, wrong, expl in lv['quiz']])
    data['reading'] = {}
    for w, r, *_ in data['v'] + kw:
        if w in data['reading']:
            continue
        wrong = reading_choices.wrong(w, r)
        if len(wrong) == 3:
            data['reading'][w] = wrong
    body = ('<section class="quiz" id="quiz"><p class="nojs">%s</p></section>'
            '<p class="quiz today-go"><a class="btn ghost" href="../../practice/?level=%s">%s<span aria-hidden="true"> →</span></a>'
            '<a class="btn ghost" href="../../practice/mock/?level=%s">%s<span aria-hidden="true"> →</span></a></p>') % (
        T('测验需要开启 JavaScript。', 'クイズには JavaScript が必要です。'), lv['id'], T('真题演练', '公式問題集で演習'),
        lv['id'], T('模拟题库', '模擬問題集'))
    page(lv, levels, 'quiz/', '测验', 'クイズ', '%s 小测验：词义、读音、汉字写法和语法，十题一组，带解说。' % lv['name'], body, data)


def practice():
    with open(os.path.join(ROOT, 'content', 'practice-keys.json'), encoding='utf-8') as source:
        keys = json.load(source)
    body = ('<section class="quiz practice"><header class="lx-head">'
            '<div class="eyebrow"><span></span>%s</div><h1>%s</h1><p class="lead">%s</p></header>'
            '<p class="mock-links"><a class="btn ghost" href="mock/">%s<span aria-hidden="true"> →</span></a></p>'
            '<div id="practice"><p class="nojs">%s</p></div>'
            '<p class="practice-source"><a href="https://www.jlpt.jp/samples/sampleindex.html" target="_blank" rel="noopener">%s</a></p>'
            '</section>') % (
        T('题库', '問題集'), T('真题演练', '公式問題集で演習'),
        T('选用 JLPT 官方 2012 年、2018 年问题集。打开官方题册，在本站计时作答。',
          '2012年版と2018年版のJLPT公式問題集を使います。公式の問題冊子を開き、このサイトで時間を計って解答します。'),
        T('模拟题库', '模擬問題集'),
        T('开启 JavaScript 后可以使用计时答题卡。', '計時と解答にはJavaScriptが必要です。'),
        T('来源 · JLPT 官方网站', '出典 · 日本語能力試験公式ウェブサイト'))
    write('practice/index.html', shell('真题演练 · JLPT 学习站', '公式問題集で演習 · JLPT 学習サイト',
                                     'JLPT N5–N1 官方问题集演练，分科计时、答题和交卷核分。', 1, body,
                                     data={'practice': keys}, nav='practice', script='practice.js'))


def mock_practice(levels, imported, reading_choices):
    types = mock_bank.build_sets(levels, imported, write, reading_choices)
    total = sum(entry['count'] for item in types.values() for entry in item['levels'].values())
    title = T('模拟题库', '模擬問題集')
    body = ('<section class="quiz practice"><header class="lx-head"><h1>%s</h1><p class="lead">%s</p></header>'
            '<p class="mock-links"><a class="btn ghost" href="../">%s<span aria-hidden="true"> →</span></a></p>'
            '<div id="mock"><noscript><p class="nojs">%s</p></noscript></div>'
            '<p class="practice-source"><a href="https://www.jlpt.jp/e/guideline/testsections.html">%s</a> · '
            '<a href="../../dictionary-sources.txt">%s</a></p></section>') % (
        title,
        T('N5–N1 共 %s 道非听力练习，按级别和题型选题。' % f'{total:,}', 'N5–N1の聴解を除く%s問。レベルと問題の種類を選んで練習できます。' % f'{total:,}'),
        T('真题演练', '公式問題集で演習'), T('开启 JavaScript 后可以抽题。', '問題を解くにはJavaScriptが必要です。'),
        T('JLPT 题型参考', 'JLPTの問題構成'), T('词汇素材来源与许可', '語彙素材の出典・ライセンス'))
    write('practice/mock/index.html', shell('模拟题库 · JLPT 学习站', '模擬問題集 · JLPT 学習サイト',
              'JLPT N5–N1 模拟题库，涵盖文字词汇、语法和阅读。', 2, body,
              data={'mock': types}, nav='practice', script='mock.js'))


# ---------- 辞典 / 语法词典（跨级别） ----------
ROWS = [  # (id, 行名, 起, 止)：按读音首字的五十音行分组
    ('a', 'あ', 'ぁ', 'お'), ('ka', 'か', 'か', 'ご'), ('sa', 'さ', 'さ', 'ぞ'), ('ta', 'た', 'た', 'ど'), ('na', 'な', 'な', 'の'),
    ('ha', 'は', 'は', 'ぽ'), ('ma', 'ま', 'ま', 'も'), ('ya', 'や', 'ゃ', 'よ'), ('ra', 'ら', 'ら', 'ろ'), ('wa', 'わ', 'ゎ', 'ん'),
]
ROW_ORDER = {rid: index for index, (rid, _, _, _) in enumerate(ROWS)}
KANA_ONLY = re.compile(r'[^ぁ-ゖァ-ー]')
LEX_PAGE_SIZE = 40


def hira(s):
    """片假名 → 平假名。"""
    return ''.join(chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' else c for c in s)


def kana_row(reading):
    for c in hira(reading):
        for rid, _, a, b in ROWS:
            if a <= c <= b:
                return rid
    return 'wa'


def _roma_table():
    t = {}
    for cons, kana in [('', 'あいうえお'), ('k', 'かきくけこ'), ('s', 'さしすせそ'), ('t', 'たちつてと'), ('n', 'なにぬねの'),
                       ('h', 'はひふへほ'), ('m', 'まみむめも'), ('r', 'らりるれろ'), ('g', 'がぎぐげご'), ('z', 'ざじずぜぞ'),
                       ('d', 'だぢづでど'), ('b', 'ばびぶべぼ'), ('p', 'ぱぴぷぺぽ')]:
        for v, k in zip('aiueo', kana):
            t[k] = cons + v
    t.update({'し': 'shi', 'ち': 'chi', 'つ': 'tsu', 'ふ': 'fu', 'じ': 'ji', 'ぢ': 'ji', 'づ': 'zu',
              'や': 'ya', 'ゆ': 'yu', 'よ': 'yo', 'わ': 'wa', 'を': 'o', 'ん': 'n'})
    return t


ROMA = _roma_table()


def romaji(s):
    """假名 → 平文式罗马字（只用来做搜索键：たべる → taberu，がっこう → gakkou）。"""
    s, out, double, i = hira(s), [], False, 0
    while i < len(s):
        c = s[i]
        nxt = s[i + 1] if i + 1 < len(s) else ''
        i += 1
        if c == 'っ':
            double = True
            continue
        r = ROMA.get(c)
        if r is None:
            continue
        if nxt and nxt in 'ゃゅょ' and r.endswith('i'):
            y = {'ゃ': 'a', 'ゅ': 'u', 'ょ': 'o'}[nxt]
            stem = r[:-1]
            r = stem + y if stem in ('sh', 'ch', 'j') else stem + 'y' + y
            i += 1
        if double:
            r, double = r[0] + r, False
        out.append(r)
    return ''.join(out)


def skey(*parts):
    """搜索键：小写、片假名转平假名，各部分用空格隔开。"""
    return esc(hira(' '.join(p for p in parts if p).lower()))


def search_key(*parts):
    return hira(unicodedata.normalize('NFKC', ' '.join(p for p in parts if p)).lower())


def badges(ids, root, sec):
    return ''.join('<a class="lvb" data-level="%s" href="%s%s/%s">%s</a>' % (i, root, i, sec, i.upper()) for i in ids)


def dictionary_data(levels):
    data = {}
    for lv in levels:
        path = os.path.join(ROOT, 'content', 'dictionary', lv['id'] + '.json')
        with open(path, encoding='utf-8') as stream:
            data[lv['id']] = json.load(stream)
    return data


def word_key(w, r):
    return unicodedata.normalize('NFKC', w), hira(unicodedata.normalize('NFKC', r))


def imported_pos(tags):
    for tag, label in [('adj-i', 'い形'), ('adj-ix', 'い形'), ('adj-na', 'な形'), ('pn', '代'), ('adv', '副'),
                       ('adj-pn', '连体'), ('conj', '连'), ('prt', '助'), ('int', '叹'), ('n', '名')]:
        if tag in tags:
            return label
    for tag in tags:
        if tag.startswith('v5') or tag == 'v4':
            return '动1'
        if tag.startswith('v1'):
            return '动2'
        if tag.startswith(('vk', 'vs')):
            return '动3'
    return None


def meaning_markup(value, lang):
    return '<span lang="en">%s</span>' % esc(value) if lang == 'en' else esc(value)


def lexicon(levels, imported):
    """站内条目优先；同一写法和读音合并，按读音排序。"""
    words = {}
    for lv in levels:
        for w, r, pos, zh, ex, exzh in lv['vocab']:
            e = words.setdefault(word_key(w, r), dict(w=w, r=r, m=zh, lv=[], pos=None, x=None, xz=None, src=[]))
            if e['pos'] is None:
                e.update(r=r, m=zh, pos=pos, x=ex, xz=exzh)
            if lv['id'] not in e['lv']:
                e['lv'].append(lv['id'])
        for ch, _, _, _, ws in lv['kanji']:
            for w, r, z in ws:
                e = words.setdefault(word_key(w, r), dict(w=w, r=r, m=z, lv=[], pos=None, x=None, xz=None, src=[]))
                if lv['id'] not in e['lv']:
                    e['lv'].append(lv['id'])
                if (ch, lv['id']) not in e['src']:
                    e['src'].append((ch, lv['id']))
    for lid, data in imported.items():
        for row in data['vocab']:
            key = word_key(row['w'], row['r'])
            e = words.get(key)
            if e is None:
                e = dict(row, lv=[], pos=imported_pos(row['pos']), src=[], sec='vocab/')
                words[key] = e
            if lid not in e['lv']:
                e['lv'].append(lid)
    for e in words.values():
        e['lv'].sort(reverse=True)
    return sorted(words.values(), key=lambda e: (hira(e['r']), e['w']))


def lex_index(rows):
    kana = [(rid, name) for rid, name, _, _ in ROWS if any(row[3] == rid for row in rows)]
    az = sorted({row[4][:1] or 'other' for row in rows if row[2] != 'k'})
    roman = [(letter, letter.upper() if letter != 'other' else T('其他', 'その他')) for letter in az]
    if any(row[2] == 'k' for row in rows):
        kana.append(('kanji', '漢字'))
        roman.append(('kanji', '漢字'))
    navs = ''
    for mode, label, groups in [('kana', '五十音', kana), ('romaji', 'A–Z', roman)]:
        items = [('', T('全部', 'すべて'))] + groups
        buttons = ''.join('<button type="button" data-group="%s" aria-pressed="%s">%s</button>' % (
            value, 'false' if value else 'true', text) for value, text in items)
        navs += '<nav class="jump" data-index="%s" aria-label="%s"%s>%s</nav>' % (
            mode, label, ' hidden' if mode == 'romaji' else '', buttons)
    return ('<div class="lx-index"><div class="seg" role="group" aria-label="排序 / 並び順">'
            '<button type="button" data-order="kana" aria-pressed="true">五十音</button>'
            '<button type="button" data-order="romaji" aria-pressed="false">%s</button></div>%s</div>') % (
                T('罗马字 A–Z', 'ローマ字 A–Z'), navs)


def lex_tools(placeholder, rows, types, show_level_filter):
    lv = ''
    if show_level_filter:
        chips = '<button type="button" class="chip" data-v="" aria-pressed="true">%s</button>' % T('全部级别', '全レベル')
        chips += ''.join('<button type="button" class="chip" data-v="n%d" aria-pressed="false">N%d</button>' % (n, n) for n in (5, 4, 3, 2, 1))
        lv = '<div class="chips" data-f="lv">%s</div>' % chips
    ty = ''
    if types:
        ty = '<div class="chips" data-f="ty">%s</div>' % ''.join(
            '<button type="button" class="chip" data-v="%s" aria-pressed="%s">%s</button>' % (v, 'true' if not v else 'false', T(zh, ja)) for v, zh, ja in types)
    filters = '<div class="lx-filters">%s%s</div>' % (lv, ty) if lv or ty else ''
    order = lex_index(rows) if any(row[2] != 'k' for row in rows) else ''
    return ('<div class="lx-tools"><input class="search big" id="q" name="q" type="search" placeholder="%s" aria-label="搜索 / 検索" autocomplete="off" autocapitalize="off" spellcheck="false">'
            '%s%s<p class="lx-count" id="lx-count" aria-live="polite"></p></div>') % (
                placeholder, filters, order)


def lex_listing(path, rows, placeholder, types=None, show_level_filter=True):
    """Keep searchable metadata separate from the HTML for each batch of entries."""
    summary = json.dumps([row[:-1] for row in rows], ensure_ascii=False, separators=(',', ':'))
    digest = hashlib.sha256(summary.encode('utf-8'))
    batches = []
    for offset in range(0, len(rows), LEX_PAGE_SIZE):
        batch = json.dumps([row[-1] for row in rows[offset:offset + LEX_PAGE_SIZE]], ensure_ascii=False, separators=(',', ':'))
        digest.update(batch.encode('utf-8'))
        batches.append(batch)
    data_path = 'data-' + digest.hexdigest()[:12] + '/'
    write(path + '/' + data_path + 'index.json', summary)
    for number, batch in enumerate(batches):
        write(path + '/' + data_path + '%d.json' % number, batch)

    labels = {rid: name + '行' for rid, name, _, _ in ROWS}
    labels['kanji'] = '漢字'
    initial = ''
    for (kind, group), members in groupby(rows[:LEX_PAGE_SIZE], key=lambda row: (row[2], row[3])):
        entries = ''.join(row[-1] for row in members)
        if kind != 'g':
            entries = '<ol class="%s">%s</ol>' % ('vlist' if kind == 'w' else 'kgrid', entries)
        initial += '<section class="lx-group"><h2 lang="ja">%s</h2>%s</section>' % (labels[group], entries)
    return ('<div class="lx" data-lex data-index-url="{index}" data-page-size="{size}">{tools}'
            '<div class="lx-results" tabindex="-1">{initial}</div>'
            '<p class="empty" id="empty" hidden>{empty}</p><div class="lx-error" hidden><p>{error}</p>'
            '<button type="button" class="btn ghost" data-retry>{retry}</button></div>'
            '<nav class="lx-pages" aria-label="分页 / ページ" hidden><button type="button" class="btn ghost" data-step="-1">{prev}</button>'
            '<span></span><button type="button" class="btn ghost" data-step="1">{next}</button></nav>'
            '<noscript><p class="nojs">{nojs}</p></noscript></div>').format(
        index=data_path + 'index.json', size=LEX_PAGE_SIZE,
        tools=lex_tools(placeholder, rows, types, show_level_filter), initial=initial,
        empty=T('没有符合条件的条目。', '該当する項目がありません。'),
        error=T('辞典加载失败。', '辞書を読み込めませんでした。'), retry=T('重新加载', '再読み込み'),
        prev=T('上一页', '前のページ'), next=T('下一页', '次のページ'),
        nojs=T('启用 JavaScript 后可搜索和翻页。', '検索やページ切り替えには JavaScript が必要です。'))


def lex_page(path, rows, title, desc, lead, placeholder, types=None):
    head = '<header class="lx-head"><div class="eyebrow"><span></span>%s</div><h1>%s</h1><p class="lead">%s</p></header>' % (
        T('工具书', '辞書'), T(*title), lead)
    body = head + lex_listing(path, rows, placeholder, types)
    write(path + '/index.html', shell(title[0] + ' · JLPT 学习站', title[1] + ' · JLPT 学習サイト', desc, 1, body, nav=path))


def kanji_key(ch, on, kun, zh, ws):
    kun_plain = re.sub(r'[（）]', '', kun)
    roman = ' '.join(romaji(reading) for reading in (on + '・' + kun_plain).split('・'))
    return search_key(ch, on, kun_plain, roman, zh, ' '.join(w + ' ' + r for w, r, _ in ws))


def kcard(lv, ch, on, kun, zh, ws, attrs='', extra='', tail='', gloss_lang=None):
    wl = ''.join('<li><span class="k-w" lang="ja">%s</span><span class="kana" lang="ja">%s</span><span class="k-wz">%s</span></li>' % (esc(w), esc(r), esc(z)) for w, r, z in ws)
    return ('<li class="kcard"{attrs}><div class="k-ch" lang="ja">{ch}</div><div class="k-body">'
            '<p class="k-m">{extra}{zh}</p><dl class="k-yomi"><dt>{on_l}</dt><dd lang="ja">{on}</dd><dt>{kun_l}</dt><dd lang="ja">{kun}</dd></dl>'
            '<ul class="k-ws">{wl}</ul></div>{tail}</li>').format(
        attrs=attrs, ch=esc(ch), extra=extra, zh=meaning_markup(zh, gloss_lang), on_l=T('音读', '音読み'), on=esc(on), kun_l=T('训读', '訓読み'), kun=esc(kun), wl=wl, tail=tail)


def card_attrs(study_id):
    return ' data-id="%s"' % esc(study_id) if study_id else ''


CARD_MARK = '<span class="st" aria-hidden="true"></span>'


def word_entry(e, root, study_id=None):
    right = ''
    if e.get('x'):
        en = ' lang="en"' if e.get('lang') else ''
        attribution = ' data-tatoeba-id="%d"' % e['tatoeba_id'] if e.get('tatoeba_id') else ''
        right += '<span lang="ja"%s>%s</span><span class="ex-zh"%s>%s</span>' % (attribution, ruby(e['x']), en, esc(e.get('xz', '')))
    if e['src']:
        right += '<span class="lx-src">%s%s</span>' % (T('汉字 ', '漢字 '), ''.join(
            '<a href="%s%s/kanji/" lang="ja">%s</a>' % (root, lid, esc(ch)) for ch, lid in e['src']))
    pos = '<span class="pos">%s</span>' % T(*POS[e['pos']]) if e['pos'] else ''
    return ('<li class="vrow"{attrs}><div class="v-head"><span class="v-w" lang="ja">{w}</span>'
            '<span class="v-r" lang="ja">{r}</span></div><div class="v-mid">{b}{pos}<span class="v-m">{m}</span></div>'
            '<div class="v-ex">{right}</div>{mark}</li>').format(
        attrs=card_attrs(study_id), w=esc(e['w']), r=esc(e['r']) if e['r'] != e['w'] else '',
        b=badges(e['lv'], root, e.get('sec', 'vocab/' if e['pos'] else 'kanji/')), pos=pos,
        m=meaning_markup(e['m'], e.get('lang')), right=right, mark=CARD_MARK if study_id else '')


def dict_page(levels, imported, level_rows):
    ents = lexicon(levels, imported)
    study_words = {lv['id']: {word_key(w, r): '%s:v:%s' % (lv['id'], w) for w, r, *_ in lv['vocab']}
                   for lv in levels}
    rows = []
    for e in sorted(ents, key=lambda e: ROW_ORDER[kana_row(e['r'])]):
        roman = romaji(e['r'])
        metadata = (search_key(e['w'], e['r'], roman, e['m']), ' '.join(e['lv']), 'w', kana_row(e['r']), roman)
        rows.append(metadata + (word_entry(e, '../'),))
        for lid in e['lv']:
            study_id = study_words[lid].get(word_key(e['w'], e['r']))
            level_rows[lid]['w'].append(metadata + (word_entry(e, '../../', study_id),))
    manual_chars = {ch for lv in levels for ch, *_ in lv['kanji']}
    word_examples = {}
    for e in ents:
        word_examples.setdefault(e['w'], (e['w'], e['r'], e['m']))
    for lv in levels:
        lid = lv['id']
        extra = badges([lid], '../', 'kanji/')
        level_badge = badges([lid], '../../', 'kanji/')
        for ch, on, kun, zh, ws in lv['kanji']:
            metadata = (kanji_key(ch, on, kun, zh, ws), lid, 'k', 'kanji', '')
            rows.append(metadata + (kcard(lv, ch, on, kun, zh, ws, extra=extra),))
            entry = kcard(lv, ch, on, kun, zh, ws, attrs=card_attrs('%s:k:%s' % (lid, ch)), extra=level_badge, tail=CARD_MARK)
            level_rows[lid]['k'].append(metadata + (entry,))
        for row in imported[lid]['kanji']:
            if row['ch'] in manual_chars:
                continue
            ws = [word_examples[w] for w in row['words'][:3] if w in word_examples]
            ch, on, kun, zh = (row[key] for key in ('ch', 'on', 'kun', 'm'))
            metadata = (kanji_key(ch, on, kun, zh, ws), lid, 'k', 'kanji', '')
            rows.append(metadata + (kcard(lv, ch, on, kun, zh, ws, extra=extra, gloss_lang=row['lang']),))
            level_rows[lid]['k'].append(metadata + (kcard(lv, ch, on, kun, zh, ws, extra=level_badge, gloss_lang=row['lang']),))
    n_k = len(rows) - len(ents)
    lead = T('收录 N5–N1 的 %d 个单词和 %d 个汉字。可用汉字、假名、罗马字或中文查。级别仅供参考。' % (len(ents), n_k),
             'N5–N1 の語彙 %d 語と漢字 %d 字を収録。漢字・かな・ローマ字・中国語で検索できます。レベルは目安です。' % (len(ents), n_k))
    lex_page('dict', rows, ('辞典', '辞書'), 'JLPT N5–N1 单词与汉字辞典，可用汉字、假名、罗马字或中文搜索。', lead,
             '漢字 / かな / romaji / 中文', [('', '全部', 'すべて'), ('w', '单词', '語彙'), ('k', '汉字', '漢字')])
    return len(ents), n_k


def gkey(g):
    return hira(KANA_ONLY.sub('', g.get('yomi') or g['p']))


def grammar_pattern(value):
    return re.sub(r'[\s〜~]', '', unicodedata.normalize('NFKC', value))


def gdict_page(levels, imported, level_rows):
    with open(os.path.join(ROOT, 'content', 'grammar-zh.json'), encoding='utf-8') as source:
        translations = json.load(source)
    example_translations = {}
    detail_translations = {}
    for lv in levels:
        lid = lv['id']
        path = os.path.join(ROOT, 'content', 'grammar-examples-zh', lid + '.json')
        with open(path, encoding='utf-8') as source:
            example_translations[lid] = json.load(source)
        path = os.path.join(ROOT, 'content', 'grammar-details-zh', lid + '.json')
        with open(path, encoding='utf-8') as source:
            detail_translations[lid] = json.load(source)
    ents = []
    for lv in levels:
        ents.extend((gkey(g), lv, i, g) for i, g in enumerate(lv['grammar'], 1))
        seen = {grammar_pattern(g['p']) for g in lv['grammar']}
        rows = imported[lv['id']]['grammar']
        frequency = Counter(grammar_pattern(g['p']) for g in rows)
        for g in rows:
            pattern = grammar_pattern(g['p'])
            if pattern not in seen or frequency[pattern] > 1:
                ents.append((gkey(g), lv, None, g))
    ents.sort(key=lambda t: (ROW_ORDER[kana_row(t[0])], t[0], t[1]['id']))
    rows = []
    for key, lv, i, g in ents:
        glosses = {} if i else example_translations[lv['id']].get(g['id'], {})
        details = {} if i else detail_translations[lv['id']].get(g['id'], {})
        examples = []
        for sentence, original in g['ex']:
            if i:
                translation = esc(original)
            else:
                chinese = glosses.get(plain(sentence))
                english = meaning_markup(original, 'en')
                translation = T(esc(chinese), english) if chinese else english
            examples.append('<li><span lang="ja">%s</span><span class="ex-zh">%s</span></li>' %
                            (ruby(sentence), translation))
        note = ''
        if g.get('note'):
            if i:
                note_text = ruby(g['note'])
            else:
                original_note = meaning_markup(g['note'], 'en')
                note_text = T(ruby(details['note']), original_note) if details.get('note') else original_note
            note = '<p class="note"><b>%s</b>%s</p>' % (T('补充', '補足'), note_text)
        zh, ja = g.get('zh', ''), g.get('ja', '')
        if i:
            mean = T(esc(zh), esc(ja))
        else:
            gloss = translations.get(lv['id'], {}).get(g['id'], {})
            if gloss.get('en') == g['en'] and gloss.get('zh'):
                zh = gloss['zh']
                mean = T(esc(zh), meaning_markup(g['en'], 'en'))
            else:
                mean = meaning_markup(g['en'], 'en')
        conn = T(esc(g['conn']), esc(conn_ja(g['conn']))) if i else meaning_markup(g['conn'], 'en')
        if details.get('conn'):
            conn = T(esc(details['conn']), conn)
        if i:
            href = '../%s/grammar/#g%d' % (lv['id'], i)
            link = T('在 %s 语法页查看' % lv['name'], '%s 文法ページで見る' % lv['name'])
        else:
            href = 'https://github.com/evanclan/OpenJLPT/blob/main/data/json/grammar/%s.json' % lv['id']
            link = T('查看 OpenJLPT 来源', 'OpenJLPT の出典を見る')
        body = (
            '<details class="gd" data-level="{lid}"><summary><span class="gd-p" lang="ja">{p}</span>'
            '<span class="lvb">{name}</span><span class="gd-m">{mean}</span></summary><div class="gd-body">'
            '<p class="gp-conn"><b>{cl}</b>{conn}</p><ul class="gp-ex">{exs}</ul>{note}').format(
            lid=lv['id'], p=esc(g['p']), name=lv['name'], mean=mean, cl=T('接续', '接続'), conn=conn, exs=''.join(examples), note=note)
        more = '<p class="gd-more"><a href="%s">%s<span aria-hidden="true"> →</span></a></p></div></details>'
        roman = romaji(key)
        alias = g.get('romaji', '')
        normalized = re.sub(r'[^a-z]', '', unicodedata.normalize('NFKD', alias.lower()))
        metadata = (search_key(g['p'], g.get('yomi', ''), key, roman, alias, normalized, zh, ja, g.get('en', ''), g['conn'], details.get('conn', '')),
                    lv['id'], 'g', kana_row(key), normalized or roman)
        rows.append(metadata + (body + more % (href, link),))
        if i:
            href = '#g%d' % i
            link = T('查看精选讲解', '詳しい解説を見る')
        level_rows[lv['id']]['g'].append(metadata + (body + more % (href, link),))
    lead = T('收录 N5–N1 的 %d 个句型，点开可看接续和例句。级别仅供参考。' % len(ents),
             'N5–N1 の文型 %d 項目を収録。文型を開くと接続と例文が見られます。レベルは目安です。' % len(ents))
    lex_page('grammar', rows, ('语法词典', '文法辞典'), 'JLPT N5–N1 语法词典，附接续、说明和例句，可搜索。', lead, '文型 / かな / romaji / 中文')
    return len(ents)


def build():
    levels = load_levels()
    imported = dictionary_data(levels)
    reading_choices = ReadingChoices(levels, imported)
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    shutil.copytree(os.path.join(ROOT, 'assets'), os.path.join(OUT, 'assets'))
    level_rows = {lv['id']: {'w': [], 'k': [], 'g': []} for lv in levels}
    nw, nk = dict_page(levels, imported, level_rows)
    ng = gdict_page(levels, imported, level_rows)
    shutil.copyfile(os.path.join(ROOT, 'DICTIONARY-SOURCES.txt'), os.path.join(OUT, 'dictionary-sources.txt'))
    home(levels, (nw, nk, ng), level_rows)
    practice()
    mock_practice(levels, imported, reading_choices)
    for lv in levels:
        rows = level_rows[lv['id']]
        hub(lv, levels, rows)
        vocab(lv, levels, rows['w'])
        kanji(lv, levels, rows['k'])
        grammar(lv, levels, rows['g'])
        quiz(lv, levels, reading_choices)
    nf = ('<div class="intro nf"><div class="eyebrow"><span></span>404</div><h1>%s</h1><p>%s</p>'
          '<p><a class="btn" href="/">%s</a></p></div>') % (
        T('页面不存在', 'ページが見つかりません'),
        T('这个地址没有对应的页面，可能是链接写错了，或者页面已经移动。', 'このアドレスに該当するページはありません。リンクが間違っているか、移動した可能性があります。'),
        T('回到首页', 'トップへ戻る'))
    # 404 可能出现在任意深度，资源用站点绝对路径
    write('404.html', shell('页面不存在 · JLPT 学习站', 'ページが見つかりません · JLPT 学習サイト', '页面不存在', 0, nf)
          .replace('href="assets/', 'href="/assets/').replace('src="assets/', 'src="/assets/').replace('<a class="brand" href="./"', '<a class="brand" href="/"')
          .replace('href="dict/"', 'href="/dict/"').replace('href="grammar/"', 'href="/grammar/"')
          .replace('href="practice/"', 'href="/practice/"'))
    n = sum(len(files) for _, _, files in os.walk(OUT))
    print('built %d files → dist/ ; 辞典 %d 词 %d 字 · 语法词典 %d 条 ; ' % (n, nw, nk, ng) + ' | '.join('%s: %d词 %d字 %d语法 %d题' % (
        lv['name'], len(level_rows[lv['id']]['w']), len(level_rows[lv['id']]['k']), len(level_rows[lv['id']]['g']), len(lv['quiz'])) for lv in levels))
    return levels


if __name__ == '__main__':
    build()
