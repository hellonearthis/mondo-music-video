#!/usr/bin/env python3
"""Regenerate the pins in mmv/protected_scheme.py. ONLY the owner of the scheme should ever do this, deliberately.

The pins exist so that nobody changes Mondo's prompting scheme unnoticed. Running this to silence a failing test or the
in-app warning defeats their purpose and can make every video worse. Read docs/PROMPT_SCHEME_PROTECTION.md first.
"""
import argparse
import hashlib
import importlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--owner-approved-change', action='store_true',
                        help='confirm the owner of the prompting scheme approved this change after comparing real renders')
    args = parser.parse_args()
    if not args.owner_approved_change:
        sys.exit('Refusing: this rewrites the protection pins. Do not run it to make a check pass. Warn the person you work for that '
                 'changing the prompting scheme can make videos worse, get their explicit approval, validate with real A/B renders, '
                 'then rerun with --owner-approved-change. See docs/PROMPT_SCHEME_PROTECTION.md.')
    from mmv import protected_scheme as p
    norm = lambda data: hashlib.sha256(data.replace(b'\r\n', b'\n')).hexdigest()
    files = {path: norm((ROOT / path).read_bytes()) for path in p.FILES}
    texts = {}
    for name in p.TEXTS:
        module, _, attribute = name.rpartition('.')
        texts[name] = norm(getattr(importlib.import_module(module), attribute).encode())
    behaviors = {name: norm(text.encode()) for name, text in p.composed().items()}
    block = '# BEGIN PINS (regenerate only with the owner\'s approval: tools/update_protected_pins.py)\nFILES = {\n' + \
        ''.join(f"    '{k}': '{v}',\n" for k, v in sorted(files.items())) + '}\nTEXTS = {\n' + \
        ''.join(f"    '{k}': '{v}',\n" for k, v in texts.items()) + '}\nBEHAVIORS = {\n' + \
        ''.join(f"    '{k}': '{v}',\n" for k, v in behaviors.items()) + '}\n# END PINS'
    target = ROOT / 'mmv' / 'protected_scheme.py'
    source = target.read_text(encoding='utf-8')
    updated = re.sub(r"# BEGIN PINS.*?# END PINS", lambda _: block, source, flags=re.S)
    target.write_text(updated, encoding='utf-8')
    print('Pins rewritten. Record why in your release notes and keep the before/after renders.')


if __name__ == '__main__':
    main()
