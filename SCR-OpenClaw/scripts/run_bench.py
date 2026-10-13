"""End-to-end orchestrator: run the SCR 30-case bench against any
OpenAI- or Anthropic-compatible provider, snapshot the entire runtime
+ traces, then clean.

Pipeline (each step depends on the previous):
  1. Preflight ping — verify base_url + api_key + model with a 1-turn call.
  2. reset_openclaw_bench.py --yes (clean agents / extraDirs / sandboxes).
  3. Write new `models.providers.<id>` + `agents.defaults.model.primary` into
     `~/.openclaw/openclaw.json` from CLI args.
  4. Rebuild 30 `scr-*` agents via the three _setup_*_agents.py scripts.
  5. Run CapFlow per-case parallel (10 subprocesses, --parallel workers).
  6. Run TrustLift sequential (1 subprocess for all 10 sandboxes).
  7. Run AuthBlur per-case parallel (10 subprocesses via --cases N).
  8. aggregate_openclaw_results.py — generate the markdown report.
  9. Snapshot openclaw.json + every result json + every sandbox dir +
     per-case logs into results/<run_id>/.
 10. Final reset — wipe agents / extraDirs / sandboxes again.

Examples:

  # DeepSeek-V3 via OpenAI-compatible API
  python run_bench.py \\
      --provider-id deepseek \\
      --base-url https://api.deepseek.com \\
      --model deepseek-chat \\
      --protocol openai \\
      --trials 3 --timeout 240 --parallel 4

  # Anthropic-protocol clone (MiniMax, GLM-Claude-style, etc.)
  python run_bench.py \\
      --provider-id custom-api-myhost-com \\
      --base-url https://api.example.com/anthropic \\
      --model my-model-name \\
      --protocol anthropic \\
      --trials 3 --timeout 240

Set OPENCLAW_API_KEY in the environment before running either example.

Required env / paths (auto-detected, override if needed):
  OPENCLAW_BIN   OpenClaw executable or openclaw.mjs (default: find `openclaw` on PATH)
  OPENCLAW_NODE  node executable, only needed when OPENCLAW_BIN points to .mjs
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.parse
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OPENCLAW_HOME = Path(os.environ.get('OPENCLAW_HOME', Path.home() / '.openclaw'))
OPENCLAW_JSON = OPENCLAW_HOME / 'openclaw.json'


def resolve_openclaw_command() -> list[str]:
    """Resolve either an OpenClaw executable or a node + openclaw.mjs pair."""
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

RESULTS_ROOT = ROOT / 'results'

CAPFLOW_SCRIPT_DIR = ROOT / 'benchmarks' / 'capflow' / 'scripts'
TRUSTLIFT_SCRIPT_DIR = ROOT / 'benchmarks' / 'trustlift' / 'scripts'
AUTHBLUR_SCRIPT_DIR = ROOT / 'benchmarks' / 'authblur' / 'scripts'

# TrustLift sandboxes must match _setup_trustlift_agents.py exactly.
TRUSTLIFT_SANDBOXES = [
    'acorns', 'adobesign', 'agent-analytics', 'agentic-jujutsu',
    'agentic-jujutsu (2)', 'ai-truthfulness-enforcer', 'american-airlines',
    'amtrak', 'analytics', 'analytics (1)',
]

PROTOCOL_API_TYPE = {
    'openai': 'openai-completions',
    'anthropic': 'anthropic-messages',
}

CAPFLOW_CASES = ROOT / 'benchmarks' / 'capflow' / 'cases'
TRUSTLIFT_DIR = ROOT / 'benchmarks' / 'trustlift' / 'cases'
AUTHBLUR_CASES = ROOT / 'benchmarks' / 'authblur' / 'cases'


# --------------------------- helpers ---------------------------

def call_oc(args: list[str], timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(
        [*resolve_openclaw_command(), *args],
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace',
        timeout=timeout,
    )


def derive_provider_id(base_url: str, override: str | None) -> str:
    if override:
        return override
    host = urllib.parse.urlparse(base_url).hostname or 'custom'
    stem = host.lower()
    if stem.startswith('api.'):
        stem = stem[4:]
    for tld in ('.com', '.cn', '.org', '.net', '.io', '.dev', '.ai', '.xyz', '.cc'):
        if stem.endswith(tld):
            stem = stem[: -len(tld)]
            break
    return stem.replace('.', '-').replace('_', '-') or 'custom'


def normalize_base_url(url: str, protocol: str) -> str:
    """Strip only the chat-completions tail for OpenAI providers.

    OpenClaw's openai-completions adapter appends `/chat/completions` to
    `baseUrl` automatically. If a user gives us the FULL endpoint URL like
    `https://yunwu.ai/v1/chat/completions`, the adapter would otherwise hit
    `…/chat/completions/chat/completions` → 404. So we strip the trailing
    `/chat/completions` only — keeping `/v1` (or whatever API path-prefix
    the gateway uses). Many gateways (yunwu.ai, openrouter, etc.) only
    serve the OpenAI protocol under `/v1/...`; stripping `/v1` sends
    requests to the bare host which returns an HTML nginx 404 page.
    """
    url = url.strip().rstrip('/')
    if protocol != 'openai':
        return url
    if url.endswith('/chat/completions'):
        return url[: -len('/chat/completions')]
    return url


def write_openclaw_json(provider_id: str, base_url: str, model: str,
                        api_key: str, protocol: str,
                        context_window: int, max_tokens: int,
                        reasoning: bool) -> None:
    if not OPENCLAW_JSON.exists():
        raise FileNotFoundError(f'{OPENCLAW_JSON} missing')
    # Backup first — never destroy the user's prior config.
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    bak = OPENCLAW_HOME / f'openclaw.json.bak.{ts}'
    shutil.copy2(OPENCLAW_JSON, bak)

    cfg = json.loads(OPENCLAW_JSON.read_text(encoding='utf-8'))

    # models.providers
    providers = cfg.setdefault('models', {}).setdefault('providers', {})
    providers[provider_id] = {
        'baseUrl': normalize_base_url(base_url, protocol),
        'api': PROTOCOL_API_TYPE[protocol],
        'apiKey': api_key,
        'models': [
            {
                'id': model,
                'name': f'{model} ({provider_id})',
                'contextWindow': context_window,
                'maxTokens': max_tokens,
                'input': ['text'],
                'cost': {'input': 0, 'output': 0, 'cacheRead': 0, 'cacheWrite': 0},
                'reasoning': reasoning,
            }
        ],
    }

    # agents.defaults.model.primary
    primary = f'{provider_id}/{model}'
    defaults = cfg.setdefault('agents', {}).setdefault('defaults', {})
    defaults['model'] = {'primary': primary}
    defaults['models'] = {primary: {}}

    OPENCLAW_JSON.write_text(json.dumps(cfg, indent=2), encoding='utf-8')
    print(f'[config] provider={provider_id} api={PROTOCOL_API_TYPE[protocol]} model={model}')
    print(f'[config] defaults.model.primary = {primary}')
    print(f'[config] backup → {bak}')


def preflight_ping(timeout: int = 60) -> bool:
    print('\n[preflight] pinging provider via agent=main …')
    try:
        r = call_oc([
            'agent', '--local', '--agent', 'main',
            '--message', 'Reply with exactly the single word: PONG',
        ], timeout=timeout)
    except subprocess.TimeoutExpired:
        print('[preflight] TIMEOUT — provider did not respond in time.')
        return False
    if r.returncode != 0:
        err = (r.stderr or '').strip()[:300]
        try:
            print(f'[preflight] FAIL rc={r.returncode} stderr={err}')
        except UnicodeEncodeError:
            print(f'[preflight] FAIL rc={r.returncode} stderr={err.encode("ascii", "replace").decode()}')
        # Don't hard-fail: PowerShell profile noise and other recoverable
        # errors trip rc=1.  The real experiment will surface a true outage
        # via per-case failures; preflight exists only to give a faster
        # signal on misconfigured providers.
        print('[preflight] continuing despite rc!=0')
        return True
    out = (r.stdout or '').upper()
    if 'PONG' not in out and 'OK' not in out:
        tail = (r.stdout or '')[-300:]
        try:
            print(f'[preflight] WARN: unexpected reply (no PONG/OK). stdout_tail={tail!r}')
        except UnicodeEncodeError:
            print(f'[preflight] WARN: unexpected reply (no PONG/OK). stdout_tail={tail.encode("ascii", "replace").decode()!r}')
        # Don't fail on missing token — providers format replies differently.
    print(f'[preflight] OK ({len(r.stdout)} chars)')
    return True


def run_subprocess(cmd: list[str], cwd: Path, log_path: Path,
                   env: dict | None = None) -> tuple[int, float]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    env_full = os.environ.copy()
    if env:
        env_full.update(env)
    print(f'  $ {" ".join(cmd)}  → {log_path.name}', flush=True)
    with open(log_path, 'w', encoding='utf-8') as logf:
        p = subprocess.Popen(
            cmd, cwd=str(cwd),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding='utf-8', errors='replace',
            env=env_full,
        )
        assert p.stdout is not None
        for line in p.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
            logf.write(line)
            logf.flush()
        rc = p.wait()
    dur = time.time() - t0
    print(f'    → rc={rc} dur={dur:.1f}s', flush=True)
    return rc, dur


def parallel_invocations(jobs: list[dict], workers: int) -> list[dict]:
    """Each job dict: {cmd, cwd, log_path, env, label}. Returns list with 'rc','dur' added."""
    results = [None] * len(jobs)
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        fut_to_idx = {}
        for i, j in enumerate(jobs):
            fut = pool.submit(
                run_subprocess, j['cmd'], j['cwd'], j['log_path'], j.get('env'),
            )
            fut_to_idx[fut] = i
        for fut in concurrent.futures.as_completed(fut_to_idx):
            i = fut_to_idx[fut]
            try:
                rc, dur = fut.result()
                results[i] = {**jobs[i], 'rc': rc, 'dur': dur}
            except Exception as exc:  # noqa: BLE001
                print(f'  [{jobs[i].get("label", i)}] exception: {exc}', flush=True)
                results[i] = {**jobs[i], 'rc': -1, 'dur': 0.0, 'error': str(exc)}
    return [r for r in results if r is not None]


# --------------------------- steps ---------------------------

def step_reset(keep_results: bool) -> None:
    print('\n[step 1/8] reset_openclaw_bench.py --yes')
    cmd = [sys.executable, str(ROOT / 'scripts' / 'reset_openclaw_bench.py'), '--yes']
    if keep_results:
        cmd.append('--keep-results')
    r = subprocess.run(cmd, cwd=str(ROOT))
    if r.returncode != 0:
        sys.exit(f'reset failed (rc={r.returncode})')


def step_setup_agents() -> None:
    print('\n[step 2/8] rebuild 30 scr-* agents')
    for label, path in [
        ('CapFlow', CAPFLOW_SCRIPT_DIR / '_setup_agents.py'),
        ('TrustLift', TRUSTLIFT_SCRIPT_DIR / '_setup_trustlift_agents.py'),
        ('AuthBlur', AUTHBLUR_SCRIPT_DIR / '_setup_authblur_agents.py'),
    ]:
        print(f'  → {label}: {path.name}')
        r = subprocess.run([sys.executable, str(path)], cwd=str(path.parent))
        if r.returncode != 0:
            sys.exit(f'{label} setup failed (rc={r.returncode})')


def step_capflow(args, run_dir: Path, log_dir: Path) -> list[dict]:
    print('\n[step 3/8] SCR-CapFlow per-case parallel')
    py = sys.executable
    env = {'OPENCLAW_TIMEOUT': str(args.timeout)}
    jobs = []
    for n in range(1, 11):
        jobs.append({
            'label': f'capflow_case{n}',
            'cmd': [py, str(CAPFLOW_SCRIPT_DIR / f'experiment_case{n}.py'),
                    '--trials', str(args.trials)],
            'cwd': CAPFLOW_SCRIPT_DIR,
            'log_path': log_dir / 'capflow' / f'case{n}.log',
            'env': env,
        })
    return parallel_invocations(jobs, args.parallel)


def step_trustlift(args, run_dir: Path, log_dir: Path) -> list[dict]:
    print('\n[step 4/8] SCR-TrustLift (sequential, 10 sandboxes)')
    py = sys.executable
    env = {'OPENCLAW_TIMEOUT': str(args.timeout)}
    rc, dur = run_subprocess(
        [py, str(TRUSTLIFT_SCRIPT_DIR / 'run_trustlift.py')],
        TRUSTLIFT_SCRIPT_DIR, log_dir / 'trustlift' / 'run.log', env,
    )
    return [{'label': 'trustlift', 'cmd': ['run_trustlift.py'], 'cwd': str(TRUSTLIFT_SCRIPT_DIR),
             'log_path': str(log_dir / 'trustlift' / 'run.log'), 'env': env, 'rc': rc, 'dur': dur}]


def step_authblur(args, run_dir: Path, log_dir: Path) -> list[dict]:
    print('\n[step 5/8] SCR-AuthBlur per-case parallel')
    py = sys.executable
    env = {'OPENCLAW_TIMEOUT': str(args.timeout)}
    jobs = []
    for n in range(1, 11):
        jobs.append({
            'label': f'authblur_case{n}',
            'cmd': [py, str(AUTHBLUR_SCRIPT_DIR / 'run_authblur.py'),
                    '--cases', str(n), '--trials', str(args.trials)],
            'cwd': AUTHBLUR_SCRIPT_DIR,
            'log_path': log_dir / 'authblur' / f'case{n}.log',
            'env': env,
        })
    return parallel_invocations(jobs, args.parallel)


def step_aggregate(args) -> tuple[int, Path, str]:
    print('\n[step 6/8] aggregate_openclaw_results.py')
    r = subprocess.run(
        [sys.executable, str(ROOT / 'scripts' / 'aggregate_openclaw_results.py')],
        cwd=str(ROOT), capture_output=True, text=True, encoding='utf-8', errors='replace',
    )
    chunk = r.stdout[-2000:] if r.returncode == 0 else r.stderr[-2000:]
    try:
        print(chunk)
    except UnicodeEncodeError:
        print(chunk.encode('ascii', 'replace').decode())
    report = ROOT / 'OPENCLAW_30CASE_REPORT.md'
    return r.returncode, report, r.stdout


def step_snapshot(run_id: str, args, step_durations: dict[str, float]) -> Path:
    """Copy openclaw.json, result JSONs, sandbox dirs, logs into results/<run_id>/."""
    print(f'\n[step 7/8] snapshot → results/{run_id}/')
    dest = RESULTS_ROOT / run_id
    dest.mkdir(parents=True, exist_ok=True)

    # Save a reproducibility snapshot without publishing provider credentials.
    if OPENCLAW_JSON.exists():
        config_snapshot = json.loads(OPENCLAW_JSON.read_text(encoding='utf-8'))
        for provider in config_snapshot.get('models', {}).get('providers', {}).values():
            if isinstance(provider, dict) and 'apiKey' in provider:
                provider['apiKey'] = '<redacted>'
        (dest / 'openclaw.json').write_text(
            json.dumps(config_snapshot, indent=2, ensure_ascii=False), encoding='utf-8',
        )

    # CapFlow results: experiment_caseN.py writes to cases/caseN/results/.
    # Older runs may have written to /tmp/openclaw_caseN*.json — search both.
    cf_dir = dest / 'capflow_results'
    cf_dir.mkdir(exist_ok=True)
    cf_root = CAPFLOW_CASES
    tmp_a = Path(os.environ.get('TEMP', '/tmp'))
    tmp_b = Path('/tmp')
    for case in range(1, 11):
        copied = False
        results_subdir = cf_root / f'case{case}' / 'results'
        if results_subdir.exists():
            latest = max(results_subdir.glob(f'experiment_case{case}_*.json'),
                         default=None, key=lambda p: p.stat().st_mtime)
            if latest is not None:
                shutil.copy2(latest, cf_dir / f'case{case}.json')
                copied = True
        if not copied:
            for src_dir in (tmp_a, tmp_b):
                for suffix in (f'openclaw_case{case}_full.json', f'openclaw_case{case}.json'):
                    src = src_dir / suffix
                    if src.exists():
                        shutil.copy2(src, cf_dir / f'case{case}.json')
                        copied = True
                        break
                if copied:
                    break

    # TrustLift results
    tl_dir = dest / 'trustlift_results'
    tl_dir.mkdir(exist_ok=True)
    tl_src = ROOT / 'benchmarks' / 'trustlift' / 'results'
    if tl_src.exists():
        for f in tl_src.glob('trustlift_openclaw_*.json'):
            shutil.copy2(f, tl_dir / f.name)

    # AuthBlur results — copy per-case files plus any legacy aggregate file
    ab_dir = dest / 'authblur_results'
    ab_dir.mkdir(exist_ok=True)
    ab_src = ROOT / 'benchmarks' / 'authblur' / 'results'
    if ab_src.exists():
        for f in ab_src.glob('authblur_openclaw_*.json'):
            shutil.copy2(f, ab_dir / f.name)

    # Aggregate report
    rep = ROOT / 'OPENCLAW_30CASE_REPORT.md'
    if rep.exists():
        shutil.copy2(rep, dest / 'aggregate_report.md')

    # Sandbox snapshots — what the LLM actually wrote into each workspace
    sb_root = dest / 'sandboxes_snapshot'
    sb_root.mkdir(exist_ok=True)
    if CAPFLOW_CASES.exists():
        for c in sorted(CAPFLOW_CASES.glob('case*')):
            tgt = sb_root / 'capflow' / c.name
            if (c / 'sandbox').exists():
                shutil.copytree(c / 'sandbox', tgt, dirs_exist_ok=True)
    if TRUSTLIFT_DIR.exists():
        for sb in TRUSTLIFT_SANDBOXES:
            tgt = sb_root / 'trustlift' / sb
            src = TRUSTLIFT_DIR / sb / '.claude' / 'skills'
            if src.exists():
                shutil.copytree(src, tgt, dirs_exist_ok=True)
    if AUTHBLUR_CASES.exists():
        for c in sorted(AUTHBLUR_CASES.glob('case*')):
            tgt = sb_root / 'authblur' / c.name
            if (c / 'sandbox').exists():
                shutil.copytree(c / 'sandbox', tgt, dirs_exist_ok=True)

    # Run metadata
    meta = {
        'run_id': run_id,
        'timestamp': datetime.now().isoformat(),
        'provider_id': args.provider_id,
        'base_url': args.base_url,
        'model': args.model,
        'protocol': args.protocol,
        'api_type': PROTOCOL_API_TYPE[args.protocol],
        'trials': args.trials,
        'timeout': args.timeout,
        'parallel': args.parallel,
        'context_window': args.context_window,
        'max_tokens': args.max_tokens,
        'reasoning': args.reasoning,
        'step_durations_s': step_durations,
        'openclaw_command': resolve_openclaw_command(),
    }
    (dest / 'run_metadata.json').write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding='utf-8',
    )
    print(f'  → {dest}')
    return dest


def step_final_reset() -> None:
    print('\n[step 8/8] final reset')
    r = subprocess.run(
        [sys.executable, str(ROOT / 'scripts' / 'reset_openclaw_bench.py'), '--yes', '--keep-results'],
        cwd=str(ROOT),
    )
    if r.returncode != 0:
        print(f'  [warn] final reset rc={r.returncode}', flush=True)


# --------------------------- main ---------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument('--base-url', required=True,
                   help='API base URL, e.g. https://api.deepseek.com or https://api.minimaxi.com/anthropic')
    p.add_argument('--model', required=True,
                   help='Model id, e.g. deepseek-chat, deepseek-reasoner, MiniMax-M3')
    p.add_argument('--api-key', default=None,
                   help='API key. Prefer OPENCLAW_API_KEY to avoid shell-history exposure.')
    p.add_argument('--api-key-env', default='OPENCLAW_API_KEY',
                   help='environment variable used when --api-key is omitted')
    p.add_argument('--protocol', required=True, choices=['openai', 'anthropic'],
                   help='openai → openai-completions, anthropic → anthropic-messages')
    p.add_argument('--provider-id', default=None,
                   help='Override OpenClaw provider id (default: derive from base-url)')
    p.add_argument('--context-window', type=int, default=64000)
    p.add_argument('--max-tokens', type=int, default=4096)
    p.add_argument('--reasoning', action='store_true',
                   help='Mark provider model as reasoning (e.g. deepseek-reasoner)')
    p.add_argument('--trials', type=int, default=3, help='Trials per (case, condition/level)')
    p.add_argument('--timeout', type=int, default=240,
                   help='Per-call OpenClaw timeout in seconds (env OPENCLAW_TIMEOUT)')
    p.add_argument('--parallel', type=int, default=3,
                   help='Max concurrent subprocesses during CapFlow/AuthBlur runs')
    p.add_argument('--skip-preflight', action='store_true',
                   help='Skip the connectivity ping (use when main agent is broken)')
    p.add_argument('--keep-prior-results', action='store_true',
                   help='Don\'t archive prior results in the start-reset')
    return p.parse_args()


def main() -> None:
    args = parse_args()
    args.api_key = args.api_key or os.environ.get(args.api_key_env)
    if not args.api_key:
        raise SystemExit(
            f'API key missing: set {args.api_key_env} or pass --api-key'
        )
    args.provider_id = derive_provider_id(args.base_url, args.provider_id)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    run_id = f'{args.provider_id}_{args.model}_{ts}'
    log_dir = RESULTS_ROOT / run_id / 'logs'
    log_dir.mkdir(parents=True, exist_ok=True)
    run_log = log_dir / 'orchestrator.log'
    # Tee orchestrator stdout to run.log as well.
    run_log_fh = open(run_log, 'w', encoding='utf-8')
    orig_stdout = sys.stdout

    class TeeStdout:
        def write(self, s):
            orig_stdout.write(s)
            run_log_fh.write(s)
            return len(s)
        def flush(self):
            orig_stdout.flush()
            run_log_fh.flush()
    sys.stdout = TeeStdout()

    print(f'====== run_bench.py @ {ts} ======')
    print(f'run_id           = {run_id}')
    print(f'base_url         = {args.base_url}')
    print(f'model            = {args.model}')
    print(f'api_key          = <redacted len={len(args.api_key)}>')
    print(f'protocol         = {args.protocol} → {PROTOCOL_API_TYPE[args.protocol]}')
    print(f'provider_id      = {args.provider_id}')
    print(f'trials           = {args.trials}')
    print(f'timeout          = {args.timeout}s per call')
    print(f'parallel         = {args.parallel} workers')
    print(f'context_window   = {args.context_window}')
    print(f'max_tokens       = {args.max_tokens}')
    print(f'reasoning        = {args.reasoning}')

    t_start = time.time()

    step_durations: dict[str, float] = {}

    # 1. Start reset
    t = time.time()
    step_reset(args.keep_prior_results)
    step_durations['reset_start'] = time.time() - t

    # 2. Write openclaw.json
    t = time.time()
    write_openclaw_json(
        provider_id=args.provider_id,
        base_url=args.base_url,
        model=args.model,
        api_key=args.api_key,
        protocol=args.protocol,
        context_window=args.context_window,
        max_tokens=args.max_tokens,
        reasoning=args.reasoning,
    )
    step_durations['write_config'] = time.time() - t

    if not args.skip_preflight and not preflight_ping(args.timeout + 30):
        sys.exit('preflight ping failed — aborting')

    # 3. Build agents
    t = time.time()
    step_setup_agents()
    step_durations['setup_agents'] = time.time() - t

    # 4. CapFlow
    t = time.time()
    step_capflow(args, RESULTS_ROOT / run_id, log_dir)
    step_durations['capflow'] = time.time() - t

    # 5. TrustLift (sequential)
    t = time.time()
    step_trustlift(args, RESULTS_ROOT / run_id, log_dir)
    step_durations['trustlift'] = time.time() - t

    # 6. AuthBlur
    t = time.time()
    step_authblur(args, RESULTS_ROOT / run_id, log_dir)
    step_durations['authblur'] = time.time() - t

    # 7. Aggregate
    t = time.time()
    rc, rep_path, _ = step_aggregate(args)
    step_durations['aggregate'] = time.time() - t
    if rc != 0:
        print(f'[warn] aggregate rc={rc}', flush=True)

    # 8. Snapshot
    t = time.time()
    run_dir = step_snapshot(run_id, args, step_durations)
    step_durations['snapshot'] = time.time() - t

    # 9. Final reset
    t = time.time()
    step_final_reset()
    step_durations['reset_end'] = time.time() - t

    total = time.time() - t_start
    print(f'\n====== DONE in {total:.1f}s ======')
    print(f'run folder: {run_dir}')
    print(f'aggregate:  {rep_path}')

    sys.stdout = orig_stdout
    run_log_fh.close()


if __name__ == '__main__':
    main()
