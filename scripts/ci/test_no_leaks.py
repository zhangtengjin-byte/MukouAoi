#!/usr/bin/env python3
"""CI test: no personal info leaks"""
import sys, os

keywords = [
    'spicysugar', '神大人', 'SnowLuma', 'TSaZ~tsGpZEJFUvg',
    '3841303389', '2108929103', 'linling', '琳玲', '2513924725',
]
SELF = os.path.basename(__file__)
errors = []
for root, dirs, files in os.walk('.'):
    if '.git' in root:
        continue
    for f in files:
        if f == SELF:
            continue
        path = os.path.join(root, f)
        try:
            content = open(path, 'rb').read().decode('utf-8', errors='ignore')
            for kw in keywords:
                if kw in content:
                    errors.append(f'{path}: found "{kw}"')
        except Exception:
            pass
if errors:
    for e in errors:
        print(f'LEAK: {e}')
    sys.exit(1)
print('Zero personal information leaks')
