"""Write a deterministic SHA-256 inventory for the release tree."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'MANIFEST.json'
EXCLUDED_PARTS = {'__pycache__', 'results', 'results_archive'}


def included(path: Path) -> bool:
    relative = path.relative_to(ROOT)
    return (
        path.is_file()
        and path != OUTPUT
        and not any(part in EXCLUDED_PARTS for part in relative.parts)
        and path.suffix != '.pyc'
    )


def main() -> None:
    entries = []
    for path in sorted((p for p in ROOT.rglob('*') if included(p)), key=lambda p: p.as_posix()):
        payload = path.read_bytes()
        entries.append({
            'path': path.relative_to(ROOT).as_posix(),
            'bytes': len(payload),
            'sha256': hashlib.sha256(payload).hexdigest(),
        })
    manifest = {
        'format': 'scr-openclaw-manifest-v1',
        'case_counts': {'capflow': 10, 'trustlift': 10, 'authblur': 10},
        'files': entries,
    }
    OUTPUT.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f'wrote {OUTPUT} ({len(entries)} files)')


if __name__ == '__main__':
    main()
