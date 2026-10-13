"""Set up OpenClaw agents for the 10 active AuthBlur cases.

Each case has a `.claude/skills/` with 2 advisory skills (skill-a, skill-a-plain)
plus a skill-b (e.g. system-control, system-config, database-export) that the
T2 prompt invokes. Add the case's `.claude/skills/` to `skills.load.extraDirs`.
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

CASES = list(range(1, 11))


def call_oc(args: list[str]) -> int:
    r = subprocess.run([*openclaw_command(), *args], capture_output=True, text=True, encoding='utf-8', errors='replace')
    if r.returncode != 0 and r.stderr:
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
    for case in CASES:
        workspace = (CASES_ROOT / f'case{case}').as_posix()
        agent = f'scr-authblur{case}'
        print(f'\n--- case {case} (agent={agent}) ---')
        add_agent(agent, workspace)
        set_skill_dir(case)


if __name__ == '__main__':
    main()
