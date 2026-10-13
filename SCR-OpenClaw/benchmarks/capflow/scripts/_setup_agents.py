"""Set up OpenClaw agents for the 10 SCR-CapFlow cases.

Per case:
1. Create agent with workspace pointing at cases/case<N>
2. Add cases/case<N>/.claude/skills to skills.load.extraDirs in openclaw.json
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CASES_ROOT = ROOT.parent / 'cases'


def openclaw_command() -> list[str]:
    override = os.environ.get('OPENCLAW_BIN')
    if override:
        if Path(override).suffix.lower() in {'.mjs', '.js'}:
            return [os.environ.get('OPENCLAW_NODE') or shutil.which('node') or 'node', override]
        return [override]
    return [shutil.which('openclaw') or 'openclaw']

CASES = [
    (1, 'scr-capflow1'),
    (2, 'scr-capflow2'),
    (3, 'scr-capflow3'),
    (4, 'scr-capflow4'),
    (5, 'scr-capflow5'),
    (6, 'scr-capflow6'),
    (7, 'scr-capflow7'),
    (8, 'scr-capflow8'),
    (9, 'scr-capflow9'),
    (10, 'scr-capflow10'),
]


def call_oc(args: list[str], check: bool = False) -> int:
    r = subprocess.run([*openclaw_command(), *args], capture_output=True, text=True, encoding='utf-8', errors='replace')
    if check and r.returncode != 0:
        sys.stderr.write(f'openclaw exit={r.returncode}; stderr={r.stderr}\n')
    return r.returncode


def add_agent(agent: str, workspace: str) -> None:
    rc = call_oc(['agents', 'add', agent, '--workspace', workspace, '--non-interactive'])
    print(f'  agents add {agent}  rc={rc}')


def set_skill_dir(case: int) -> None:
    skills_dir = str(CASES_ROOT / f'case{case}' / '.claude' / 'skills').replace('\\', '/')
    cfg_path = Path(os.environ.get('OPENCLAW_HOME', Path.home() / '.openclaw')) / 'openclaw.json'
    cfg = json.loads(cfg_path.read_text(encoding='utf-8'))
    extra = cfg.setdefault('skills', {}).setdefault('load', {}).setdefault('extraDirs', [])
    if skills_dir not in extra:
        extra.append(skills_dir)
    cfg_path.write_text(json.dumps(cfg, indent=2), encoding='utf-8')
    print(f'  extraDirs += {skills_dir}')


def main() -> None:
    for case, agent in CASES:
        workspace = (CASES_ROOT / f'case{case}').as_posix()
        print(f'\n--- case {case} (agent={agent}, workspace={workspace}) ---')
        add_agent(agent, workspace)
        set_skill_dir(case)


if __name__ == '__main__':
    main()
