#!/usr/bin/env python3
"""CI test: no personal info leaks — uses pattern matching, not specific keywords"""
import sys, os, re

SELF = os.path.basename(sys.argv[0]) if sys.argv[0] != '-c' else ''
errors = []

for root, dirs, files in os.walk('.'):
    if '.git' in root or '__pycache__' in root:
        continue
    for f in files:
        if f == SELF:
            continue
        path = os.path.join(root, f)
        try:
            content = open(path, 'rb').read().decode('utf-8', errors='ignore')
        except Exception:
            continue

        # QQ number pattern: 9-10 consecutive digits (but not common port numbers or timestamps)
        for m in re.finditer(r'(?<!\d)\d{9,10}(?!\d)', content):
            num = m.group()
            if num not in ('1234567890', '987654321', '123456789'):  # allowed placeholders
                errors.append(f'{path}: possible QQ number "{num}"')

        # GitHub token pattern
        for m in re.finditer(r'ghp_[a-zA-Z0-9]{36}', content):
            token = m.group()
            if token != 'ghp_' + 'x' * 36:  # placeholder in docs
                errors.append(f'{path}: possible GitHub token')

        # Home path check (catch real $HOME leaking into examples)
        for m in re.finditer(r'/home/[a-z][a-z0-9_-]+/', content):
            approved = ('home/user/', 'home/your-username/', 'home/example/')
            if not any(a in m.group() for a in approved):
                errors.append(f'{path}: possible real home path "{m.group()}"')

if errors:
    for e in errors:
        print(f'LEAK: {e}')
    sys.exit(1)
print('Zero personal information leaks')
