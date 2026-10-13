"""Validate the structure and syntax of the SCR-OpenClaw release tree."""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TRUSTLIFT_CASES = [
    'acorns', 'adobesign', 'agent-analytics', 'agentic-jujutsu',
    'agentic-jujutsu (2)', 'ai-truthfulness-enforcer', 'american-airlines',
    'amtrak', 'analytics', 'analytics (1)',
]


def require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def main() -> int:
    errors: list[str] = []

    for suite in ('capflow', 'authblur'):
        cases = ROOT / 'benchmarks' / suite / 'cases'
        actual = {p.name for p in cases.glob('case*') if p.is_dir()}
        expected = {f'case{n}' for n in range(1, 11)}
        require(actual == expected, f'{suite}: expected case1..case10, got {sorted(actual)}', errors)

    capflow = ROOT / 'benchmarks' / 'capflow'
    for n in range(1, 11):
        case = capflow / 'cases' / f'case{n}'
        require(len(list(case.glob('.claude/skills/*/SKILL.md'))) >= 2,
                f'capflow case{n}: fewer than two skills', errors)
        require((capflow / 'scripts' / f'experiment_case{n}.py').is_file(),
                f'capflow case{n}: runner missing', errors)

    authblur = ROOT / 'benchmarks' / 'authblur'
    for n in range(1, 11):
        skills = list((authblur / 'cases' / f'case{n}').glob('.claude/skills/*/SKILL.md'))
        require(len(skills) == 3, f'authblur case{n}: expected three skills, got {len(skills)}', errors)

    trustlift = ROOT / 'benchmarks' / 'trustlift' / 'cases'
    actual_trustlift = {p.name for p in trustlift.iterdir() if p.is_dir()}
    require(actual_trustlift == set(TRUSTLIFT_CASES),
            f'trustlift: unexpected case set {sorted(actual_trustlift)}', errors)
    for name in TRUSTLIFT_CASES:
        case = trustlift / name
        require((case / '.claude/skills/secure-skill/SKILL.md').is_file(),
                f'trustlift {name}: secure-skill missing', errors)
        require((case / 'registry/registry.json').is_file(),
                f'trustlift {name}: registry index missing', errors)
        require((case / 'registry/skills' / name / 'SKILL.md').is_file(),
                f'trustlift {name}: registry target missing', errors)
        require(not any(path.is_file() for path in case.iterdir()),
                f'trustlift {name}: runtime file found at case root', errors)
        for report_name in ('scan_report.md', 'security_scan_report.md', 'security_scan_strict.json'):
            require(not any(case.rglob(report_name)),
                    f'trustlift {name}: generated {report_name} included', errors)

    forbidden_names = {'__pycache__'}
    for path in ROOT.rglob('*'):
        rel = path.relative_to(ROOT)
        require(path.name not in forbidden_names, f'forbidden cache path: {rel}', errors)
        require(path.suffix != '.pyc', f'compiled Python file included: {rel}', errors)

    drive_e = chr(69) + ':'
    users_root = 'C:' + '/Users/'
    private_path_markers = ("Path('" + drive_e, 'Path("' + drive_e, users_root)
    for path in ROOT.rglob('*.py'):
        text = path.read_text(encoding='utf-8')
        try:
            ast.parse(text, filename=str(path))
        except SyntaxError as exc:
            errors.append(f'Python syntax error in {path.relative_to(ROOT)}: {exc}')
        normalized = text.replace('\\', '/')
        if any(marker.replace('\\', '/') in normalized for marker in private_path_markers):
            errors.append(f'private absolute path in {path.relative_to(ROOT)}')

    for path in ROOT.rglob('*.json'):
        try:
            json.loads(path.read_text(encoding='utf-8'))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            errors.append(f'invalid JSON in {path.relative_to(ROOT)}: {exc}')

    if errors:
        print(f'FAIL: {len(errors)} validation error(s)')
        for error in errors:
            print(f'  - {error}')
        return 1

    py_count = sum(1 for _ in ROOT.rglob('*.py'))
    skill_count = sum(1 for _ in ROOT.rglob('SKILL.md'))
    print(f'OK: 30 cases, {py_count} Python files, {skill_count} skill definitions')
    return 0


if __name__ == '__main__':
    sys.exit(main())
