"""Build the original JLPT practice sets from authored material and licensed vocabulary."""

import hashlib
import json
import random
import re
from collections import Counter, defaultdict

from content.mock_grammar import ACTIONS, RULES
from content.mock_reading import EVENTS, SCENES
from content.mock_vocab import AFFIXES, PARAPHRASES


TYPES = (
    ('reading', '汉字读音', '漢字読み', '12345'),
    ('spelling', '汉字写法', '表記', '2345'),
    ('formation', '构词', '語形成', '2'),
    ('context', '语境选词', '文脈規定', '12345'),
    ('paraphrase', '近义表达', '言い換え類義', '12345'),
    ('usage', '词语用法', '用法', '1234'),
    ('grammar', '句子语法', '文の文法（形式）', '12345'),
    ('order', '句子排序', '文の組み立て', '12345'),
    ('cohesion', '篇章语法', '文章の文法', '12345'),
    ('short', '短篇阅读', '短文の内容理解', '12345'),
    ('medium', '中篇阅读', '中文の内容理解', '12345'),
    ('long', '长篇阅读', '長文の内容理解', '13'),
    ('integrated', '综合阅读', '統合理解', '12'),
    ('theme', '主旨理解', '主張理解', '12'),
    ('lookup', '信息检索', '情報検索', '12345'),
)
QUESTIONS_PER_TYPE = 300
SET_SIZE = 10
KANJI = re.compile(r'[一-龯々]')
RUBY = re.compile(r'\[[ぁ-ゖァ-ー]+\]')
WORD_CHARS = r'[一-龯々ァ-ヺー]'


def question(prompt, correct, wrong, why, passage='', source=None):
    return dict(q=prompt, a=correct, d=list(wrong), why=why, p=passage, src=source)


def fingerprint(kind, item, answer):
    # The chunks are part of the prompt for a sentence-order exercise.
    return item['p'], item['q'], answer if kind == 'order' else ''


def rows(block):
    return [line.split('|') for line in block.strip().splitlines() if line]


def vocabulary(levels, imported):
    banks = {}
    for level in levels:
        lid = level['id']
        entries = {}
        for word, reading, pos, gloss, example, _ in level['vocab']:
            tag = {'名': 'n', '副': 'adv', 'い形': 'adj-i', 'な形': 'adj-na'}.get(pos, pos)
            entries[word, reading] = dict(w=word, r=reading, m=gloss, pos=[tag], x=example)
        for row in imported[lid]['vocab']:
            entries.setdefault((row['w'], row['r']), row)
        banks[lid] = list(entries.values())
    return banks


def dictionary_gloss(word):
    return word['m'].split('；')[0].strip()


def example_context(word):
    example = RUBY.sub('', word.get('x') or '')
    token = word['w']
    if not example or len(example) > 90:
        return None
    # Avoid hitting a kanji compound inside a longer word.
    before = '(?<!' + WORD_CHARS + ')' if KANJI.match(token) else ''
    after = '(?!' + WORD_CHARS + ')' if KANJI.search(token[-1:]) else ''
    match = re.search(before + re.escape(token) + after, example)
    if not match or example.count(token) != 1:
        return None
    return example[:match.start()], example[match.end():]


def similar_options(value, candidates, rng):
    candidates = list(dict.fromkeys(c for c in candidates if c and c != value))
    rng.shuffle(candidates)
    candidates.sort(key=lambda c: (abs(len(c) - len(value)), c[0] != value[0]))
    return candidates[:3]


def kanji_questions(bank, all_words, kind, rng, reading_choices):
    yomi = defaultdict(set)
    for w in all_words:
        yomi[w['w']].add(w['r'])
    pool = [w for w in bank if KANJI.search(w['w']) and len(yomi[w['w']]) == 1 and
            re.fullmatch(r'[ぁ-ゖァ-ヺー]+', w['r'])]
    for w in pool:
        word, reading = w['w'], w['r']
        why = '「%s」读作「%s」。%s。' % (word, reading, dictionary_gloss(w).rstrip('。'))
        parts = example_context(w)
        if kind == 'reading':
            passage = '【%s】' % word if not parts else parts[0] + '【%s】' % word + parts[1]
            wrong = reading_choices.wrong(word, reading)
            yield question('【　】のことばはどう読みますか。', reading, wrong, why, passage, w.get('tatoeba_id') if parts else None)
        else:
            wrong = similar_options(word, [p['w'] for p in pool if p['r'] != reading], rng)
            passage = '【%s】' % reading if not parts else parts[0] + '【%s】' % reading + parts[1]
            yield question('【　】のことばを漢字で書くと、どれですか。', word, wrong, why, passage, w.get('tatoeba_id') if parts else None)


def formation_questions():
    for affix, meaning, foil, stems in rows(AFFIXES):
        for stem in stems.split('/'):
            blank = stem.replace('( )', '（　）') if '( )' in stem else stem + '（　）'
            full = blank.replace('（　）', affix)
            yield question('「%s」という意味になるように、（　）に入るものを選びなさい。' % meaning,
                           affix, foil.split('・'), '完整表记是「%s」。这里的「%s」表示「%s」。' % (full, affix, meaning), blank)


def context_questions(bank, rng):
    parts_of_speech = {'n', 'adv', 'adj-i', 'adj-na'}
    for w in bank:
        parts = example_context(w)
        tags = set(w['pos']) & parts_of_speech
        if not parts or not tags or not w.get('m'):
            continue
        left, right = parts
        if len(left + right) < 9 or not re.match(r'[はがをにへともでのな、。だです]', right):
            continue
        word = w['w']
        meaning = dictionary_gloss(w)
        alternatives = [p['w'] for p in bank if set(p['pos']) & tags and p['w'] != word and p['r'] != w['r'] and
                        p['w'] not in left + right and not set(p['w']) & set(word) and
                        dictionary_gloss(p) not in meaning and meaning not in dictionary_gloss(p)]
        wrong = similar_options(word, alternatives, rng)
        if len(wrong) == 3:
            yield question('（　）に入る最も自然なことばを選びなさい。', word, wrong,
                           '这里用「%s（%s）」，意思是「%s」。' % (word, w['r'], meaning),
                           left + '（　）' + right, w.get('tatoeba_id'))


def paraphrase_questions(lid, rng):
    pairs = rows(PARAPHRASES[lid])
    for position, (word, answer) in enumerate(pairs):
        # Stay within the same portion of the list (adverbs, nouns or verbs).
        pool = [a for w, a in pairs[max(0, position - 10):position + 11]
                if w != word and a != answer and a not in answer and answer not in a and
                w not in answer and word not in a]
        wrong = similar_options(answer, pool, rng)
        yield question('「%s」に最も近い意味の表現はどれですか。' % word, answer, wrong,
                       '「%s」可以换成「%s」。' % (word, answer))


def usage_questions(bank):
    foils = (
        ('窓を%sくと、風が入った。', 'この角を%sれば駅です。', 'もう少し%sくなったら知らせてください。'),
        ('水を%sんでから薬を飲んだ。', '毎晩ここで音楽を%sいた。', 'その箱を%sれば中身が見える。'),
        ('赤ちゃんが%sいているので起きた。', '鉛筆で名前を%sいた。', '夜になると少し%sくなった。'),
    )
    for i, w in enumerate(bank):
        if set(w['pos']) != {'n'} or not KANJI.search(w['w']) or not example_context(w):
            continue
        # Use an attested expression and closed verb/adjective environments where a bare noun fails.
        word = w['w']
        sentence = RUBY.sub('', w['x'])
        wrong = [template % word for template in foils[i % len(foils)]]
        yield question('「%s」の使い方として自然な文を選びなさい。' % word, sentence, wrong,
                       '「%s（%s）」是名词，意思是「%s」。' % (word, w['r'], dictionary_gloss(w)),
                       source=w.get('tatoeba_id'))


def grammar_questions(lid, kind):
    for action in ACTIONS[lid]:
        keys = dict(zip(('o', 'd', 'stem', 'te', 'ta', 'nai', 'vol'), action))
        nai = keys['nai']
        keys['nai_bare'] = nai[:-3] + 'せ' if keys['d'].endswith('する') else nai[:-2]
        for prefix, chunks, suffix, blank, distractors, note in RULES[lid]:
            parts = [c.format(**keys) for c in chunks.split(' / ')]
            full = prefix + ''.join(parts) + suffix
            if kind == 'grammar':
                prompt = prefix + ''.join(parts[:blank] + ['（　）'] + parts[blank + 1:]) + suffix
                wrong = distractors.format(**keys).split('・')
                yield question('（　）に入る最もよいものを選びなさい。', parts[blank], wrong, note + ' 完整句子是「' + full + '」。', prompt)
            else:
                orders = [(0, 2, 1, 3), (1, 0, 3, 2), (2, 3, 0, 1)]
                wrong = [' ／ '.join(parts[i] for i in order) for order in orders]
                prompt = prefix + '　＿　＿　＿　＿　' + suffix
                yield question('四つの部分を並べて、自然な文を作りなさい。', ' ／ '.join(parts), wrong,
                               note + ' 完整句子是「' + full + '」。', prompt)


def text_grammar(lid):
    tier = int(lid[1])
    connectors = {
        5: ('でも', 'だから', 'それに', 'つまり'),
        4: ('しかし', 'それで', 'そのうえ', 'つまり'),
        3: ('ところが', 'そのため', 'さらに', '言い換えると'),
        2: ('とはいえ', 'その結果', '加えて', '要するに'),
        1: ('にもかかわらず', 'したがって', 'ひいては', 'すなわち'),
    }[tier]
    scenes = rows(SCENES)
    start = 0 if tier >= 4 else 15
    for title, goal, plan, problem, action, result, review in scenes[start:start + 15]:
        contexts = (
            ('%sため、はじめは%sつもりだった。' % (goal, plan),
             '実際には%sため、その案ではうまくいかなかった。' % problem, '空格前说的是原定计划，空格后说该计划实际行不通，需要转折。'),
            ('前のやり方では、%sという問題があった。' % problem,
             '%sことにした。' % action, '后句是前句问题带来的决定，需要因果衔接。'),
            ('やり方を変えたら、%s。' % result,
             '新しい方法を使った人たちに意見を聞くこともできた。', '后句在已经取得的一个结果之外，再补充另一个结果。'),
            ('%sことにしたが、今のところ結果が分かっているのは最初に試した場合だけだ。' % action,
             '条件が変わっても同じ効果があるかは、まだ分からない。', '前句说只知道首次试行的结果，后句换一种方式说明这个范围限制。'),
        )
        opens = {
            5: 'みんなで話しました。', 4: '係の人に話を聞きました。', 3: '試しに方法を変えた時の報告です。',
            2: '検討から実施までの経過を次のように記録した。', 1: '担当者から聞いた内容のうち、判断の根拠に関わる部分を記す。'
        }
        if tier == 1:
            contexts = contexts[:2] + (
                ('%sところ、%s。担当者が記録を残せば、この仕組みは他の担当者にも伝わる。' % (action, result),
                 '担当が交代した後も、その記録をもとに対応を続けられるだろう。', '后句把记录带来的作用进一步推及未来组织运行。'),
            ) + contexts[3:]
        for i, (left, right, why) in enumerate(contexts):
            passage = '「%s」について\n%s%s（　）、%s' % (title, opens[tier], left, right)
            yield question('文章の流れに合うことばを選びなさい。', connectors[i],
                           [w for w in connectors if w != connectors[i]], why, passage)


def notices(lid, kind):
    tier = int(lid[1])
    weekdays = ('月', '火', '水', '木', '金', '土', '日')
    for i, (event, place, first, second, item) in enumerate(rows(EVENTS)):
        start = 8 + (i + tier) % 4
        moved = start + 2
        day, new = weekdays[i % 7], weekdays[(i + 2) % 7]
        fee = 100 * (1 + (i + tier) % 7)
        if kind == 'short':
            if tier >= 4:
                passage = '%sのお知らせ\n%s曜日に%s時からする予定でした。今度は%s曜日の%s時からです。場所は前と同じ%sです。%sを持って来てください。'
            else:
                passage = '【%s】日程変更\n当初は%s曜日の%s時に始める予定でしたが、準備の都合により%s曜日の%s時開始に変更します。会場は%sのままです。参加する人は%sを各自で用意してください。'
            passage %= (event, day, start, new, moved, place, item)
            entries = (
                ('何曜日にありますか。', new + '曜日', [day + '曜日'] + [d + '曜日' for d in weekdays if d not in (new, day)][:2]),
                ('何時から始まりますか。', '%d時' % moved, ['%d時' % t for t in (start, start + 1, start + 3)]),
                ('どこで行いますか。', place, list(dict.fromkeys(p for _, p, *_ in rows(EVENTS) if p != place))[:3]),
                ('何を用意しますか。', item, list(dict.fromkeys(x for *_, x in rows(EVENTS) if x != item))[:3]),
            )
        else:
            opening = start - 1
            passage = (
                '【%s】会場　%s\n'
                'Ａ　%s曜日　%s時開始　対象：%s　参加費：%s円\n'
                'Ｂ　%s曜日　%s時開始　対象：%s　参加費：%s円\n'
                'どちらも開始の１時間前から受付。%sを持参。\n'
                '申込方法　Ａは電話、Ｂはウェブ。どちらも開催日の２日前まで。'
            ) % (event, place, day, start, first, fee, new, moved, second, fee + 200, item)
            entries = (
                ('%sが参加できるのは何曜日ですか。' % first, day + '曜日', [new + '曜日'] + [d + '曜日' for d in weekdays if d not in (day, new)][:2]),
                ('%sが参加する回は何時から受付をしますか。' % first, '%s時' % opening, ['%s時' % t for t in (start, moved - 1, moved)]),
                ('%sが参加する回の参加費はいくらですか。' % second, '%s円' % (fee + 200), ['%s円' % k for k in (fee, fee + 100, fee + 300)]),
                ('%sが申し込むとき、どうしますか。' % second, '開催日の２日前までにウェブで申し込む',
                 ['開催日の２日前までに電話で申し込む', '当日の受付でウェブに登録する', '開催日の前日に会場で申し込む']),
            )
        for prompt, correct, wrong in entries:
            yield question(prompt, correct, wrong, '根据通知中与题目对应的日期、场次或参加条件，答案是「%s」。' % correct, passage)


def passage_for(lid, kind, facts):
    title, goal, plan, problem, action, result, review = facts
    tier = int(lid[1])
    if kind == 'medium' and tier >= 4:
        perspective = 'きのう、係の人から話を聞きました。' if tier == 4 else '先週、友だちが教えてくれました。'
        return ('「%s」の話\n%s%sため、みんなで話しました。はじめは%s予定でした。でも、%sので、'
                '計画を変えました。それで、%sことにしました。\n'
                'やってみると、%s。前よりよくなりました。これからは、%sを調べます。') % (title, perspective, goal, plan, problem, action, result, review)
    if kind == 'medium':
        style = {3: 'そこで試しに', 2: 'そこで実施する範囲を限定し、', 1: 'そこで、問題が確認された範囲に対象を絞り、'}[tier]
        return ('「%s」の見直しについて\n担当者が目指したのは%sことだった。当初は%s案を検討していたが、'
                '%sという事情が明らかになった。対応を先送りにすれば、同じ問題が続いてしまう。%s%sことにした。'
                '\nこの方針に変えたところ、%s。担当者はこの変化を認めながらも、結果をほかの場合にそのまま当てはめるのは早いと考えている。'
                '今後は%sを確認してから、継続の可否を決めるという。') % (title, goal, plan, problem, style, action, result, review)
    if kind == 'integrated':
        return ('【Ａ　計画段階の連絡】\n「%s」の目的は%sことです。最初の案としては、%s方向で準備を進めています。'
                'ただ、調査では%sという問題も指摘されています。その問題が解消されなければ、当初の案だけでは目的を達成できないでしょう。'
                '評価に使う記録は、変更前の分も残しておきます。\n\n'
                '【Ｂ　実施後の記録】\nＡで挙げられた問題を踏まえ、実際には%sことにしました。記録を比べたところ、%s。'
                'この変化は目的に沿ったものですが、すぐに範囲を広げるつもりはありません。'
                '次は%sを調べ、その結果をＡの担当者とも共有します。%s') % (title, goal, plan, problem, action, result, review,
                'なお、判断に必要なのは、目的が同じかどうかだけでなく、問題が起きる条件も同じかどうかです。' if tier == 1 else
                '次回の会議では、うまくいった点とまだ調べる点を分けて報告します。')
    if kind == 'theme':
        intro = ('何かを変えるとき、目に見える成果が出ると、同じ方法を他でも使いたくなる。だが、解決しようとした事情が異なれば、同じ結果が出る保証はない。'
                 '私は、目の前の改善と、別の条件でも有効だという判断を区別したい。') if tier == 1 else (
                 'よい結果が出た方法を聞くと、私たちはそのまままねしたくなる。しかし、うまくいったという報告だけで、どこでも使えると考えるのは早い。'
                 '大事なのは、なぜその場で役に立ったのかを確かめることだ。')
        return ('%s\n「%s」を例に考えよう。目的は%sことだった。初めに出たのは%s案だった。ところが、%sという事情が分かった。'
                'そこで、実際には%sことにした。その結果、%s。最初の案と比べると、何を変えたかだけでなく、どの障害に対応したかが見えてくる。\n'
                '一方、最初の調査だけでは、実施する曜日や利用する人が変わったときに同じ成果が出るか判断できない。'
                '確認すべきことの一つは、%sという点だ。調査の目的は、変化を見えなくすることでも、当初の案を正当化することでもない。\n'
                'このように結果と条件を一緒に記録して初めて、別の場面でも参考にできる。'
                '有効だった方法について、利点だけでなく適用できる条件と残った課題まで検討することが重要である。') % (
                    intro, title, goal, plan, problem, action, result, review)
    intro = ('担当者への聞き取りで関心を持ったのは、実施後の結果以上に、途中で何を調べ、どの時点で見通しを修正したかということだった。'
             '結論だけを見れば単純な変更に見えるが、記録を順にたどると、当初と同じ目的を保ちながら手段を変えたことが分かる。') if tier == 1 else (
             '私はある取り組みについて、担当者に話を聞いた。終わった後の結果だけを聞くと簡単に見えるが、始めるまでは問題がいくつもあったそうだ。')
    return ('%s\n今回取り上げるのは「%s」だ。担当者は、%sために計画を立てた。最初の会議では、%s案が出た。'
            'しかし、関係する人に実際の状況を聞いたところ、%sという問題があった。聞き取りをしたのは、計画を実施してから問題に気づくより、先に調整したほうがよいと考えたからだ。\n'
            'そこで、目的は変えず、方法だけ見直した。実際には%sことにした。変更の前後で状況を記録したところ、%s。'
            '少なくとも調査した範囲では、変更の直後にも意味のある変化が確認できた。\n'
            '発表では、この結果だけを取り上げる人もいた。しかし、話を聞いた担当者は、予定したことがすべて済んだとは考えていない。'
            '次にすることは、%sを調べることだ。時期や人数が変わっても同様に進むかを確認してから、今後の方針を決める。'
            'これまでの記録を残しておけば、次の結果が初回と違った場合に理由を調べやすくなる。') % (intro, title, goal, plan, problem, action, result, review)


def passage_questions(lid, kind):
    scenes = rows(SCENES)
    if kind == 'medium':
        scenes = scenes[:15] if int(lid[1]) >= 4 else scenes[15:]
    for facts in scenes:
        title, goal, plan, problem, action, result, review = facts
        passage = passage_for(lid, kind, facts)
        items = [
            ('最初に考えていた方法はどれか。', plan, (action, 'すでに得られた結果をそのまま公表する', '新しい調査が終わるまで何も決めない')),
            ('当初の方法を採用しなかった理由は何か。', problem, ('目的を別のものに変更した', 'すでに問題がすべてなくなった', '前の方法について記録を取る必要がなくなった')),
            ('実際に行ったことはどれか。', action, (plan, '当初の案を変えずに準備を続ける', 'これまでの取り組みをすべて元に戻す')),
            ('方法を変えた後、どんな結果が出たか。', result, ('何も変わらなかった', '予定していた変更を取りやめた', '別の目的を立てることになった')),
        ]
        if kind == 'theme':
            items[0] = ('筆者が最も伝えたいことは何か。', '成果に加え、その方法が有効な条件や残った課題を確認することが大切だ',
                        ('うまくいった方法はどこでも同じように用いるべきだ', '結果を測るより当初の計画を守ることが重要だ', '成果が出た方法については経緯を記録する必要がない'))
        if kind == 'integrated':
            items[2] = ('Ａに示された問題を踏まえて、Ｂはどう対応したか。', action,
                        (plan, 'Ａが挙げた問題は存在しないと判断した', 'Ａの記録を使わずに当初の案をそのまま実施した'))
            items[0] = ('ＡとＢを比べると、実施段階で変わったものは何か。', '当初の目的を実現するために選んだ方法',
                        ('解決したい問題のない地域へ移す方針', '変更前の状況を書き残すことの可否', '調査を行わずに結果を報告する方針'))
        if kind == 'medium' and int(lid[1]) <= 2:
            items[0] = ('担当者が、すぐに今後の方針を決めないのはなぜか。', '条件が変わっても今回の方法が役立つか確認したいから',
                        ('最初の案について、何が問題だったか一切分からないから', '現在の結果は目標とは全く関係がないから', '最初から目的を変更するよう決まっていたから'))
        if kind != 'medium':
            items.append(('次に確認することは何か。', review, ('当初の案を取り消した人の名前', '変更前の役割をなくした理由', 'これまでの結果を発表しなかった理由')))
        for prompt, correct, wrong in items:
            yield question(prompt, correct, wrong, '文章中与这道题对应的是「%s」。' % correct, passage)


def build_sets(levels, imported, write, reading_choices):
    banks = vocabulary(levels, imported)
    all_words = [entry for bank in banks.values() for entry in bank]
    manifest = {}
    totals = Counter()

    for kind, zh, ja, applicable in TYPES:
        manifest[kind] = dict(label=[zh, ja], levels={})
        used = set()
        sets_per_level, extra_sets = divmod(QUESTIONS_PER_TYPE // SET_SIZE, len(applicable))
        for i, number in enumerate(applicable):
            lid = 'n' + number
            count = SET_SIZE * (sets_per_level + (i < extra_sets))
            rng = random.Random(kind + '-' + lid)
            bank = banks[lid][:]
            rng.shuffle(bank)
            if kind in ('reading', 'spelling'):
                items = kanji_questions(bank, all_words, kind, rng, reading_choices)
            elif kind == 'formation':
                items = formation_questions()
            elif kind == 'context':
                items = context_questions(bank, rng)
            elif kind == 'paraphrase':
                items = paraphrase_questions(lid, rng)
            elif kind == 'usage':
                items = usage_questions(bank)
            elif kind in ('grammar', 'order'):
                items = grammar_questions(lid, kind)
            elif kind == 'cohesion':
                items = text_grammar(lid)
            elif kind in ('short', 'lookup'):
                items = notices(lid, kind)
            else:
                items = passage_questions(lid, kind)

            # A change to the option order alone does not create a new question.
            unique = {}
            for item in items:
                options = [item['a']] + item['d']
                if len(options) != 4 or len(set(options)) != 4:
                    continue
                key = fingerprint(kind, item, item['a'])
                if key in used or key in unique:
                    continue
                unique[key] = item
                if len(unique) == count:
                    break
            if len(unique) < count:
                raise ValueError('%s/%s: need %d unique questions, have %d' % (lid, kind, count, len(unique)))
            used.update(unique)
            chosen = list(unique.values())
            rng.shuffle(chosen)
            for item in chosen:
                options = [item['a']] + item.pop('d')
                rng.shuffle(options)
                item['a'] = options.index(item['a'])
                item['opts'] = options
            data = json.dumps(chosen, ensure_ascii=False, separators=(',', ':'))
            digest = hashlib.sha256(data.encode('utf-8')).hexdigest()[:12]
            files = []
            for offset in range(0, count, SET_SIZE):
                file = 'data/%s/%s-%s-%d.json' % (lid, kind, digest, offset // SET_SIZE + 1)
                write('practice/mock/' + file, json.dumps(chosen[offset:offset + SET_SIZE], ensure_ascii=False, separators=(',', ':')))
                files.append(file)
            manifest[kind]['levels'][lid] = dict(count=count, files=files)
            totals[kind] += count
        if totals[kind] != QUESTIONS_PER_TYPE:
            raise ValueError('%s has %d questions' % (kind, totals[kind]))
    return manifest
