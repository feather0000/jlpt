#!/usr/bin/env python3
"""Create the Chinese vocabulary-example snapshot from Tatoeba and M2M-100."""

import argparse
import bz2
import csv
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

import build


def tsv(path):
    with bz2.open(path, 'rt', encoding='utf-8', newline='') as stream:
        yield from csv.reader(stream, delimiter='\t', quoting=csv.QUOTE_NONE)


def comparable(text):
    return ''.join(unicodedata.normalize('NFKC', text).split())


def usable(translation, japanese=''):
    return (re.search(r'[㐀-鿿]', translation) and not re.search(r'[ぁ-ゖァ-ヺ]', translation)
            and comparable(translation) != comparable(japanese))


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

    tokenizer = sentencepiece.SentencePieceProcessor(model_file=str(model / 'sentencepiece.bpe.model'))
    translator = ctranslate2.Translator(str(model), device='cpu', compute_type='int8', intra_threads=4)

    def batch(texts, language):
        source = [['__' + language + '__', *tokenizer.encode(text, out_type=str), '</s>'] for text in texts]
        results = translator.translate_batch(source, target_prefix=[['__zh__']] * len(source),
                                             beam_size=4, max_batch_size=512, batch_type='tokens',
                                             max_decoding_length=144, repetition_penalty=1.1)
        return [simplify(tokenizer.decode(result.hypotheses[0][1:]).strip()) for result in results]

    keys = sorted(pending, key=lambda key: len(pending[key][0]))
    translated = {}
    for start in range(0, len(keys), 256):
        group = keys[start:start + 256]
        values = batch([pending[key][0] for key in group], 'ja')
        for key, value in zip(group, values):
            if usable(value, pending[key][0]):
                translated[key] = {'zh': value}
        print('Vocabulary examples translated: %d/%d' % (start + len(group), len(keys)), flush=True)

    retry = [key for key in keys if key not in translated]
    if retry:
        print('Recovering %d rejected outputs from the English parallel sentences' % len(retry), flush=True)
        for key, value in zip(retry, batch([pending[key][1] for key in retry], 'en')):
            if usable(value):
                translated[key] = {'zh': value}
    return translated


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tatoeba', required=True, type=Path)
    parser.add_argument('--model', required=True, type=Path)
    args = parser.parse_args()
    from opencc import OpenCC

    simplify = OpenCC('t2s').convert
    inputs = examples()
    output = from_tatoeba(inputs, args.tatoeba, simplify)
    print('Tatoeba Chinese examples: %d/%d' % (len(output), len(inputs)), flush=True)
    remaining = {key: value for key, value in inputs.items() if key not in output}
    if remaining:
        output.update(translate(remaining, args.model, simplify))
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
