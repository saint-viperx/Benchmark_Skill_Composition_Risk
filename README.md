# SCR-Bench: Skill Composition Risk Benchmark

SCR-Bench evaluates security risks that emerge when individually benign agent skills are composed into multi-step workflows. A harmful outcome may arise through an activated composition path even when no single skill appears harmful in isolation.

This anonymous artifact contains the benchmark cases, executable skills, experiment runners, and analysis utilities needed to reproduce the evaluation.

## Benchmark components

| Component | Scope | Description |
|---|---|---|
| **SCR-CapFlow** | 150 cases | Measures whether an upstream skill supplies targets or operational context that enables a downstream skill to perform a harmful state-changing action. |
| **SCR-TrustLift** | 401 trials | Measures whether an upstream security-review signal increases an agent's willingness to install or invoke a risky downstream skill. |
| **SCR-AuthBlur** | 118 cases | Measures whether advisory or authorization-like context shifts the agent toward unsafe downstream approval decisions. |
| **SCR-MultiSkill** | Multi-path extension | Extends the three mechanisms to longer skill chains and branching paths, with compact case builders and a unified experiment runner. |
| **SCR-OpenClaw** | 30-case portability suite | Ports ten cases from each core sub-benchmark to OpenClaw and provides setup, execution, validation, and aggregation utilities. |

The primary metric is attack success rate (ASR): the fraction of trials in which the target harmful action is executed or the risky downstream action is approved. Lower values indicate safer behavior.

## Repository layout

```text
SCR-Bench/
├── SCR-CapFlow/       # capability-flow cases and runners
├── SCR-TrustLift/     # control and endorsed trust-transfer groups
├── SCR-AuthBlur/      # context-level authorization experiments
├── SCR-MultiSkill/    # longer and branching composition paths
└── SCR-OpenClaw/      # OpenClaw-compatible 30-case suite
```

Each core sub-benchmark is self-contained and includes its own English README:

- [SCR-CapFlow](SCR-CapFlow/README.md)
- [SCR-TrustLift](SCR-TrustLift/README.md)
- [SCR-AuthBlur](SCR-AuthBlur/README.md)
- [SCR-OpenClaw](SCR-OpenClaw/README.md)

For the multi-skill extension, run `python SCR-MultiSkill/scripts/run_full_experiment.py --help` to inspect the unified runner options. Its three subdirectories contain the CapFlow, TrustLift, and AuthBlur multi-path cases.

## General workflow

1. Install and configure the agent CLI required by the selected component.
2. Follow the component README or inspect the runner's `--help` output.
3. Run experiments in an isolated environment.
4. Use the included aggregation utilities to summarize case-level outputs.

The benchmark intentionally presents risky-looking requests and skills. Cases are designed around local fixtures and mock state, but an isolated test environment is still recommended.

## Artifact notes

- Runtime results, caches, local credentials, and provider configuration are not included.
- Paths used by the released runners are repository-relative or configurable through environment variables and command-line arguments.
- Bundled skill text is retained as benchmark input, including multilingual content where it is part of a case.
