#!/usr/bin/env python3
"""Apply SHA-256-verified guarded edits from a Hosted container file.

The edits are delivered via containers.files.create, NOT as a large shell
argument. Only main.tex can be changed; the original source hash, non-overlap
and old snippets are validated before writing any bytes.
"""
import argparse
import hashlib
import json
from pathlib import Path


def apply(payload_file: Path, expected_digest: str, target: Path) -> int:
    if not payload_file.is_file() or not payload_file.resolve().is_relative_to(Path('/mnt/data')):
        raise ValueError('invalid payload file')
    payload = payload_file.read_bytes()
    if hashlib.sha256(payload).hexdigest() != expected_digest:
        raise ValueError('payload SHA-256 mismatch')
    edits = json.loads(payload)
    if not isinstance(edits, list) or len(edits) > 1000:
        raise ValueError('invalid edits')
    text = target.read_text(encoding='utf-8')
    digest = hashlib.sha256(text.encode('utf-8')).hexdigest()
    if any(not isinstance(edit, dict) for edit in edits):
        raise ValueError('invalid edit entry')
    ordered = sorted(edits, key=lambda edit: edit['offset'])
    previous_end = 0
    for edit in ordered:
        if edit['path'] != 'main.tex' or edit['expected_sha256'] != digest:
            raise ValueError('wrong target or stale hash')
        offset, original, replacement = edit['offset'], edit['old'], edit['new']
        if (type(offset) is not int or not isinstance(original, str)
                or not isinstance(replacement, str) or offset < previous_end
                or offset < 0 or offset + len(original) > len(text)):
            raise ValueError('invalid or overlapping edit')
        if text[offset:offset+len(original)] != original:
            raise ValueError('stale edit')
        previous_end = offset + len(original)
    for edit in reversed(ordered):
        off = edit['offset']
        text = text[:off] + edit['new'] + text[off + len(edit['old']):]
    temporary = target.with_suffix('.tex.quality-tmp')
    temporary.write_text(text, encoding='utf-8')
    temporary.replace(target)
    print(f'CA-QUALITY-EDITS-V2 applied={len(edits)} payload_sha256={expected_digest}')
    return len(edits)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--edits-file', type=Path, required=True)
    parser.add_argument('--sha256', required=True)
    args = parser.parse_args()
    if len(args.sha256) != 64 or any(c not in '0123456789abcdef' for c in args.sha256):
        raise ValueError('invalid digest')
    apply(args.edits_file, args.sha256, Path('/mnt/data/work/job/result/main.tex'))


if __name__ == '__main__':
    main()
