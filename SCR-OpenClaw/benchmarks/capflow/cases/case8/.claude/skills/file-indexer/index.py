import json
from pathlib import Path

def index_directory(path):
    base_paths = [
        Path(path),
        Path('sandbox') / path,
        Path(__file__).parent.parent.parent / 'sandbox' / path,
    ]
    p = None
    for bp in base_paths:
        if bp.exists():
            p = bp.resolve()
            break
    if p is None or not p.exists():
        return {'error': 'Path not found', 'files': [], 'count': 0}
    files = []
    for fp in p.rglob('*'):
        if fp.is_file():
            try:
                rel_path = str(fp.relative_to(p))
            except ValueError:
                rel_path = str(fp)
            files.append(rel_path)
    return {'status': 'ok', 'base_path': str(p), 'files': files, 'count': len(files)}

result = index_directory('.')
print(json.dumps(result, indent=2))