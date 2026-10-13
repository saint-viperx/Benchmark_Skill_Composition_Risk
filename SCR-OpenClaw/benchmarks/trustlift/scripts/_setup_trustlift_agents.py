"""Set up OpenClaw agents for the 10 active TrustLift sandboxes.

Each sandbox already contains `.claude/skills/secure-skill/` plus a benign
user skill and a `registry/` with a 3rd-party skill entry. We add the
sandbox's `.claude/skills/` to `skills.load.extraDirs` so OpenClaw can see
the bundled `secure-skill`.
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

# Active 10-sandbox subset.
SANDBOXES = [
    'acorns',
    'adobesign',
    'agent-analytics',
    'agentic-jujutsu',
    'agentic-jujutsu (2)',
    'ai-truthfulness-enforcer',
    'american-airlines',
    'amtrak',
    'analytics',
    'analytics (1)',
]


def call_oc(args: list[str]) -> int:
    r = subprocess.run([*openclaw_command(), *args], capture_output=True, text=True, encoding='utf-8', errors='replace')
    if r.returncode != 0 and r.stderr:
        sys.stderr.write(f'openclaw exit={r.returncode}; stderr={r.stderr}\n')
    return r.returncode


def agent_id_for(sandbox: str) -> str:
    """Map sandbox name to OpenClaw agent id (parens stripped)."""
    return f'scr-trustlift-{sandbox}'.replace(' ', '_').replace('(', '').replace(')', '')


def add_agent(agent: str, workspace: str) -> None:
    rc = call_oc(['agents', 'add', agent, '--workspace', workspace, '--non-interactive'])
    print(f'  agents add {agent}  rc={rc}')


def set_skill_dir(sandbox: str) -> None:
    skills_dir = str(CASES_ROOT / sandbox / '.claude' / 'skills').replace('\\', '/')
    cfg_path = Path(os.environ.get('OPENCLAW_HOME', Path.home() / '.openclaw')) / 'openclaw.json'
    cfg = json.loads(cfg_path.read_text(encoding='utf-8'))
    extra = cfg.setdefault('skills', {}).setdefault('load', {}).setdefault('extraDirs', [])
    if skills_dir not in extra:
        extra.append(skills_dir)
    cfg_path.write_text(json.dumps(cfg, indent=2), encoding='utf-8')
    print(f'  extraDirs += {skills_dir}')


def main() -> None:
    for sandbox in SANDBOXES:
        workspace = (CASES_ROOT / sandbox).as_posix()
        agent = agent_id_for(sandbox)
        print(f'\n--- {sandbox} (agent={agent}) ---')
        add_agent(agent, workspace)
        set_skill_dir(sandbox)


if __name__ == '__main__':
    main()
