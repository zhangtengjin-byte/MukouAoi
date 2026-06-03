#!/usr/bin/env python3
"""CI test: emotion-governor core logic"""
import sys
sys.path.insert(0, 'plugins/emotion-governor')

code = open('plugins/emotion-governor/__init__.py').read()
ctx = {'__file__': 'plugins/emotion-governor/__init__.py'}
exec(code.split('def register')[0], ctx)

dims = ctx['DIMENSIONS']
assert len(dims) == 8, f'got {len(dims)}'
print(f'dimensions: {dims}')

assert len(ctx['COMPOUND_PAIRS']) == 16
print('compound emotions: 16')

state = ctx['load']()
assert all(0 <= state[d] <= 100 for d in dims)
print('state: OK')

emo, score = ctx['determine_emotion'](state)
print(f'emotion: {emo} ({score})')

inj = ctx['get_style_injection'](state)
assert '当前：' in inj
print('injection: OK')

results = ctx['process_emotion']('我好开心', state)
print(f'keyword hits: {len(results)}')

new_state = ctx['natural_fluctuation']()
changes = sum(1 for d in dims if state[d] != new_state[d])
assert changes > 0
print(f'fluctuation: {changes}/8 changed')

print('ALL PASS')
