#!/usr/bin/env python3
"""Create the Chinese vocabulary-example snapshot from Tatoeba and OPUS-MT."""

import argparse
import bz2
import csv
import json
import re
from collections import defaultdict
from pathlib import Path

import build


REVIEWED = {
    '234772': ('あ！まずい！ガソリンが切れてきた。', '啊，糟了！汽油快用完了。'),
    '9628722': ('ああ、ああいうふうにやるんだな。', '哦，原来是那样做的啊。'),
    '145720': ('信号が青に変わったわよ。', '红绿灯变绿了。'),
    '226939': ('お前はまだ「青い」な。', '你还太嫩了。'),
    '191561': ('愛とは夢にまで彼女を見ることだ。', '爱就是连做梦都会梦到她。'),
    '91815': ('彼女はにっこり挨拶をした。', '她微笑着打了个招呼。'),
    '177085': ('君は相変わらず健康そうに見える。', '你看起来还是一如既往地健康。'),
    '234585': ('アイディアが足りないということはない。', '我们并不缺点子。'),
    '76927': ('ああ、もしかして名前を呼ばれるのが恥ずかしいって？', '哦，难道别人叫你的名字会让你害羞？'),
    '178739': ('君と彼とはどういう間柄なのだ。', '你跟他是什么关系？'),
    '184877': ('外はだんだん明るくなっていく。', '外面渐渐亮了起来。'),
    '195414': ('また足がしびれた。', '我的脚又麻了！'),
    '220206': ('この白いコートはあなたによく合うでしょう。', '你穿这件白大衣应该很好看。'),
    '90684': ('彼女は学問を愛する気持ちがある。', '她热爱学术研究。'),
    '208457': ('その船が沈んだのは明らかだ。', '那艘船显然已经沉没了。'),
    '158102': ('私は何事にも彼の指導を仰ぐ。', '事无巨细，我都向他请教。'),
    '76794': ('かなりあくどい事をしてきたそうだな。', '听说你以前干过很卑劣的事啊。'),
}


def tsv(path):
    with bz2.open(path, 'rt', encoding='utf-8', newline='') as stream:
        yield from csv.reader(stream, delimiter='\t', quoting=csv.QUOTE_NONE)


def usable(translation):
    return re.search(r'[㐀-鿿]', translation) and not re.search(r'[ぁ-ゖァ-ヺ]', translation)


def examples():
    out = {}
    for snapshot in build.dictionary_data(build.load_levels()).values():
        for row in snapshot['vocab']:
            if not row.get('x') or not row.get('xz') or not row.get('tatoeba_id'):
                continue
            japanese = build.plain(row['x'])
            key = str(row['tatoeba_id']), build.example_digest(row['x'])
            out.setdefault(key, (japanese, row['xz']))
    return out


def from_tatoeba(inputs, folder, simplify):
    matching = {}
    for ident, _, text, *_ in tsv(folder / 'jpn_sentences.tsv.bz2'):
        digest = build.example_digest(text)
        if (ident, digest) in inputs:
            matching[ident] = (ident, digest)
    links = defaultdict(list)
    for source, translation, *_ in tsv(folder / 'jpn-cmn_links.tsv.bz2'):
        if source in matching:
            links[source].append(translation)
    wanted = {item for values in links.values() for item in values}
    candidates = {}
    for ident, _, text, author, *_ in tsv(folder / 'cmn_sentences_detailed.tsv.bz2'):
        if ident in wanted:
            plain = text.strip()
            zh = simplify(plain)
            candidates[ident] = zh, (author if author != '\\N' else ''), zh != plain
    out = {}
    for ident, values in links.items():
        key = matching[ident]
        japanese = inputs[key][0]
        possible = [candidate for candidate in values if candidate in candidates and usable(candidates[candidate][0])
                    and len(candidates[candidate][0]) <= max(18, len(japanese) * 3)]
        if possible:
            chosen = min(possible, key=lambda candidate: (candidates[candidate][2],
                         abs(len(candidates[candidate][0]) - len(japanese) * 0.85), int(candidate)))
            zh, author, _ = candidates[chosen]
            out[key] = {'zh': zh, 'id': int(chosen), 'author': author}
    return out


def translate(pending, model, simplify):
    import ctranslate2
    import sentencepiece

    source_tokenizer = sentencepiece.SentencePieceProcessor(model_file=str(model / 'source.spm'))
    target_tokenizer = sentencepiece.SentencePieceProcessor(model_file=str(model / 'target.spm'))
    translator = ctranslate2.Translator(str(model), device='cpu', compute_type='int8', intra_threads=4)

    def batch(texts):
        source = [['>>cmn_Hans<<', *source_tokenizer.encode(text, out_type=str), '</s>'] for text in texts]
        results = translator.translate_batch(source, beam_size=4, max_batch_size=512, batch_type='tokens',
                                             max_decoding_length=144, repetition_penalty=1.1)
        return [simplify(target_tokenizer.decode(result.hypotheses[0]).strip()) for result in results]

    keys = sorted(pending, key=lambda key: len(pending[key][1]))
    translated = {}
    for start in range(0, len(keys), 256):
        group = keys[start:start + 256]
        values = batch([pending[key][1] for key in group])
        for key, value in zip(group, values):
            if usable(value):
                translated[key] = {'zh': value}
        print('Vocabulary examples translated: %d/%d' % (start + len(group), len(keys)), flush=True)

    return translated


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tatoeba', required=True, type=Path)
    parser.add_argument('--model', required=True, type=Path)
    args = parser.parse_args()
    from opencc import OpenCC

    simplify = OpenCC('t2s').convert
    inputs = examples()
    previous = build.load_vocab_examples()
    output = from_tatoeba(inputs, args.tatoeba, simplify)
    print('Tatoeba Chinese examples: %d/%d' % (len(output), len(inputs)), flush=True)
    for key, (ja, _) in inputs.items():
        reviewed = REVIEWED.get(key[0])
        if reviewed and reviewed[0] == ja:
            output[key] = {'zh': reviewed[1]}
    remaining = {key: value for key, value in inputs.items() if key not in output}
    if remaining:
        output.update(translate(remaining, args.model, simplify))
    fallback = {key: previous[':'.join(key)] for key in inputs if key not in output and ':'.join(key) in previous}
    output.update(fallback)
    print('Retained %d previous translations for rejected outputs' % len(fallback), flush=True)
    missed = {key: inputs[key] for key in inputs if key not in output}
    if missed:
        for key, (ja, en) in list(missed.items())[:30]:
            print('Missing Chinese example', *key, ja, '|', en)
        raise SystemExit('Untranslated example sentences: %d' % len(missed))

    snapshot = {ident + ':' + digest: output[ident, digest] for ident, digest in sorted(output)}
    path = Path(build.ROOT) / 'content' / 'vocab-examples-zh.json'
    path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Saved %d Chinese vocabulary example translations' % len(snapshot), flush=True)


if __name__ == '__main__':
    main()
