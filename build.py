#!/usr/bin/env python3
"""JLPT 学习站构建脚本：content/n*.py + assets/ → dist/（纯静态）。

只用标准库，Python 3.8+ 即可运行：  python3 build.py
内容写在 content/n5.py … n1.py，改完重新构建；dist/ 就是要部署的目录。
"""
import glob
import html
import importlib.util
import json
import os
import re
import shutil

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, 'dist')
esc = html.escape

# 漢字[かんじ] → <ruby>
RUBY = re.compile(r'([一-鿿々]+)\[([ぁ-ゖァ-ー]+)\]')
POS = {  # 词性标签：中文界面 / 日文界面
    '名': ('名词', '名詞'), '动1': ('动词Ⅰ', '動詞Ⅰ'), '动2': ('动词Ⅱ', '動詞Ⅱ'), '动3': ('动词Ⅲ', '動詞Ⅲ'),
    'い形': ('い形容词', 'い形容詞'), 'な形': ('な形容词', 'な形容詞'), '副': ('副词', '副詞'), '连体': ('连体词', '連体詞'),
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


def shell(title_zh, title_ja, desc, depth, body, level=None, data=None):
    root = '../' * depth
    home = root or './'
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
            '<header class="mast"><a class="brand" href="%s"><img class="brand-mark" src="%sassets/lingyu-mark.svg" alt="" width="38" height="38"> feather0<span>%s</span></a>%s</header>\n'
            '<main id="main">\n%s\n</main>\n'
            '<footer><span>feather0 · %s</span><span>%s</span></footer>\n</div>\n%s\n<script src="%sassets/app.js"></script>\n</body>\n</html>\n') % (
        ' data-level="%s"' % level if level else '', esc(title_ja), HEADJS, esc(title_zh), esc(desc), root, root,
        T('跳到正文', '本文へ'), home, root, T('JLPT 学习站', 'JLPT 学習サイト'), tools, body,
        T('JLPT 学习站', 'JLPT 学習サイト'),
        T('个人整理的备考资料，与 JLPT 主办机构无关。学习记录只保存在这台设备的浏览器里。',
          '個人で作成した学習資料で、JLPT の主催団体とは関係ありません。学習記録はこの端末のブラウザにのみ保存されます。'),
        embed(data) if data is not None else '', root)


def write(path, text):
    full = os.path.join(OUT, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, 'w', encoding='utf-8') as f:
        f.write(text)


def counts(lv):
    return '%d %s · %d %s · %d %s' % (len(lv['vocab']), T('词', '語'), len(lv['kanji']), T('字', '字'), len(lv['grammar']), T('语法', '文法'))


# ---------- 首页 ----------
def home(levels):
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
    body = ('<div class="intro"><div class="eyebrow"><span></span>{eyebrow}</div>'
            '<h1><i>JLPT</i>{h1}</h1><p>{intro}</p></div>'
            '<section id="levels" aria-labelledby="catalogue"><div class="rule"><h2 id="catalogue">{cat}</h2><span lang="ja">レベル別インデックス</span></div>'
            '<div class="shelf">{books}</div></section>'
            '<section class="how" aria-labelledby="how-h"><div class="rule"><h2 id="how-h">{how_h}</h2><span lang="ja">学習の進め方</span></div>'
            '<div class="how-grid">{how}</div>'
            '<p class="reset-row"><button type="button" class="link-btn" id="reset">{reset}</button></p></section>').format(
        eyebrow=T('日本语能力考试备考', '日本語能力試験 対策'), h1=T('学习站', '学習サイト'),
        intro=T('按 N5 到 N1 五个级别整理单词、汉字和语法，配合间隔重复卡片和小测验，每天学一点。',
                'N5 から N1 まで、語彙・漢字・文法をレベル別に整理。間隔反復カードとミニクイズで、毎日少しずつ学べます。'),
        cat=T('级别目录', 'レベル一覧'), books=books, how_h=T('怎么用', '使い方'), how=how_html,
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
        wl = ''.join('<li><span class="k-w" lang="ja">%s</span><span class="kana" lang="ja">%s</span><span class="k-wz">%s</span></li>' % (esc(w), esc(r), esc(z)) for w, r, z in ws)
        rows += ('<li class="kcard" data-id="{cid}" data-k="{k}"><div class="k-ch" lang="ja">{ch}</div><div class="k-body">'
                 '<p class="k-m">{zh}</p><dl class="k-yomi"><dt>{on_l}</dt><dd lang="ja">{on}</dd><dt>{kun_l}</dt><dd lang="ja">{kun}</dd></dl>'
                 '<ul class="k-ws">{wl}</ul></div><span class="st" aria-hidden="true"></span></li>').format(
            cid=esc(cid), k=esc((ch + ' ' + on + ' ' + kun + ' ' + zh + ' ' + ' '.join(w + ' ' + r for w, r, _ in ws)).lower()),
            ch=esc(ch), zh=esc(zh), on_l=T('音读', '音読み'), on=esc(on), kun_l=T('训读', '訓読み'), kun=esc(kun), wl=wl)
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


def build():
    levels = load_levels()
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    shutil.copytree(os.path.join(ROOT, 'assets'), os.path.join(OUT, 'assets'))
    home(levels)
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
          .replace('href="assets/', 'href="/assets/').replace('src="assets/', 'src="/assets/').replace('<a class="brand" href="./"', '<a class="brand" href="/"'))
    n = sum(len(files) for _, _, files in os.walk(OUT))
    print('built %d files → dist/ ; ' % n + ' | '.join('%s: %d词 %d字 %d语法 %d题' % (
        lv['name'], len(lv['vocab']), len(lv['kanji']), len(lv['grammar']), len(lv['quiz'])) for lv in levels))
    return levels


if __name__ == '__main__':
    build()
