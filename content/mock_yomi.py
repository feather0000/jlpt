"""Reading distractors based on the target spelling and Japanese sound contrasts."""

import re
import unicodedata
from collections import defaultdict


KANJI = re.compile(r'[一-龯々]')
KANA = re.compile(r'[ぁ-ゖー]+')
MORA = re.compile(r'[ぁ-ゖ](?:[ぁぃぅぇぉゃゅょゎ])?|ー')
KANA_TO_HIRA = str.maketrans({chr(c): chr(c - 0x60) for c in range(ord('ァ'), ord('ヶ') + 1)})
HIRA_TO_KANA = str.maketrans({value: chr(key) for key, value in KANA_TO_HIRA.items()})

# Same consonant or vowel, or a common voicing contrast.
VOICE = ('かが', 'きぎ', 'くぐ', 'けげ', 'こご', 'さざ', 'しじ', 'すず', 'せぜ', 'そぞ',
         'ただ', 'ちぢ', 'つづ', 'てで', 'とど', 'はばぱ', 'ひびぴ', 'ふぶぷ', 'へべぺ', 'ほぼぽ')
VOWELS = ('あいうえお', 'かきくけこ', 'がぎぐげご', 'さしすせそ', 'ざじずぜぞ', 'たちつてと',
          'だぢづでど', 'なにぬねの', 'はひふへほ', 'ばびぶべぼ', 'ぱぴぷぺぽ', 'まみむめも', 'やゆよ', 'らりるれろ')
CONSONANTS = ('かさたなはまら', 'きしちにひみり', 'くすつぬふむる', 'けせてねへめれ', 'こそとのほもろ')
O_ROW = 'おこごそぞとどのほぼぽもよろをょ'
E_ROW = 'えけげせぜてでねへべぺめれぇ'
U_ROW = 'うくぐすずつづぬふぶぷむゆるゅ'
SOKUON_NEXT = 'かきくけこさしすせそたちつてとはひふへほぱぴぷぺぽ'
SMALL = 'ぁぃぅぇぉゃゅょゎっー'

# Writings with more than one common reading, including readings that can be
# absent from a level-filtered dictionary.
COMMON_VARIANTS = {
    '私': ('わたし', 'わたくし'), '今日': ('きょう', 'こんにち'), '明日': ('あした', 'あす', 'みょうにち'),
    '昨日': ('きのう', 'さくじつ'), '一日': ('いちにち', 'ついたち'), '十分': ('じゅうぶん', 'じゅっぷん', 'じっぷん'),
    '日本': ('にほん', 'にっぽん'), '市場': ('いちば', 'しじょう'), '人気': ('にんき', 'ひとけ'),
    '行く': ('いく', 'ゆく'), '金色': ('きんいろ', 'こんじき'), '上手': ('じょうず', 'うわて', 'かみて'),
    '下手': ('へた', 'したて', 'しもて'), '家': ('いえ', 'うち'), '敵': ('てき', 'かたき'),
}

# For familiar targets, use common confusions before the general sound rules.
COMMON_DISTRACTORS = {
    '学校': ('がくこう', 'がっこ', 'がっきょう'),
    '先生': ('せんせ', 'せんぜい', 'せんしょう'),
    '教室': ('きょしつ', 'きょうじつ', 'きょうしち'),
    '鉛筆': ('えんひつ', 'えんびつ', 'えいぴつ'),
    '切手': ('きて', 'きつて', 'きりて'),
    '兄弟': ('きょうたい', 'きょだい', 'きょうてい'),
    '姉': ('あに', 'あめ', 'おね'),
    '会社': ('かいじゃ', 'かいしょ', 'がいしゃ'),
    '冷房': ('れいほう', 'れいぼ', 'りょうぼう'),
    '経験': ('けいげん', 'けいきん', 'けけん'),
    '関係': ('かんげい', 'かんけ', 'かんかい'),
    '結果': ('けつか', 'げっか', 'けっこう'),
    '影響': ('えいぎょう', 'えいきょ', 'えんきょう'),
    '準備': ('じゅんぴ', 'じゅんひ', 'じゅうび'),
    '傾向': ('けいごう', 'けいこ', 'きょうこう'),
    '発表': ('はつひょう', 'はっぴょ', 'はっぽう'),
    '大げさ': ('だいげさ', 'たいげさ', 'おげさ'),
    '弱い': ('やわい', 'よあい', 'じゃくい'),
    '実費': ('じつひ', 'じつぴ', 'じっひ'),
    '楽観': ('らくかん', 'らっかい', 'がっかん'),
    '雰囲気': ('ふいんき', 'ふんいぎ', 'ふんえき'),
}


def hira(value):
    return unicodedata.normalize('NFKC', value).translate(KANA_TO_HIRA)


def stems(on, kun):
    for entry in (on + '・' + kun).split('・'):
        base, _, okuri = hira(entry).replace('(', '.').replace(')', '').strip('-').partition('.')
        if KANA.fullmatch(base) and (not okuri or KANA.fullmatch(okuri)):
            yield base, okuri


def replacements(value, groups):
    for group in groups:
        if value in group:
            yield from (kana for kana in group if kana != value)


def plausible(reading):
    return (KANA.fullmatch(reading) and reading[0] not in SMALL and
            all(i + 1 < len(reading) and reading[i + 1] in SOKUON_NEXT
                for i, kana in enumerate(reading) if kana == 'っ'))


def sound_errors(part):
    # Read palatalized kana as one unit. Changes only affect kanji portions.
    mora = MORA.findall(part)
    for i, unit in enumerate(mora):
        before, after = ''.join(mora[:i]), ''.join(mora[i + 1:])
        if unit.endswith(('ゃ', 'ゅ', 'ょ')):
            for small in replacements(unit[-1], ('ゃゅょ',)):
                yield 'palatal', before + unit[:-1] + small + after
            yield 'palatal', before + unit[:-1] + after
        for kana in replacements(unit[0], VOICE):
            yield 'voicing', before + kana + unit[1:] + after
        if unit == 'っ':
            for stop in ('', 'く', 'つ', 'ち', 'き'):
                yield 'geminate', before + stop + after
        elif after[:1] in SOKUON_NEXT and unit in ('き', 'く', 'ち', 'つ'):
            yield 'geminate', before + 'っ' + after
        preceding = mora[i - 1][-1] if i else ''
        long_tail = bool(preceding) and (unit == 'ー' or (unit == 'う' and preceding in O_ROW + U_ROW) or
                                        (unit == 'い' and preceding in E_ROW + 'い') or unit in ('お', 'え') and unit == preceding)
        if long_tail:
            yield 'length', before + after
        if not long_tail and unit[-1] in O_ROW + U_ROW + E_ROW and (not after or after[0] not in 'あいうえおんっー'):
            long = 'い' if unit[-1] in E_ROW else 'う'
            if not after.startswith(long):
                yield 'length', before + unit + long + after
        for category, groups in (('vowel', VOWELS), ('consonant', CONSONANTS)):
            if len(unit) == 1:
                for kana in replacements(unit, groups):
                    yield category, before + kana + after


class ReadingChoices:
    def __init__(self, levels, imported):
        self.words = defaultdict(set, {word: set(readings) for word, readings in COMMON_VARIANTS.items()})
        self.characters = defaultdict(set)
        for level in levels:
            source = imported[level['id']]
            for item in source['vocab']:
                self.words[hira(item['w'])].add(hira(item['r']))
            for item in source['kanji']:
                self.characters[item['ch']].update(stems(item['on'], item['kun']))
            for word, reading, *_ in level['vocab']:
                self.words[hira(word)].add(hira(reading))
            for ch, on, kun, _, examples in level['kanji']:
                self.characters[ch].update(stems(on, kun))
                for word, reading, _ in examples:
                    self.words[hira(word)].add(hira(reading))

    def known(self, word):
        word = hira(word)
        readings = set(self.words.get(word, ()))
        if len(word) == 1:
            readings.update(base for base, _ in self.characters.get(word, ()))
        elif KANJI.match(word) and KANA.fullmatch(word[1:]):
            # The okurigana must match before a kun reading counts as an alias.
            readings.update(base + suffix for base, suffix in self.characters.get(word[0], ()) if suffix == word[1:])
        return readings

    def components(self, chars, part):
        # Find a segmentation that already matches the correct reading. Only
        # swap one kanji's reading in that segmentation.
        parts = []

        def align(index, remaining):
            if index == len(chars):
                return not remaining
            char = chars[index] if chars[index] != '々' else chars[index - 1]
            bases = {base for base, _ in self.characters.get(char, ())}
            if not bases:
                return False
            forms = bases | {v for base in bases for category, v in sound_errors(base)
                              if category in ('geminate', 'voicing')}
            for form in sorted(forms, key=lambda value: (value not in bases, -len(value), value)):
                if remaining.startswith(form) and len(remaining) >= len(form) + len(chars) - index - 1:
                    parts.append((form, bases))
                    if align(index + 1, remaining[len(form):]):
                        return True
                    parts.pop()
            return False

        if not align(0, part):
            return
        for i, (actual, bases) in enumerate(parts):
            for alternate in sorted(bases, key=lambda value: (abs(len(value) - len(actual)), value)):
                actual_mora, alternate_mora = MORA.findall(actual), MORA.findall(alternate)
                distance = abs(len(alternate_mora) - len(actual_mora))
                if (alternate != actual and distance <= 1 and
                        (not distance or set(actual_mora) & set(alternate_mora))):
                    yield ''.join(alternate if j == i else value for j, (value, _) in enumerate(parts))

    def wrong(self, word, reading):
        spelling, answer = hira(word), hira(reading)
        written = unicodedata.normalize('NFKC', reading)
        katakana = re.fullmatch(r'[ァ-ヶー]+', written)
        if not katakana and not KANA.fullmatch(written):
            return []
        if not KANJI.search(spelling) or not plausible(answer) or self.words.get(spelling, {answer}) != {answer}:
            return []
        chunks = re.split(r'([一-龯々]+)', spelling)
        pattern = ''.join('(.+?)' if i % 2 else re.escape(chunk) for i, chunk in enumerate(chunks))
        matched = re.fullmatch(pattern, answer)
        if not matched:
            return []
        forbidden = self.known(spelling) | {answer}
        candidates = defaultdict(dict)
        for group, part in enumerate(matched.groups(), 1):
            start, end = matched.span(group)
            chars = chunks[2 * group - 1]
            alternates = [('component', value) for value in self.components(chars, part)]
            for category, changed in alternates + list(sound_errors(part)):
                if category == 'length' and chunks[2 * group] and len(MORA.findall(part)) == 1 and len(changed) > len(part):
                    continue
                candidate = answer[:start] + changed + answer[end:]
                if candidate not in forbidden and plausible(candidate):
                    candidates[category][candidate] = abs(len(MORA.findall(candidate)) - len(MORA.findall(answer)))

        wrong = [value for value in COMMON_DISTRACTORS.get(spelling, ())
                 if value not in forbidden and plausible(value) and re.fullmatch(pattern, value)]
        priority = ('geminate', 'voicing', 'component', 'palatal', 'length', 'vowel', 'consonant')
        for category in priority:
            if len(wrong) >= 3:
                break
            choices = candidates[category]
            if choices:
                # A different spelling of an okurigana or a legitimate word
                # reading is never used as a distractor.
                choice = min((value for value in choices if value not in wrong),
                             key=lambda value: (choices[value], value[0] != answer[0], value), default=None)
                if choice:
                    wrong.append(choice)
        if len(wrong) < 3:
            for category in priority:
                wrong.extend(value for value in candidates[category] if value not in wrong)
        return [choice.translate(HIRA_TO_KANA) if katakana else choice for choice in wrong[:3]]
