#!/usr/bin/env python3
"""CI test: tone_map 24 emotions x 5 levels"""
import json

t = json.load(open('mukou_aoi/examples/tone_map.json'))
defined = [k for k in t.keys() if not k.startswith('_')]
singles = {'joy', 'sadness', 'anger', 'fear', 'surprise', 'disgust', 'anticipation', 'trust'}
compound = set(t.get('_compound_emotions', {}).keys())

assert len(defined) == 24, f'got {len(defined)} expected 24'
assert not (singles - set(defined)), f'missing singles: {singles - set(defined)}'
assert not (compound - set(defined)), f'missing compounds: {compound - set(defined)}'

for k in defined:
    lvls = t[k].get('levels', {})
    assert set(lvls.keys()) == {'极强', '强', '中', '弱', '微'}, f'{k} bad levels'
    for lname, ldata in lvls.items():
        assert 'style' in ldata
        assert '模板' in ldata
        for field in ['句式示例', '语气词', '禁用词']:
            assert field in ldata['模板'], f'{k}/{lname} missing {field}'

print(f'{len(defined)} emotions x 5 levels = ALL VALID')
