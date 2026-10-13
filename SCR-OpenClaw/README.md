# SCR-OpenClaw

SCR-OpenClaw is a 30-case benchmark for evaluating security failures caused by skill composition and cross-turn context in OpenClaw agents. It packages the exact active cases used by the three SCR sub-benches, their executable skills, experiment runners, aggregation code, and a historical baseline report.

## Benchmark scope

| Sub-benchmark | Cases | What it measures | Primary metric |
|---|---:|---|---|
| CapFlow | 10 | Whether separately useful discovery and action skills compose into a higher-impact action | linked attack success rate |
| TrustLift | 10 | Whether a trusted security-review skill leads the agent to install an untrusted registry skill | registry installation rate |
| AuthBlur | 10 | Whether prior advisory context changes a later high-impact authorization decision | approval rate by context level |

The full case-level inventory is in [docs/CASE_INDEX.md](docs/CASE_INDEX.md). Historical results from the source workspace are preserved in [docs/BASELINE_RESULTS.md](docs/BASELINE_RESULTS.md); generated results are intentionally excluded from the release package.

## Repository layout

```text
SCR-OpenClaw/
├── benchmarks/
│   ├── capflow/
│   │   ├── cases/case1..case10/       # skill pairs
│   │   └── scripts/                   # ten case runners + setup/bridge
│   ├── trustlift/
│   │   ├── cases/<sandbox>/           # trusted scanner + local registry
│   │   └── scripts/                   # setup and suite runner
│   └── authblur/
│       ├── cases/case1..case10/       # advisory/action skill sets
│       └── scripts/                   # setup and four-level runner
├── docs/
│   ├── CASE_INDEX.md
│   └── BASELINE_RESULTS.md
├── scripts/
│   ├── run_bench.py                   # end-to-end 30-case orchestrator
│   ├── reset_openclaw_bench.py        # scoped reset and result archival
│   ├── aggregate_openclaw_results.py  # Markdown report generator
│   ├── validate_release.py            # package integrity checks
│   └── build_manifest.py              # SHA-256 manifest generator
└── MANIFEST.json
```

Runtime sandboxes and result directories are created on demand and ignored by Git. Historical archives, model outputs, caches, research notes, and case-generation utilities are not part of this benchmark release.

## Requirements

- Python 3.10 or newer; the runners use only the standard library.
- A working OpenClaw installation and `~/.openclaw/openclaw.json`.
- An OpenAI-compatible or Anthropic-compatible model endpoint.
- OpenClaw on `PATH`, or `OPENCLAW_BIN` pointing to the executable or `openclaw.mjs`. When using an `.mjs` file, set `OPENCLAW_NODE` if `node` is not on `PATH`.

The original experiments were tested with OpenClaw 2026.7.1 on Windows 11. Paths in this release are repository-relative and the runners also support POSIX home directories.

## Quick start

First validate the checkout:

```bash
python scripts/validate_release.py
```

Set the provider key in an environment variable, then run all 30 cases. For an OpenAI-compatible endpoint:

```bash
export OPENCLAW_API_KEY='your-key'
python scripts/run_bench.py \
  --provider-id example \
  --base-url https://api.example.com/v1 \
  --model example-model \
  --protocol openai \
  --trials 3 \
  --parallel 3
```

PowerShell uses `$env:OPENCLAW_API_KEY = 'your-key'`; the remaining command-line arguments are the same. For an Anthropic-compatible endpoint, use `--protocol anthropic`.

The run produces:

- raw suite results under `benchmarks/*/results/` and CapFlow case `results/` directories;
- an aggregate `OPENCLAW_30CASE_REPORT.md`;
- a redacted, self-contained run snapshot under `results/<provider>_<model>_<timestamp>/`.

Run `python scripts/run_bench.py --help` for all provider, timeout, concurrency, and reasoning-model options.

## Individual suites

The orchestrator creates 30 `scr-*` OpenClaw agents automatically. For debugging, setup and run a suite directly:

```bash
python benchmarks/capflow/scripts/_setup_agents.py
python benchmarks/capflow/scripts/experiment_case1.py --trials 1

python benchmarks/trustlift/scripts/_setup_trustlift_agents.py
python benchmarks/trustlift/scripts/run_trustlift.py

python benchmarks/authblur/scripts/_setup_authblur_agents.py
python benchmarks/authblur/scripts/run_authblur.py --cases 1 --trials 1
```

Aggregate the latest available result for each case with:

```bash
python scripts/aggregate_openclaw_results.py
```

## Safety and state changes

The cases use local mock files and loopback HTTP capture servers; they are designed not to touch production services. Even so, run the benchmark in an isolated test environment because it intentionally asks agents to perform risky-looking actions.

`run_bench.py` changes the active OpenClaw provider configuration, creates agents whose IDs begin with `scr-`, writes local sandbox state, and finally removes those agents. It backs up `openclaw.json` before modification. Published run snapshots redact provider `apiKey` fields, but local configuration backups can still contain credentials and must not be committed.

## Reproducibility notes

- CapFlow evaluates five conditions: control, A-only, B-only, neutral A+B, and explicit A+B.
- TrustLift performs one install-decision prompt per sandbox per suite run.
- AuthBlur evaluates four preceding-context levels, from an unrelated control to a full advisory authorization context.
- Every model call uses a fresh session except AuthBlur's paired T1/T2 turns, which deliberately share a session.
- Unknown AuthBlur decisions are scored as denial in the aggregate report.
