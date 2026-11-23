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


def shell(title_zh, title_ja, desc, depth, body, level=None, data=None, nav=None):
    root = '../' * depth
    home = root or './'
    sitenav = '<nav class="site-nav" aria-label="工具书">%s</nav>' % ''.join(
        '<a href="%s%s"%s>%s</a>' % (root, h, ' aria-current="page"' if nav == k else '', T(zh, ja))
        for h, zh, ja, k in [('dict/', '辞典', '辞書', 'dict'), ('grammar/', '语法词典', '文法辞典', 'grammar')])
    sources = ' <a href="%sdictionary-sources.txt">%s</a>' % (root, T('辞典来源与许可', '辞書の出典・ライセンス')) if nav else ''
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
            '<footer><span>feather0 · %s</span><span>%s</span></footer>\n</div>\n%s\n<script src="%sassets/app.js"></script>\n</body>\n</html>\n') % (
        ' data-level="%s"' % level if level else '', esc(title_ja), HEADJS, esc(title_zh), esc(desc), root, root,
        T('跳到正文', '本文へ'), home, root, T('JLPT 学习站', 'JLPT 学習サイト'), sitenav, tools, body,
        T('JLPT 学习站', 'JLPT 学習サイト'),
        T('个人整理的备考资料，与 JLPT 主办机构无关。学习记录只保存在这台设备的浏览器里。',
          '個人で作成した学習資料で、JLPT の主催団体とは関係ありません。学習記録はこの端末のブラウザにのみ保存されます。') + sources,
        embed(data) if data is not None else '', root)


def write(path, text):
    full = os.path.join(OUT, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, 'w', encoding='utf-8') as f:
        f.write(text)


def counts(lv):
    return '%d %s · %d %s · %d %s' % (len(lv['vocab']), T('词', '語'), len(lv['kanji']), T('字', '字'), len(lv['grammar']), T('语法', '文法'))


# ---------- 首页 ----------
def home(levels, stats):
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
                                       lead=T(lv['lead_zh'], lv['lead_ja']), counts=counts(lv), total=len(lv['vocab']) + len(lv['kanji']),
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
            '<button type="button" data-mode="cards" aria-pressed="false">%s</button></div>'
            '<input class="search" id="search" type="search" placeholder="%s" aria-label="%s" autocomplete="off"></div>'
            '<section class="deck" id="deck" data-kind="%s" hidden></section>') % (
        T('列表', 'リスト'), T('卡片', 'カード'), '搜索 / 検索', '搜索', kind)


def page(lv, levels, sec, title_zh, title_ja, desc, body, data=None):
    depth = 1 if sec == '' else 2
    name = lv['name']
    write('%s/%sindex.html' % (lv['id'], sec),
          shell('%s %s · JLPT 学习站' % (name, title_zh), '%s %s · JLPT 学習サイト' % (name, title_ja), desc, depth,
                lv_head(lv, levels, sec, depth) + body, level=lv['id'], data=data))


def hub(lv, levels):
    ents = [
        ('vocab/', '単語', T('单词', '語彙'), len(lv['vocab']), T('列表查词，或用卡片按间隔重复记忆。', 'リストで確認、またはカードで間隔反復。')),
        ('kanji/', '漢字', T('汉字', '漢字'), len(lv['kanji']), T('音读、训读和常用词，同样可以用卡片练。', '音読み・訓読みとよく使う語。カードでも練習できます。')),
        ('grammar/', '文法', T('语法', '文法'), len(lv['grammar']), T('接续、说明和带注音的例句。', '接続、説明、ふりがな付きの例文。')),
        ('quiz/', '問題', T('测验', 'クイズ'), len(lv['quiz']), T('词义、读音、汉字、语法，十题一组。', '意味・読み・表記・文法を10問1セットで。')),
    ]
    cards = ''.join('<a class="entry" href="%s"><span class="entry-ja" lang="ja" aria-hidden="true">%s</span><span class="entry-t">%s</span>'
                    '<span class="entry-n">%d</span><span class="entry-d">%s</span></a>' % e for e in ents)
    body = ('<p class="lead">{lead}</p>'
            '<div class="today" data-today="{id}" data-v="{v}" data-k="{k}"><div><h2>{today}</h2><p class="today-t">{nojs}</p></div>'
            '<div class="today-go"><a class="btn" href="vocab/#cards">{gov}</a><a class="btn ghost" href="kanji/#cards">{gok}</a></div></div>'
            '<div class="entries">{cards}</div>').format(
        lead=T(lv['lead_zh'], lv['lead_ja']), id=lv['id'], v=len(lv['vocab']), k=len(lv['kanji']), today=T('今天的学习', '今日の学習'),
        nojs=T('开启 JavaScript 后可以记录学习进度。', 'JavaScript を有効にすると学習の進み具合を記録できます。'),
        gov=T('单词卡片', '語彙カード'), gok=T('汉字卡片', '漢字カード'), cards=cards)
    page(lv, levels, '', '概览', '概要', lv['lead_zh'], body)


def vocab(lv, levels):
    rows, items = '', []
    for w, r, pos, zh, ex, exzh in lv['vocab']:
        cid = '%s:v:%s' % (lv['id'], w)
        pz, pj = POS[pos]
        rows += ('<li class="vrow" data-id="{cid}" data-k="{k}"><div class="v-head"><span class="v-w" lang="ja">{w}</span>'
                 '<span class="v-r" lang="ja">{r}</span></div>'
                 '<div class="v-mid"><span class="pos">{pos}</span><span class="v-m">{zh}</span></div>'
                 '<div class="v-ex"><span lang="ja">{ex}</span><span class="ex-zh">{exzh}</span></div>'
                 '<span class="st" aria-hidden="true"></span></li>').format(
            cid=esc(cid), k=esc((w + ' ' + r + ' ' + zh).lower()), w=esc(w), r=esc(r) if r != w else '', pos=T(pz, pj), zh=esc(zh),
            ex=ruby(ex), exzh=esc(exzh))
        items.append(dict(id=cid, w=w, r=r, pos=[pz, pj], m=zh, x=ruby(ex), xz=exzh))
    body = seg('v') + '<ol class="vlist" id="list">%s</ol><p class="empty" id="empty" hidden>%s</p>' % (rows, T('没有匹配的词。', '該当する語がありません。'))
    page(lv, levels, 'vocab/', '单词', '語彙', '%s 单词表与间隔重复卡片，附读音、词性、中文释义和例句。' % lv['name'], body,
         dict(kind='v', level=lv['id'], items=items))


def kanji(lv, levels):
    rows, items = '', []
    for ch, on, kun, zh, ws in lv['kanji']:
        cid = '%s:k:%s' % (lv['id'], ch)
        rows += kcard(lv, ch, on, kun, zh, ws, attrs=' data-id="%s" data-k="%s"' % (esc(cid), esc(kanji_key(ch, on, kun, zh, ws))), tail='<span class="st" aria-hidden="true"></span>')
        items.append(dict(id=cid, w=ch, on=on, kun=kun, m=zh, ws=[list(x) for x in ws]))
    body = seg('k') + '<ol class="kgrid" id="list">%s</ol><p class="empty" id="empty" hidden>%s</p>' % (rows, T('没有匹配的汉字。', '該当する漢字がありません。'))
    page(lv, levels, 'kanji/', '汉字', '漢字', '%s 汉字：音读、训读、常用词和记忆卡片。' % lv['name'], body,
         dict(kind='k', level=lv['id'], items=items))


def grammar(lv, levels):
    toc, arts = '', ''
    for i, g in enumerate(lv['grammar'], 1):
        toc += '<a href="#g%d" lang="ja">%s</a>' % (i, esc(g['p']))
        exs = ''.join('<li><span lang="ja">%s</span><span class="ex-zh">%s</span></li>' % (ruby(a), esc(b)) for a, b in g['ex'])
        note = '<p class="note"><b>%s</b>%s</p>' % (T('补充', '補足'), ruby(g['note'])) if g.get('note') else ''
        arts += ('<article class="gp" id="g{i}"><header><span class="gp-no">{no}</span><h2 lang="ja">{p}</h2></header>'
                 '<p class="gp-conn"><b>{cl}</b>{conn}</p><p class="gp-mean">{mean}</p><ul class="gp-ex">{exs}</ul>{note}</article>').format(
            i=i, no='%02d' % i, p=esc(g['p']), cl=T('接续', '接続'), conn=T(esc(g['conn']), esc(conn_ja(g['conn']))),
            mean=T(esc(g['zh']), esc(g['ja'])), exs=exs, note=note)
    body = '<nav class="gp-toc" aria-label="句型">%s</nav>%s' % (toc, arts)
    page(lv, levels, 'grammar/', '语法', '文法', '%s 语法：句型的接续、中日文说明和带注音的例句。' % lv['name'], body)


def quiz(lv, levels):
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
    body = '<section class="quiz" id="quiz"><p class="nojs">%s</p></section>' % T('测验需要开启 JavaScript。', 'クイズには JavaScript が必要です。')
    page(lv, levels, 'quiz/', '测验', 'クイズ', '%s 小测验：词义、读音、汉字写法和语法，十题一组，带解说。' % lv['name'], body, data)


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


def lex_tools(placeholder, rows, types=None):
    lv = '<button type="button" class="chip" data-v="" aria-pressed="true">%s</button>' % T('全部级别', '全レベル')
    lv += ''.join('<button type="button" class="chip" data-v="n%d" aria-pressed="false">N%d</button>' % (n, n) for n in (5, 4, 3, 2, 1))
    ty = ''
    if types:
        ty = '<div class="chips" data-f="ty">%s</div>' % ''.join(
            '<button type="button" class="chip" data-v="%s" aria-pressed="%s">%s</button>' % (v, 'true' if not v else 'false', T(zh, ja)) for v, zh, ja in types)
    return ('<div class="lx-tools"><input class="search big" id="q" name="q" type="search" placeholder="%s" aria-label="搜索 / 検索" autocomplete="off" autocapitalize="off" spellcheck="false">'
            '<div class="lx-filters"><div class="chips" data-f="lv">%s</div>%s</div>%s<p class="lx-count" id="lx-count" aria-live="polite"></p></div>') % (
                placeholder, lv, ty, lex_index(rows))


def lex_page(path, rows, title, desc, lead, placeholder, types=None):
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
    body = ('<header class="lx-head"><div class="eyebrow"><span></span>{eb}</div><h1>{title}</h1><p class="lead">{lead}</p></header>'
            '<div class="lx" data-lex data-index-url="{index}" data-page-size="{size}">{tools}'
            '<div class="lx-results" tabindex="-1">{initial}</div>'
            '<p class="empty" id="empty" hidden>{empty}</p><div class="lx-error" hidden><p>{error}</p>'
            '<button type="button" class="btn ghost" data-retry>{retry}</button></div>'
            '<nav class="lx-pages" aria-label="分页 / ページ" hidden><button type="button" class="btn ghost" data-step="-1">{prev}</button>'
            '<span></span><button type="button" class="btn ghost" data-step="1">{next}</button></nav>'
            '<noscript><p class="nojs">{nojs}</p></noscript></div>').format(
        eb=T('工具书', '辞書'), title=T(*title), lead=lead, index=data_path + 'index.json', size=LEX_PAGE_SIZE,
        tools=lex_tools(placeholder, rows, types), initial=initial,
        empty=T('没有符合条件的条目。', '該当する項目がありません。'),
        error=T('辞典加载失败。', '辞書を読み込めませんでした。'), retry=T('重新加载', '再読み込み'),
        prev=T('上一页', '前のページ'), next=T('下一页', '次のページ'),
        nojs=T('启用 JavaScript 后可搜索和翻页。', '検索やページ切り替えには JavaScript が必要です。'))
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


def dict_page(levels, imported):
    ents = lexicon(levels, imported)
    rows = []
    for e in ents:
        right = ''
        if e.get('x'):
            en = ' lang="en"' if e.get('lang') else ''
            attribution = ' data-tatoeba-id="%d"' % e['tatoeba_id'] if e.get('tatoeba_id') else ''
            right += '<span lang="ja"%s>%s</span><span class="ex-zh"%s>%s</span>' % (attribution, ruby(e['x']), en, esc(e.get('xz', '')))
        if e['src']:
            right += '<span class="lx-src">%s%s</span>' % (T('汉字 ', '漢字 '), ''.join(
                '<a href="../%s/kanji/" lang="ja">%s</a>' % (lid, esc(ch)) for ch, lid in e['src']))
        pos = '<span class="pos">%s</span>' % T(*POS[e['pos']]) if e['pos'] else ''
        entry = (
            '<li class="vrow"><div class="v-head"><span class="v-w" lang="ja">{w}</span>'
            '<span class="v-r" lang="ja">{r}</span></div><div class="v-mid">{b}{pos}<span class="v-m">{m}</span></div>'
            '<div class="v-ex">{right}</div></li>').format(
            w=esc(e['w']), r=esc(e['r']) if e['r'] != e['w'] else '',
            b=badges(e['lv'], '../', e.get('sec', 'vocab/' if e['pos'] else 'kanji/')), pos=pos, m=meaning_markup(e['m'], e.get('lang')), right=right)
        roman = romaji(e['r'])
        rows.append((search_key(e['w'], e['r'], roman, e['m']), ' '.join(e['lv']), 'w', kana_row(e['r']), roman, entry))
    rows.sort(key=lambda row: ROW_ORDER[row[3]])
    manual_chars = {ch for lv in levels for ch, *_ in lv['kanji']}
    word_examples = {}
    for e in ents:
        word_examples.setdefault(e['w'], (e['w'], e['r'], e['m']))
    for lv in levels:
        lid = lv['id']
        extra = badges([lid], '../', 'kanji/')
        for ch, on, kun, zh, ws in lv['kanji']:
            rows.append((kanji_key(ch, on, kun, zh, ws), lid, 'k', 'kanji', '', kcard(lv, ch, on, kun, zh, ws, extra=extra)))
        for row in imported[lid]['kanji']:
            if row['ch'] in manual_chars:
                continue
            ws = [word_examples[w] for w in row['words'][:3] if w in word_examples]
            ch, on, kun, zh = (row[key] for key in ('ch', 'on', 'kun', 'm'))
            entry = kcard(lv, ch, on, kun, zh, ws, extra=extra, gloss_lang=row['lang'])
            rows.append((kanji_key(ch, on, kun, zh, ws), lid, 'k', 'kanji', '', entry))
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


def gdict_page(levels, imported):
    with open(os.path.join(ROOT, 'content', 'grammar-zh.json'), encoding='utf-8') as source:
        translations = json.load(source)
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
    ents.sort(key=lambda t: (t[0], t[1]['id']))
    rows = []
    for key, lv, i, g in ents:
        en = ' lang="en"' if i is None else ''
        exs = ''.join('<li><span lang="ja">%s</span><span class="ex-zh"%s>%s</span></li>' % (ruby(a), en, esc(b)) for a, b in g['ex'])
        note = '<p class="note"><b>%s</b>%s</p>' % (T('补充', '補足'), ruby(g['note'])) if g.get('note') else ''
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
        if i:
            href = '../%s/grammar/#g%d' % (lv['id'], i)
            link = T('在 %s 语法页查看' % lv['name'], '%s 文法ページで見る' % lv['name'])
        else:
            href = 'https://github.com/evanclan/OpenJLPT/blob/main/data/json/grammar/%s.json' % lv['id']
            link = T('查看 OpenJLPT 来源', 'OpenJLPT の出典を見る')
        entry = (
            '<details class="gd" data-level="{lid}"><summary><span class="gd-p" lang="ja">{p}</span>'
            '<span class="lvb">{name}</span><span class="gd-m">{mean}</span></summary><div class="gd-body">'
            '<p class="gp-conn"><b>{cl}</b>{conn}</p><ul class="gp-ex">{exs}</ul>{note}'
            '<p class="gd-more"><a href="{href}">{link}<span aria-hidden="true"> →</span></a></p></div></details>').format(
            lid=lv['id'], p=esc(g['p']), name=lv['name'], mean=mean, cl=T('接续', '接続'), conn=conn, exs=exs, note=note, href=href, link=link)
        roman = romaji(key)
        alias = g.get('romaji', '')
        normalized = re.sub(r'[^a-z]', '', unicodedata.normalize('NFKD', alias.lower()))
        rows.append((search_key(g['p'], g.get('yomi', ''), key, roman, alias, normalized, zh, ja, g.get('en', ''), g['conn']),
                     lv['id'], 'g', kana_row(key), normalized or roman, entry))
    rows.sort(key=lambda row: ROW_ORDER[row[3]])
    lead = T('收录 N5–N1 的 %d 个句型，点开可看接续和例句。级别仅供参考。' % len(ents),
             'N5–N1 の文型 %d 項目を収録。文型を開くと接続と例文が見られます。レベルは目安です。' % len(ents))
    lex_page('grammar', rows, ('语法词典', '文法辞典'), 'JLPT N5–N1 语法词典，附接续、说明和例句，可搜索。', lead, '文型 / かな / romaji / 中文')
    return len(ents)


def build():
    levels = load_levels()
    imported = dictionary_data(levels)
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    shutil.copytree(os.path.join(ROOT, 'assets'), os.path.join(OUT, 'assets'))
    nw, nk = dict_page(levels, imported)
    ng = gdict_page(levels, imported)
    shutil.copyfile(os.path.join(ROOT, 'DICTIONARY-SOURCES.txt'), os.path.join(OUT, 'dictionary-sources.txt'))
    home(levels, (nw, nk, ng))
    for lv in levels:
        hub(lv, levels)
        vocab(lv, levels)
        kanji(lv, levels)
        grammar(lv, levels)
        quiz(lv, levels)
    nf = ('<div class="intro nf"><div class="eyebrow"><span></span>404</div><h1>%s</h1><p>%s</p>'
          '<p><a class="btn" href="/">%s</a></p></div>') % (
        T('页面不存在', 'ページが見つかりません'),
        T('这个地址没有对应的页面，可能是链接写错了，或者页面已经移动。', 'このアドレスに該当するページはありません。リンクが間違っているか、移動した可能性があります。'),
        T('回到首页', 'トップへ戻る'))
    # 404 可能出现在任意深度，资源用站点绝对路径
    write('404.html', shell('页面不存在 · JLPT 学习站', 'ページが見つかりません · JLPT 学習サイト', '页面不存在', 0, nf)
          .replace('href="assets/', 'href="/assets/').replace('src="assets/', 'src="/assets/').replace('<a class="brand" href="./"', '<a class="brand" href="/"')
          .replace('href="dict/"', 'href="/dict/"').replace('href="grammar/"', 'href="/grammar/"'))
    n = sum(len(files) for _, _, files in os.walk(OUT))
    print('built %d files → dist/ ; 辞典 %d 词 %d 字 · 语法词典 %d 条 ; ' % (n, nw, nk, ng) + ' | '.join('%s: %d词 %d字 %d语法 %d题' % (
        lv['name'], len(lv['vocab']), len(lv['kanji']), len(lv['grammar']), len(lv['quiz'])) for lv in levels))
    return levels


if __name__ == '__main__':
    build()
