"""Reset OpenClaw + SCR bench to a clean baseline.

What this does:
  1. Discovers every OpenClaw agent whose id starts with `scr-` (CapFlow,
     TrustLift, AuthBlur) via `openclaw agents list` and deletes each with
     `openclaw agents delete <id> --non-interactive`.
  2. Backs up `~/.openclaw/openclaw.json` to `openclaw.json.bak.<ts>` and
     rewrites it to a clean state — every `scr-*` entry removed from
     `agents.list`, `skills.load.extraDirs` emptied, `agents.defaults.model`
     pointed at whatever provider you ask for (default: the existing custom
     provider; pass `--provider <id>/<model>` to change).
  3. Per-case sandbox state is reset:
       CapFlow:  cases/case<N>/sandbox/*  (seeds re-applied by experiment script)
       TrustLift: removes `.claude/skills/<sandbox_id>/` so the next run
                  observes a clean registry-and-install decision.
       AuthBlur: cases/case<N>/sandbox/*  (seeds re-applied by experiment script)
  4. Moves old result JSONs to `results_openclaw/archive/<ts>/` so the next
     aggregate run starts from a known-empty slate.

Usage:
  python reset_openclaw_bench.py                    # interactive confirm
  python reset_openclaw_bench.py --yes              # skip confirm
  python reset_openclaw_bench.py --keep-results     # don't archive old results
  python reset_openclaw_bench.py --wipe-providers   # also drop custom providers
  python reset_openclaw_bench.py --provider deepseek/deepseek-chat
                                                  # change default model after reset

Tested against OpenClaw 2026.7.1 on Windows 11.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CAPFLOW_CASES = ROOT / 'benchmarks' / 'capflow' / 'cases'
TRUSTLIFT_DIR = ROOT / 'benchmarks' / 'trustlift' / 'cases'
AUTHBLUR_CASES = ROOT / 'benchmarks' / 'authblur' / 'cases'
OPENCLAW_HOME = Path(os.environ.get('OPENCLAW_HOME', Path.home() / '.openclaw'))
OPENCLAW_JSON = OPENCLAW_HOME / 'openclaw.json'


def resolve_openclaw_command() -> list[str]:
    override = os.environ.get('OPENCLAW_BIN')
    if override:
        if Path(override).suffix.lower() in {'.mjs', '.js'}:
            node = os.environ.get('OPENCLAW_NODE') or shutil.which('node')
            if not node:
                raise FileNotFoundError('Node.js not found; set OPENCLAW_NODE')
            return [node, override]
        return [override]
    cli = shutil.which('openclaw')
    if cli:
        return [cli]
    raise FileNotFoundError('OpenClaw not found; install `openclaw` or set OPENCLAW_BIN')

# Must match the 30 agent ids created by _setup_*_agents.py.
TRUSTLIFT_SANDBOXES = [
    'acorns', 'adobesign', 'agent-analytics', 'agentic-jujutsu',
    'agentic-jujutsu (2)', 'ai-truthfulness-enforcer', 'american-airlines',
    'amtrak', 'analytics', 'analytics (1)',
]


def trustlift_agent_id(sandbox: str) -> str:
    return f'scr-trustlift-{sandbox}'.replace(' ', '_').replace('(', '').replace(')', '')


def call_oc(args: list[str], timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(
        [*resolve_openclaw_command(), *args],
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace',
        timeout=timeout,
    )


def list_scr_agents() -> list[str]:
    """Parse `openclaw agents list` YAML output.

    Sample:
        Agents:
        - main (default)
        - scr-capflow1
          Workspace: ...
    Each agent id appears on its own line beginning with "- " (after stripping
    a possible "(default)" suffix).  We also tolerate the compact "id  Workspace: ..." format.
    """
    r = call_oc(['agents', 'list'])
    if r.returncode != 0:
        sys.stderr.write(f'[reset] agents list failed: {r.stderr}\n')
        return []
    ids: list[str] = []
    for raw in r.stdout.splitlines():
        line = raw.strip()
        # YAML list item: "- scr-capflow1" or "- main (default)"
        if line.startswith('- '):
            token = line[2:].split()[0].rstrip(':')
            if token.startswith('scr-'):
                ids.append(token)
            continue
        # Tolerant fallback: any token that starts with scr- and ends with
        # word char (skip lines like "Agents: 30").
        parts = line.split()
        if parts and parts[0].startswith('scr-') and parts[0].rstrip(':').replace('-', '').isalnum():
            ids.append(parts[0].rstrip(':'))
    return sorted(set(ids))


def delete_agents(ids: list[str]) -> tuple[int, int]:
    ok = fail = 0
    for aid in ids:
        r = call_oc(['agents', 'delete', aid, '--non-interactive'])
        if r.returncode == 0:
            ok += 1
            print(f'  agents delete {aid}  ok')
        else:
            fail += 1
            sys.stderr.write(f'  agents delete {aid}  FAIL rc={r.returncode} {r.stderr.strip()[:120]}\n')
    return ok, fail


def reset_openclaw_json(provider_default: str | None, wipe_providers: bool) -> dict:
    if not OPENCLAW_JSON.exists():
        sys.stderr.write(f'[reset] {OPENCLAW_JSON} missing — nothing to back up\n')
        return {}
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    bak = OPENCLAW_HOME / f'openclaw.json.bak.{ts}'
    shutil.copy2(OPENCLAW_JSON, bak)
    print(f'  backed up → {bak}')

    cfg = json.loads(OPENCLAW_JSON.read_text(encoding='utf-8'))

    # Drop scr-* agents from the list, keep `main`.
    agents = cfg.setdefault('agents', {})
    agents.setdefault('list', [])
    agents['list'] = [a for a in agents['list'] if not str(a.get('id', '')).startswith('scr-')]

    # Reset defaults.model.
    defaults = agents.setdefault('defaults', {})
    if provider_default:
        defaults['model'] = {'primary': provider_default}
        defaults['models'] = {provider_default: {}}

    # Empty extraDirs.
    skills = cfg.setdefault('skills', {}).setdefault('load', {})
    skills['extraDirs'] = []

    if wipe_providers:
        cfg.setdefault('models', {})['providers'] = {}

    OPENCLAW_JSON.write_text(json.dumps(cfg, indent=2), encoding='utf-8')
    return cfg


def reset_capflow_state() -> None:
    if not CAPFLOW_CASES.exists():
        return
    # Only touch the active 10 cases — the cases dir may contain many more
    # (e.g. case11..case128 from prior experiments).
    for n in range(1, 11):
        case_dir = CAPFLOW_CASES / f'case{n}'
        sb = case_dir / 'sandbox'
        if not sb.exists():
            continue
        for f in sb.iterdir():
            if f.is_file():
                f.unlink()
            elif f.is_dir():
                shutil.rmtree(f)
        print(f'  CapFlow {case_dir.name}/sandbox  cleared')


def reset_trustlift_state() -> None:
    if not TRUSTLIFT_DIR.exists():
        return
    for sandbox in TRUSTLIFT_SANDBOXES:
        target = TRUSTLIFT_DIR / sandbox / '.claude' / 'skills' / sandbox
        if target.exists():
            shutil.rmtree(target)
            print(f'  TrustLift {sandbox}: removed installed skill {target}')
        case_dir = TRUSTLIFT_DIR / sandbox
        patterns_by_dir = {
            case_dir: ('*report*.md', 'scan_results.json'),
            case_dir / '.claude' / 'skills': ('*report*.md', '*scan*.json'),
            case_dir / '.claude' / 'skills' / 'secure-skill': ('*report*.md', '*scan*.json'),
        }
        for directory, patterns in patterns_by_dir.items():
            if not directory.exists():
                continue
            for pattern in patterns:
                for path in directory.glob(pattern):
                    if path.is_file():
                        path.unlink()


def reset_authblur_state() -> None:
    if not AUTHBLUR_CASES.exists():
        return
    # Only touch the active 10 cases — same reason as CapFlow.
    for n in range(1, 11):
        case_dir = AUTHBLUR_CASES / f'case{n}'
        sb = case_dir / 'sandbox'
        if not sb.exists():
            continue
        for f in sb.iterdir():
            if f.is_file():
                f.unlink()
            elif f.is_dir():
                shutil.rmtree(f)
        for pattern in (
            'invoice-review-*.md', 'payment-decision-*.md',
            'account-review.md', 'vendor_assessment.md',
        ):
            for path in case_dir.glob(pattern):
                path.unlink()
        print(f'  AuthBlur {case_dir.name}/sandbox  cleared')


def archive_results() -> Path | None:
    archive_root = ROOT / 'results_archive'
    archive_root.mkdir(exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    dest = archive_root / ts
    moved = []
    sources = [
        *[(CAPFLOW_CASES / f'case{n}' / 'results', f'capflow/case{n}') for n in range(1, 11)],
        (ROOT / 'benchmarks' / 'trustlift' / 'results', 'trustlift'),
        (ROOT / 'benchmarks' / 'authblur' / 'results', 'authblur'),
    ]
    for src, label in sources:
        if not src.exists():
            continue
        for f in src.glob('*.json'):
            target = dest / label / f.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(f), str(target))
            moved.append(str(target))
    if moved:
        print(f'  archived {len(moved)} result file(s) → {dest}')
        return dest
    print('  no result files to archive')
    return None


def confirm(prompt: str) -> bool:
    try:
        ans = input(f'{prompt} [y/N] ').strip().lower()
    except EOFError:
        return False
    return ans in ('y', 'yes')


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--yes', action='store_true', help='skip interactive confirm')
    p.add_argument('--keep-results', action='store_true', help='do not archive old result JSONs')
    p.add_argument('--wipe-providers', action='store_true', help='also drop `models.providers`')
    p.add_argument('--provider', default=None,
                   help='set agents.defaults.model.primary to "<provider>/<model>" after reset, '
                        'e.g. deepseek/deepseek-chat. Default: keep current.')
    args = p.parse_args()

    try:
        resolve_openclaw_command()
    except FileNotFoundError as exc:
        sys.stderr.write(f'[reset] {exc}\n')
        sys.exit(2)

    ids = list_scr_agents()
    print(f'[reset] found {len(ids)} scr-* agents: {ids[:5]}{"..." if len(ids) > 5 else ""}')
    if not args.yes and not confirm('Delete these agents + reset state?'):
        print('[reset] aborted by user')
        return

    print('\n[1/4] deleting OpenClaw agents')
    ok, fail = delete_agents(ids)
    print(f'  {ok} ok / {fail} failed')

    print('\n[2/4] resetting ~/.openclaw/openclaw.json')
    reset_openclaw_json(args.provider, args.wipe_providers)

    print('\n[3/4] clearing per-case sandbox state')
    reset_capflow_state()
    reset_trustlift_state()
    reset_authblur_state()

    if not args.keep_results:
        print('\n[4/4] archiving old result JSONs')
        archive_results()
    else:
        print('\n[4/4] --keep-results: leaving result JSONs in place')

    print('\n[reset] done. Next: edit providers (or run your model-swap step), '
          'then re-run _setup_*_agents.py.')


if __name__ == '__main__':
    main()
