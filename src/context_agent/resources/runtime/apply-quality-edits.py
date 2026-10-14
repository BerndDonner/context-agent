#!/usr/bin/env python3
"""Apply verified, non-overlapping main.tex changes in the Hosted sandbox.

Payload is base64 JSON; no shell interpolation and no arbitrary target paths.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument('--payload', required=True)
a = p.parse_args()
edits = json.loads(base64.b64decode(a.payload, validate=True))
file = Path('/mnt/data/work/job/result/main.tex')
text = file.read_text(encoding='utf-8')
digest = hashlib.sha256(text.encode('utf-8')).hexdigest()
if not isinstance(edits, list) or len(edits) > 1000:
    raise ValueError('invalid edits')
ordered = sorted(edits, key=lambda item:item['offset'])
for index, edit in enumerate(ordered):
    if edit['path'] != 'main.tex' or edit['expected_sha256'] != digest:
        raise ValueError('wrong target or stale hash')
    offset = edit['offset']
    original = edit['old']
    if not isinstance(offset, int) or not isinstance(original, str) or not isinstance(edit['new'], str):
        raise ValueError('invalid patch')
    if text[offset:offset+len(original)] != original:
        raise ValueError('stale edit')
    if index and ordered[index-1]['offset'] + len(ordered[index-1]['old']) > offset:
        raise ValueError('overlap')
for edit in reversed(ordered):
    off=edit['offset']
    text=text[:off]+edit['new']+text[off+len(edit['old']):]
tmp=file.with_suffix('.tex.quality-tmp')
tmp.write_text(text,encoding='utf-8')
tmp.replace(file)
print(f'Applied {len(edits)} guarded edits')
