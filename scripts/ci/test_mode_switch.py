#!/usr/bin/env python3
"""CI test: mode-switch core logic"""
code = open('plugins/mode-switch/__init__.py').read()
ctx = {'__file__': 'plugins/mode-switch/__init__.py'}
exec(code.split('def register')[0], ctx)

assert ctx['get_mode']() in ('work', 'life')
ctx['set_mode']('life')
assert ctx['get_mode']() == 'life'
ctx['set_mode']('work')
assert ctx['get_mode']() == 'work'

print('ALL PASS')
