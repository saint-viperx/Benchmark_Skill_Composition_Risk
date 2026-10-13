#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Automated SCR-MultiSkill experiment orchestrator.

The runner checks and resets runtime state, builds the three sub-benchmarks,
runs their experiments, stores a reproducibility snapshot, and restores the
benchmark fixtures to a clean state. Step logs are written under ``run_logs``.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Project and sub-benchmark paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CAPFLOW_ROOT = PROJECT_ROOT / "SCR-CapFlow-MultiPath"
TRUSTLIFT_ROOT = PROJECT_ROOT / "SCR-TrustLift-MultiPath"
AUTHBLUR_ROOT = PROJECT_ROOT / "SCR-AuthBlur-MultiPath"
SNAPSHOTS_ROOT = PROJECT_ROOT / "snapshots"

CLAUDE_HOME = Path(os.environ.get("USERPROFILE") or os.path.expanduser("~")) / ".claude"
_project_cache_key = "".join("-" if c in ":\\/" else c for c in str(PROJECT_ROOT.resolve()))
PROJECT_SESSION_DIR = Path(
    os.environ.get("SCR_CLAUDE_PROJECT_SESSION_DIR")
    or CLAUDE_HOME / "projects" / _project_cache_key
)
GLOBAL_SESSIONS_DIR = CLAUDE_HOME / "sessions"
PROJECT_SETTINGS = PROJECT_ROOT / ".claude" / "settings.json"
GLOBAL_SETTINGS = CLAUDE_HOME / "settings.json"


# Build-time fixtures are preserved; runtime artifacts are removed.
CAPFLOW_SANDBOX_INVARIANT_FILES = {"inventory.json"}
AUTHBLUR_SANDBOX_INVARIANT_FILES = {"test.txt", "decision_target.json", "policy_metadata.json"}
CAPFLOW_SANDBOX_DIRS_TO_WIPE = {"results"}
AUTHBLUR_SANDBOX_DIRS_TO_WIPE = {"results"}
CAPFLOW_PER_CASE_FILES_TO_WIPE = {".claude/skills/*"}  # rebuilt by build_cases
TRUSTLIFT_PER_SANDBOX_DIRS_TO_WIPE = {".claude/skills"}
TRUSTLIFT_RESULTS_FILES_TO_KEEP = set()


@dataclass
class StepResult:
    name: str
    ok: bool
    started_at: float
    finished_at: float
    stdout_tail: str = ""
    stderr_tail: str = ""
    message: str = ""

    @property
    def duration_s(self) -> float:
        return self.finished_at - self.started_at


@dataclass
class CleanReport:
    """Structured output from ``check_clean``."""
    is_clean: bool
    findings: list[tuple[str, str]] = field(default_factory=list)
    """List of ``(region, description)`` pairs; empty means clean."""

    def add(self, region: str, desc: str) -> None:
        self.findings.append((region, desc))

    def render(self) -> str:
        if self.is_clean:
            return "CLEAN"
        lines = ["DIRTY:"]
        for region, desc in self.findings:
            lines.append(f"  [{region}] {desc}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Environment detection
# ---------------------------------------------------------------------------
def detect_model_name() -> str:
    """Read the model from project settings, then fall back to global settings."""
    for p in (PROJECT_SETTINGS, GLOBAL_SETTINGS):
        if not p.exists():
            continue
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        env = d.get("env", {}) or {}
        m = d.get("model") or env.get("ANTHROPIC_MODEL") or env.get("ANTHROPIC_DEFAULT_OPUS_MODEL")
        if m:
            return str(m)
    return "unknown-model"


def claude_cli_version() -> str:
    try:
        r = subprocess.run(
            ["claude", "--version"], capture_output=True, text=True, encoding="utf-8", timeout=10
        )
        return (r.stdout or r.stderr).strip()
    except Exception as exc:
        return f"claude not callable: {exc}"


# ---------------------------------------------------------------------------
# Clean check
# ---------------------------------------------------------------------------
def _list_files(p: Path) -> list[Path]:
    if not p.exists():
        return []
    return [c for c in p.iterdir()]


def _list_files_recursive(p: Path, max_n: int = 50) -> list[Path]:
    if not p.exists():
        return []
    out: list[Path] = []
    for c in p.rglob("*"):
        if c.is_file():
            out.append(c)
            if len(out) >= max_n:
                break
    return out


def check_clean() -> CleanReport:
    """Inspect five runtime regions and report every generated artifact.

    A region is dirty when case sandboxes or result directories contain
    non-invariant files, or when relevant agent session caches are non-empty.
    """
    r = CleanReport(is_clean=True)
    invariants = CAPFLOW_SANDBOX_INVARIANT_FILES | AUTHBLUR_SANDBOX_INVARIANT_FILES

    # 1) Per-case sandboxes: anything outside the invariant set is dirty.
    for label, root in (("capflow", CAPFLOW_ROOT), ("authblur", AUTHBLUR_ROOT)):
        cases_root = root / "cases"
        if not cases_root.exists():
            continue
        for case in sorted(cases_root.iterdir()):
            if not case.is_dir():
                continue
            sb = case / "sandbox"
            if not sb.exists():
                continue
            extras: list[str] = []
            for c in sb.iterdir():
                if c.name in invariants:
                    continue
                rel = c.relative_to(sb).as_posix()
                extras.append(rel)
            # Also inspect nested non-invariant files.
            for c in sb.rglob("*"):
                if c.is_dir():
                    continue
                if c.name in invariants:
                    continue
                rel = c.relative_to(sb).as_posix()
                if rel not in extras:
                    extras.append(rel)
            if extras:
                r.add(f"{label}-sandbox",
                      f"{case.name}/sandbox contains run artifacts: {sorted(set(extras))[:8]}")

    # 2) per-case results
    for label, root in (("capflow", CAPFLOW_ROOT), ("authblur", AUTHBLUR_ROOT)):
        rd = root / "cases"
        if not rd.exists():
            continue
        for case in sorted(rd.iterdir()):
            res = case / "results"
            if res.exists():
                files = [c.name for c in res.iterdir() if c.is_file()]
                if files:
                    r.add(f"{label}-results", f"{case.name}/results has {len(files)} file(s): {files[:5]}")

    # 3) per-case .claude/skills (CapFlow + AuthBlur)
    for label, root in (("capflow", CAPFLOW_ROOT), ("authblur", AUTHBLUR_ROOT)):
        for case in sorted((root / "cases").iterdir()):
            if not case.is_dir():
                continue
            sd = case / ".claude" / "skills"
            if sd.exists():
                skills = sorted(p.name for p in sd.iterdir() if p.is_dir())
                if skills:
                    r.add(f"{label}-skills", f"{case.name}/.claude/skills has {skills}")

    # 4) TrustLift per-sandbox .claude/skills + results/INST-*.stdout.txt
    tl_experiment = TRUSTLIFT_ROOT / "experiment"
    if tl_experiment.exists():
        for sb in sorted(tl_experiment.iterdir()):
            if not sb.is_dir():
                continue
            sd = sb / ".claude" / "skills"
            if sd.exists():
                skills = sorted(p.name for p in sd.iterdir() if p.is_dir())
                if skills:
                    r.add("trustlift-skills", f"{sb.name}/.claude/skills has {skills}")

    tl_results = TRUSTLIFT_ROOT / "results"
    if tl_results.exists():
        for sb in sorted(tl_results.iterdir()):
            if not sb.is_dir():
                continue
            outs = [c.name for c in sb.iterdir() if c.name.endswith(".stdout.txt")]
            if outs:
                r.add("trustlift-results", f"{sb.name}/ has {len(outs)} stdout files")

        # Top-level summary.*.json
        summaries = [c.name for c in tl_results.iterdir()
                     if c.is_file() and c.name.startswith("summary.")]
        if summaries:
            r.add("trustlift-results", f"top-level has summaries: {summaries}")

    # 5) Claude CLI global session cache
    if PROJECT_SESSION_DIR.exists():
        files = [c.name for c in PROJECT_SESSION_DIR.iterdir() if c.is_file()]
        non_mem = [f for f in files if not f.startswith("memory")]
        if non_mem:
            r.add("session-cache", f"{PROJECT_SESSION_DIR.name}/ has files: {non_mem[:5]}")

    if GLOBAL_SESSIONS_DIR.exists():
        js = [c.name for c in GLOBAL_SESSIONS_DIR.iterdir() if c.name.endswith(".json")]
        if js:
            r.add("sessions-global", f"sessions/ has {len(js)} json files (sample: {js[:3]})")

    if r.findings:
        r.is_clean = False
    return r


# ---------------------------------------------------------------------------
# Reset (clean by backup + delete)
# ---------------------------------------------------------------------------
def _remove(path: Path, backup_root: Optional[Path], backup_label: str) -> None:
    """Recursively remove path. If backup_root is not None, copy path into backup_root/backup_label first."""
    if backup_root is not None:
        target = backup_root / backup_label
        try:
            if path.is_dir():
                shutil.copytree(path, target, dirs_exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
        except Exception as exc:
            print(f"      [warn] backup of {path} failed: {exc}")
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    else:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
def reset_to_clean(snap_dir: Path, *, keep_backup: bool) -> None:
    """Optionally back up dirty regions, then restore a clean fixture state.

    When ``keep_backup`` is false, large runtime artifacts are removed without
    being retained in the pre-clean snapshot.
    """
    if keep_backup:
        backup_root = snap_dir / "pre_clean"
        backup_root.mkdir(parents=True, exist_ok=True)

    # 1) CapFlow per-case sandbox/results + .claude/skills
    capflow_invariants = CAPFLOW_SANDBOX_INVARIANT_FILES
    for case in sorted((CAPFLOW_ROOT / "cases").iterdir()):
        if not case.is_dir():
            continue
        sb = case / "sandbox"
        if sb.exists():
            for child in list(sb.iterdir()):
                if child.name in capflow_invariants:
                    continue
                _remove(child, backup_root if keep_backup else None,
                        f"capflow.{case.name}.{child.name}")

        rd = case / "results"
        if rd.exists():
            for child in list(rd.iterdir()):
                _remove(child, backup_root if keep_backup else None,
                        f"capflow.{child.name}")

        skills_dir = case / ".claude" / "skills"
        if skills_dir.exists():
            if keep_backup:
                shutil.copytree(skills_dir,
                                backup_root / f"capflow.{case.name}.skills",
                                dirs_exist_ok=True)
            shutil.rmtree(skills_dir)

    # 2) AuthBlur per-case sandbox/results + .claude/skills
    authblur_invariants = AUTHBLUR_SANDBOX_INVARIANT_FILES
    for case in sorted((AUTHBLUR_ROOT / "cases").iterdir()):
        if not case.is_dir():
            continue
        sb = case / "sandbox"
        if sb.exists():
            for child in list(sb.iterdir()):
                if child.name in authblur_invariants:
                    continue
                _remove(child, backup_root if keep_backup else None,
                        f"authblur.{case.name}.{child.name}")

        rd = case / "results"
        if rd.exists():
            for child in list(rd.iterdir()):
                _remove(child, backup_root if keep_backup else None,
                        f"authblur.{child.name}")

        skills_dir = case / ".claude" / "skills"
        if skills_dir.exists():
            if keep_backup:
                shutil.copytree(skills_dir,
                                backup_root / f"authblur.{case.name}.skills",
                                dirs_exist_ok=True)
            shutil.rmtree(skills_dir)

    # 3) TrustLift per-sandbox .claude/skills + all results/<INST>/*.stdout.txt
    tl_experiment = TRUSTLIFT_ROOT / "experiment"
    if tl_experiment.exists():
        for sb in sorted(tl_experiment.iterdir()):
            if not sb.is_dir():
                continue
            sd = sb / ".claude" / "skills"
            if sd.exists():
                if keep_backup:
                    shutil.copytree(sd, backup_root / f"trustlift.{sb.name}.skills",
                                    dirs_exist_ok=True)
                shutil.rmtree(sd)

    tl_results = TRUSTLIFT_ROOT / "results"
    if tl_results.exists():
        for sb in list(tl_results.iterdir()):
            if sb.is_dir():
                if keep_backup:
                    shutil.copytree(sb, backup_root / f"trustlift.results.{sb.name}",
                                    dirs_exist_ok=True)
                shutil.rmtree(sb)
            elif sb.is_file() and sb.name.startswith("summary."):
                if keep_backup:
                    shutil.copy2(sb, backup_root / f"trustlift.{sb.name}")
                sb.unlink()

    # 4) Claude global session cache — back up is impractical (50 MB+)
    if PROJECT_SESSION_DIR.exists():
        non_mem = [c for c in PROJECT_SESSION_DIR.iterdir()
                   if c.is_file() and not c.name.startswith("memory")]
        if non_mem:
            if keep_backup:
                backup_root.joinpath("session-cache").mkdir(parents=True, exist_ok=True)
                for c in non_mem:
                    try:
                        shutil.copy2(c, backup_root / "session-cache" / c.name)
                    except Exception:
                        pass
            for c in non_mem:
                try:
                    c.unlink()
                except Exception:
                    pass

    # 5) Global sessions/<id>.json — clean
    if GLOBAL_SESSIONS_DIR.exists():
        js = [c for c in GLOBAL_SESSIONS_DIR.iterdir() if c.name.endswith(".json")]
        if js:
            if keep_backup:
                backup_root.joinpath("sessions-global").mkdir(parents=True, exist_ok=True)
                for c in js:
                    try:
                        shutil.copy2(c, backup_root / "sessions-global" / c.name)
                    except Exception:
                        pass
            for c in js:
                try:
                    c.unlink()
                except Exception:
                    pass


# ---------------------------------------------------------------------------
# Build (re-emit invariants)
# ---------------------------------------------------------------------------
def _run_step(step: StepResult, cmd: list[str], cwd: Path, log_path: Path) -> bool:
    """Wrap subprocess.run; tee into log_path; record step metadata."""
    step.started_at = time.time()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        r = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=600)
        step.ok = (r.returncode == 0)
        step.stdout_tail = (r.stdout or "")[-1200:]
        step.stderr_tail = (r.stderr or "")[-1200:]
        log_path.write_text(
            f"$ {' '.join(cmd)}\n[exit={r.returncode}]\n--- STDOUT ---\n{r.stdout}\n--- STDERR ---\n{r.stderr}",
            encoding="utf-8",
        )
    except subprocess.TimeoutExpired:
        step.ok = False
        step.message = "TIMEOUT after 600s"
        log_path.write_text("TIMEOUT", encoding="utf-8")
    except Exception as exc:
        step.ok = False
        step.message = str(exc)
        log_path.write_text(f"EXC: {exc}", encoding="utf-8")
    finally:
        step.finished_at = time.time()
    return step.ok


def rebuild_all(run_logs_dir: Path) -> list[StepResult]:
    steps: list[StepResult] = []
    for sub, root, script in [
        ("capflow-build", CAPFLOW_ROOT, ["python", "tools/build_cases.py"]),
        ("authblur-build", AUTHBLUR_ROOT, ["python", "tools/build_cases.py"]),
        ("authblur-build-scripts", AUTHBLUR_ROOT, ["python", "tools/build_scripts.py"]),
        ("trustlift-build", TRUSTLIFT_ROOT, ["python", "tools/build_sandboxes.py"]),
    ]:
        s = StepResult(name=sub, ok=False, started_at=0.0, finished_at=0.0)
        ok = _run_step(s, script, root, run_logs_dir / f"{sub}.log")
        steps.append(s)
        if not ok:
            break  # stop on first failure
    return steps


# ---------------------------------------------------------------------------
# Run experiments
# ---------------------------------------------------------------------------
def run_capflow(cases: list[int], *, trials: int, timeout: int, parallel_unused: int,
                run_logs_dir: Path, model_tag: str) -> list[StepResult]:
    """Run the per-case CapFlow experiment scripts."""
    out: list[StepResult] = []
    for cid in cases:
        script = CAPFLOW_ROOT / "scripts" / f"experiment_case{cid}.py"
        if not script.exists():
            s = StepResult(name=f"capflow-case{cid}", ok=False, started_at=0.0, finished_at=0.0,
                           message=f"missing {script}")
            out.append(s)
            continue
        result_path = CAPFLOW_ROOT / "cases" / f"case{cid}" / "results" / f"run_real_t{str(trials)}_{model_tag}.json"
        result_path.parent.mkdir(parents=True, exist_ok=True)
        s = StepResult(name=f"capflow-case{cid}", ok=False, started_at=0.0, finished_at=0.0)
        ok = _run_step(
            s,
            ["python", str(script), "--condition", "all",
             "--trials", str(trials),
             "--output", str(result_path)],
            CAPFLOW_ROOT,
            run_logs_dir / f"capflow_case{cid}.log",
        )
        out.append(s)
    return out


def run_trustlift(*, trials_unused: int, timeout: int, parallel: int,
                  run_logs_dir: Path) -> list[StepResult]:
    out: list[StepResult] = []
    # TrustLift evaluates six conditions.
    for cond in ("directed", "non_endorsed", "endorsed_full",
                 "endorsed_branch", "pair_review_install", "pair_manifest_install"):
        s = StepResult(name=f"trustlift-{cond}", ok=False, started_at=0.0, finished_at=0.0)
        ok = _run_step(
            s,
            ["python", "run_experiment.py",
             "--condition", cond,
             "--parallel", str(parallel),
             "--timeout", str(timeout)],
            TRUSTLIFT_ROOT,
            run_logs_dir / f"trustlift_{cond}.log",
        )
        out.append(s)
    return out


def run_authblur(cases: list[int], *, trials: int, timeout: int, parallel_unused: int,
                 run_logs_dir: Path, model_tag: str) -> list[StepResult]:
    out: list[StepResult] = []
    for cid in cases:
        script = AUTHBLUR_ROOT / "experiment_scripts" / f"run_experiment_levels_{cid}.py"
        if not script.exists():
            s = StepResult(name=f"authblur-case{cid}", ok=False, started_at=0.0, finished_at=0.0,
                           message=f"missing {script}")
            out.append(s)
            continue
        result_path = AUTHBLUR_ROOT / "cases" / f"case{cid}" / "results" / f"run_real_t{str(trials)}_{model_tag}.json"
        result_path.parent.mkdir(parents=True, exist_ok=True)
        s = StepResult(name=f"authblur-case{cid}", ok=False, started_at=0.0, finished_at=0.0)
        ok = _run_step(
            s,
            ["python", str(script),
             "--trials", str(trials),
             "--output", str(result_path)],
            AUTHBLUR_ROOT,
            run_logs_dir / f"authblur_case{cid}.log",
        )
        # pass --timeout to script if it accepts it; many don't have it; harmless either way
        out.append(s)
    return out


# ---------------------------------------------------------------------------
# Snapshot
# ---------------------------------------------------------------------------
def make_snapshot(snap_dir: Path, *, model_name: str, parallel: int, timeout: int,
                  trials: int, command_line: list[str], steps: list[StepResult],
                  pre_backup_kept: bool) -> None:
    snap_dir.mkdir(parents=True, exist_ok=True)
    post = snap_dir / "post_run"
    post.mkdir(parents=True, exist_ok=True)

    # Capture runtime state immediately after the run.
    def _copy(src: Path, dest_rel: str) -> None:
        if not src.exists():
            return
        target = post / dest_rel
        if src.is_dir():
            shutil.copytree(src, target, dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns("__pycache__"))
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, target)

    _copy(PROJECT_SETTINGS, "project.settings.json")
    _copy(GLOBAL_SETTINGS, "global.settings.json")
    _copy(PROJECT_SESSION_DIR, "session-cache")
    _copy(GLOBAL_SESSIONS_DIR, "sessions-global")
    _copy(CAPFLOW_ROOT / "cases", "capflow.cases")
    _copy(AUTHBLUR_ROOT / "cases", "authblur.cases")
    _copy(TRUSTLIFT_ROOT / "experiment", "trustlift.experiment")
    _copy(TRUSTLIFT_ROOT / "results", "trustlift.results")

    # meta
    meta = {
        "snapshot_dir": str(snap_dir),
        "model_name": model_name,
        "claude_cli_version": claude_cli_version(),
        "python_version": sys.version,
        "platform": platform.platform(),
        "cwd": os.getcwd(),
        "command_line": command_line,
        "args": {"parallel": parallel, "timeout": timeout, "trials": trials},
        "env_relevant": {k: v for k, v in os.environ.items()
                         if k.startswith(("ANTHROPIC_", "CLAUDE_CODE_", "API_TIMEOUT_"))},
        "steps": [
            {"name": s.name, "ok": s.ok, "duration_s": round(s.duration_s, 2),
             "message": s.message, "stdout_tail": s.stdout_tail, "stderr_tail": s.stderr_tail}
            for s in steps
        ],
        "started_at": _dt.datetime.fromtimestamp(steps[0].started_at).isoformat()
                      if steps else None,
        "finished_at": _dt.datetime.fromtimestamp(steps[-1].finished_at).isoformat()
                       if steps else None,
        "pre_backup_kept": pre_backup_kept,
    }
    (snap_dir / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False),
                                         encoding="utf-8")

    # also copy meta into post_run for portability
    shutil.copy2(snap_dir / "meta.json", post / "meta.json")


def final_clean() -> None:
    """Reset to clean — no backup this time (we just snapshotted everything)."""
    tmp = PROJECT_ROOT / "snapshots" / "_tmp_pre_final_clean"
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True, exist_ok=True)
    reset_to_clean(tmp, keep_backup=False)
    shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_cases_arg(arg: str) -> list[int]:
    return [int(x.strip()) for x in arg.split(",") if x.strip()]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--parallel", type=int, default=4,
                   help="TrustLift sandboxes run in parallel (default 4).")
    p.add_argument("--timeout", type=int, default=300,
                   help="Per-claude-CLI-call timeout, seconds (default 300).")
    p.add_argument("--trials", type=int, default=3,
                   help="Trials per condition per case (default 3).")
    p.add_argument("--cases", type=parse_cases_arg, default=[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11],
                   help="Comma-separated case ids to run, default 1..11.")
    p.add_argument("--sub-benches", default="capflow,trustlift,authblur",
                   help="Subset of {capflow,trustlift,authblur}, default all.")
    p.add_argument("--skip-capflow", action="store_true", help=argparse.SUPPRESS)
    p.add_argument("--skip-trustlift", action="store_true", help=argparse.SUPPRESS)
    p.add_argument("--skip-authblur", action="store_true", help=argparse.SUPPRESS)
    p.add_argument("--output-root", type=Path, default=SNAPSHOTS_ROOT,
                   help="Where to write snapshots/ (default ./snapshots).")
    p.add_argument("--snapshot-name", default="auto",
                   help="Snapshot dir name, or 'auto' for YYYYMMDD_HHMMSS_<model>.")
    p.add_argument("--model-name", default="auto",
                   help="Override model tag (default: read from .claude/settings.json).")
    p.add_argument("--no-build", action="store_true",
                   help="Skip build_cases / build_scripts / build_sandboxes step.")
    p.add_argument("--keep-pre-backup", action="store_true",
                   help="Keep pre-clean dirty backups inside the snapshot "
                        "(default: not kept to save disk).")
    p.add_argument("--no-snapshot", action="store_true",
                   help="Skip the snapshot step (for debugging).")
    p.add_argument("--no-final-clean", action="store_true",
                   help="Skip the final clean step.")
    p.add_argument("--dry-run", action="store_true",
                   help="Print what would happen without running anything that mutates state.")
    args = p.parse_args()

    parallel: int = args.parallel
    timeout: int = args.timeout
    trials: int = args.trials
    cases: list[int] = args.cases
    sub_benches = {s.strip() for s in args.sub_benches.split(",") if s.strip()}
    if args.skip_capflow:
        sub_benches.discard("capflow")
    if args.skip_trustlift:
        sub_benches.discard("trustlift")
    if args.skip_authblur:
        sub_benches.discard("authblur")

    model_name = (args.model_name if args.model_name != "auto" else detect_model_name())
    if args.snapshot_name == "auto":
        stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        safe = model_name.replace("/", "_").replace(":", "_").replace("\\", "_")
        snap_name = f"{stamp}_{safe}"
    else:
        snap_name = args.snapshot_name
    snap_dir = (args.output_root / snap_name).resolve()

    # ---------- print banner ----------
    print("=" * 70)
    print(f"[run_full_experiment] model={model_name}")
    print(f"[run_full_experiment] parallel={parallel} timeout={timeout}s trials={trials}")
    print(f"[run_full_experiment] cases={cases} sub-benches={sorted(sub_benches)}")
    print(f"[run_full_experiment] snapshot_dir={snap_dir}")
    if args.dry_run:
        print("[run_full_experiment] DRY RUN — no state mutation")
    print("=" * 70)

    if args.dry_run:
        print("  + detect_model_name  ->", model_name)
        print("  + check_clean()")
        print("  + reset_to_clean()   (if dirty; backup to snapshot/pre_clean/)")
        print("  + rebuild_all()      (build_cases / build_scripts / build_sandboxes)")
        print("  + run_capflow()      for cases =", cases)
        print("  + run_trustlift()    6 conditions")
        print("  + run_authblur()     for cases =", cases)
        print("  + make_snapshot()    to", snap_dir)
        print("  + final_clean()")
        return 0

    snap_dir.mkdir(parents=True, exist_ok=True)
    run_logs_dir = snap_dir / "run_logs"
    run_logs_dir.mkdir(parents=True, exist_ok=True)

    # Write meta-protocol
    (snap_dir / "protocol.txt").write_text(
        "\n".join([
            f"model_name        = {model_name}",
            f"claude_cli_version = {claude_cli_version()}",
            f"started_at        = {_dt.datetime.now().isoformat()}",
            f"args              = parallel={parallel} timeout={timeout} trials={trials}",
            f"                  cases={cases} sub_benches={sorted(sub_benches)}",
        ]),
        encoding="utf-8",
    )

    # ---------- step 1: check_clean ----------
    print("\n[1/6] check_clean() ...")
    rep = check_clean()
    print("      ", rep.render().replace("\n", "\n       "))

    # ---------- step 2: reset_to_clean if dirty ----------
    if not rep.is_clean:
        print("\n[2/6] reset_to_clean() ...")
        reset_to_clean(snap_dir, keep_backup=args.keep_pre_backup)
        # verify
        rep2 = check_clean()
        print("      ", "PASS — re-check clean" if rep2.is_clean else "STILL DIRTY:\n       " + rep2.render().replace("\n", "\n       "))
        if not rep2.is_clean:
            print("[ERROR] reset_to_clean() failed; aborting")
            return 2
    else:
        print("\n[2/6] reset_to_clean() skipped (already clean)")

    # ---------- step 3: rebuild ----------
    steps_all: list[StepResult] = []
    if not args.no_build:
        print("\n[3/6] rebuild_all() ...")
        rebuild_steps = rebuild_all(run_logs_dir)
        steps_all.extend(rebuild_steps)
        for s in rebuild_steps:
            print(f"      {s.name}: ok={s.ok} dur={s.duration_s:.1f}s")
            if not s.ok:
                print("         ", s.stderr_tail[-200:] if s.stderr_tail else s.message)
                print("[ERROR] build step failed; aborting")
                return 3
    else:
        print("\n[3/6] rebuild_all() skipped (--no-build)")

    # ---------- step 4: run experiments ----------
    print("\n[4/6] running experiments ...")
    if "capflow" in sub_benches:
        cf_steps = run_capflow(cases, trials=trials, timeout=timeout, parallel_unused=parallel,
                                run_logs_dir=run_logs_dir, model_tag=snap_name)
        steps_all.extend(cf_steps)
        print(f"      capflow: {sum(1 for s in cf_steps if s.ok)}/{len(cf_steps)} ok")

    if "trustlift" in sub_benches:
        tl_steps = run_trustlift(trials_unused=trials, timeout=timeout, parallel=parallel,
                                  run_logs_dir=run_logs_dir)
        steps_all.extend(tl_steps)
        print(f"      trustlift: {sum(1 for s in tl_steps if s.ok)}/{len(tl_steps)} ok")

    if "authblur" in sub_benches:
        ab_steps = run_authblur(cases, trials=trials, timeout=timeout, parallel_unused=parallel,
                                 run_logs_dir=run_logs_dir, model_tag=snap_name)
        steps_all.extend(ab_steps)
        print(f"      authblur: {sum(1 for s in ab_steps if s.ok)}/{len(ab_steps)} ok")

    # ---------- step 5: snapshot ----------
    if not args.no_snapshot:
        print(f"\n[5/6] make_snapshot() → {snap_dir} ...")
        try:
            make_snapshot(snap_dir, model_name=model_name, parallel=parallel, timeout=timeout,
                          trials=trials, command_line=sys.argv, steps=steps_all,
                          pre_backup_kept=args.keep_pre_backup)
            print(f"      OK ({snap_dir})")
        except Exception as exc:
            print(f"      FAIL: {exc}")
            return 5
    else:
        print("\n[5/6] snapshot skipped (--no-snapshot)")

    # ---------- step 6: final clean ----------
    if not args.no_final_clean:
        print("\n[6/6] final_clean() ...")
        try:
            final_clean()
            rep3 = check_clean()
            if rep3.is_clean:
                status_msg = "PASS — clean"
            else:
                status_msg = "STILL DIRTY:\n       " + rep3.render().replace("\n", "\n       ")
            print(f"      {status_msg}")
        except Exception as exc:
            print(f"      FAIL: {exc}")
            return 6
    else:
        print("\n[6/6] final_clean skipped (--no-final-clean)")

    print("\n[done]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
