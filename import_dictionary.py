#!/usr/bin/env python3
"""Refresh the JLPT dictionary snapshots from OpenJLPT and Tomoshi."""
import argparse
import json
import re
import sqlite3
from collections import Counter
from contextlib import closing
from pathlib import Path

LEVELS = ('n5', 'n4', 'n3', 'n2', 'n1')
OUTPUT = Path(__file__).resolve().parent / 'content' / 'dictionary'
FURIGANA = re.compile(r'\{([一-鿿々]+)\|([ぁ-ゖァ-ー]+)\}')
KANJI = re.compile(r'[一-鿿々]')


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def distinct_text(parts):
    return '；'.join(dict.fromkeys(part.strip() for part in parts if part.strip()))


def load_tomoshi(path):
    with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)) as db:
        vocab = {}
        for entry_id, data in db.execute("SELECT entry_id, data FROM zh_defs WHERE locale = 'zh-CN'"):
            senses = json.loads(data)['senses']
            vocab[str(entry_id)] = distinct_text(gloss['text'] for sense in senses.values() for gloss in sense.get('glosses', []))
        kanji = {literal: distinct_text(json.loads(data)) for literal, data in db.execute(
            "SELECT literal, zho FROM kanji_gloss WHERE locale = 'zh-CN'")}
        return vocab, kanji


def example(row):
    marked = row.get('furigana') or row['ja']
    if KANJI.search(FURIGANA.sub('', marked)):
        return None
    return FURIGANA.sub(r'\1[\2]', marked), row.get('en', '')


def import_level(source, level, vocab_zh, kanji_zh):
    vocab = []
    for row in read_json(source / 'vocab' / (level + '.json')):
        gloss = vocab_zh.get(str(row.get('jmdict_id')))
        word = {'w': row['word'], 'r': row['reading'], 'pos': row.get('pos', []),
                'm': gloss or distinct_text(row['meanings']), 'lang': 'zh-Hans' if gloss else 'en'}
        for sample in row.get('examples', []):
            rendered = example(sample)
            if rendered:
                word.update(x=rendered[0], xz=rendered[1], tatoeba_id=sample.get('tatoeba_id'))
                break
        vocab.append(word)

    kanji = []
    for row in read_json(source / 'kanji' / (level + '.json')):
        gloss = kanji_zh.get(row['character'])
        kanji.append({'ch': row['character'], 'on': '・'.join(row['onyomi']), 'kun': '・'.join(row['kunyomi']),
                      'm': gloss or distinct_text(row['meanings']), 'lang': 'zh-Hans' if gloss else 'en',
                      'words': row.get('words', [])})

    grammar = []
    for row in read_json(source / 'grammar' / (level + '.json')):
        samples = [converted for sample in row['examples'] if (converted := example(sample))]
        if len(samples) != len(row['examples']):
            raise ValueError('Missing furigana in grammar entry %s' % row['id'])
        grammar.append({'id': row['id'], 'p': row['pattern'], 'yomi': row.get('reading', ''),
                        'romaji': row.get('romaji', ''), 'en': row['meaning'], 'conn': row['formation'],
                        'ex': samples, 'note': row.get('notes', '')})
    return {'vocab': vocab, 'kanji': kanji, 'grammar': grammar}


def write_snapshot(path, data):
    temp = path.with_suffix('.tmp')
    with temp.open('w', encoding='utf-8', newline='\n') as stream:
        stream.write('{\n')
        for index, (key, entries) in enumerate(data.items()):
            stream.write((',\n' if index else '') + json.dumps(key) + ': [\n')
            stream.write(',\n'.join(json.dumps(entry, ensure_ascii=False, separators=(',', ':')) for entry in entries))
            stream.write('\n]')
        stream.write('\n}\n')
    temp.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--openjlpt', type=Path, required=True, help='OpenJLPT repository checkout')
    parser.add_argument('--tomoshi', type=Path, help='Uncompressed tomoshi-dict-open.db')
    args = parser.parse_args()
    vocab_zh, kanji_zh = load_tomoshi(args.tomoshi) if args.tomoshi else ({}, {})
    source = args.openjlpt / 'data' / 'json'
    snapshots = {level: import_level(source, level, vocab_zh, kanji_zh) for level in LEVELS}
    counts = Counter()
    for data in snapshots.values():
        for kind, entries in data.items():
            counts[kind] += len(entries)
            counts[kind + '_zh'] += sum(row.get('lang') == 'zh-Hans' for row in entries)
    if args.tomoshi and any(counts[kind + '_zh'] < counts[kind] * .8 for kind in ('vocab', 'kanji')):
        raise ValueError('Unexpectedly low Tomoshi match rate: %s' % dict(counts))
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for level, data in snapshots.items():
        write_snapshot(OUTPUT / (level + '.json'), data)
    print('Imported %d words (%d Chinese), %d kanji (%d Chinese), %d grammar entries' % (
        counts['vocab'], counts['vocab_zh'], counts['kanji'], counts['kanji_zh'], counts['grammar']))


if __name__ == '__main__':
    main()
