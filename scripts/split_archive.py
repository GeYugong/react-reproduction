"""Split a completed archive into Git-compatible parts with restoration hashes."""
import argparse
import hashlib
import json
from pathlib import Path


def split_archive(source, record_path):
    record = json.loads(record_path.read_text(encoding='utf-8-sig'))
    whole = hashlib.sha256()
    parts = []
    with source.open('rb') as stream:
        while block := stream.read(45 * 1024 * 1024):
            whole.update(block)
            target = source.with_name(source.name + f'.part{len(parts):03d}')
            digest = hashlib.sha256(block).hexdigest()
            if target.exists():
                assert hashlib.sha256(target.read_bytes()).hexdigest() == digest
            else:
                target.write_bytes(block)
            parts.append({'path':str(target.as_posix()), 'bytes':len(block), 'sha256':digest})
    assert whole.hexdigest() == record['sha256']
    assert sum(p['bytes'] for p in parts) == record['bytes']
    record['parts'] = parts
    record['restore'] = 'Concatenate part files in listed order as binary bytes; verify archive SHA256 before extracting.'
    record_path.write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'parts':len(parts),'sha256':whole.hexdigest()}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('record', type=Path)
    args = parser.parse_args()
    split_archive(args.source, args.record)
