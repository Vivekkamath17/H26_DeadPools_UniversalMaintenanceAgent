#!/usr/bin/env python3
"""
main.py
───────
CLI Orchestrator for the Universal Maintenance Agent.

Coordinates the 4-agent sequential loop:
  [1] DeepInspectorAgent  →  deterministic static analysis
  [2] DiagnosticAgent     →  open-weight LLM reasoning (CoV)
  [3] SandboxAgent        →  patch application + test verification + self-healing
  [4] CapsuleCompiler     →  Dependency Exit Capsule (JSON + Markdown)

Usage
─────
  python main.py --repo <PATH_OR_GITHUB_URL> [--output OUTPUT_DIR]

Environment Variables
─────────────────────
  GROQ_API_KEY      – enable Groq backend
  GROQ_MODEL        – Groq model name (default: llama3-8b-8192)
  OLLAMA_BASE_URL   – Ollama server URL (default: http://localhost:11434)
  OLLAMA_MODEL      – Ollama model tag (default: llama3:8b)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from pathlib import Path

# ── Load environment variables from .env ─────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ── Rich terminal UI ─────────────────────────────────────────────────────────
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
    from rich.rule import Rule
    from rich.table import Table
    from rich import print as rprint
    import io as _io
    _HAS_RICH = True
    # Force UTF-8 on Windows to avoid cp1252 UnicodeEncodeError
    _safe_file = _io.TextIOWrapper(
        _io.open(1, "wb", closefd=False), encoding="utf-8", errors="replace", line_buffering=True
    ) if sys.platform == "win32" else None
    console = Console(file=_safe_file, highlight=False, emoji=False)
except ImportError:
    _HAS_RICH = False
    console = None  # type: ignore[assignment]


def _banner() -> None:
    if _HAS_RICH:
        console.print(Panel.fit(
            "[bold bright_cyan]Universal Maintenance Agent[/bold bright_cyan]\n"
            "[dim]Enterprise-Grade Multi-Agent Maintenance System[/dim]\n"
            "[dim]Agent Skills Open Standard v1.0.0[/dim]",
            border_style="bright_cyan",
        ))
    else:
        print("=" * 60)
        print("  Universal Maintenance Agent")
        print("  Enterprise-Grade Multi-Agent Maintenance System")
        print("=" * 60)


def _section(title: str) -> None:
    if _HAS_RICH:
        console.print(Rule(f"[bold yellow]{title}[/bold yellow]", style="yellow"))
    else:
        print(f"\n{'─' * 60}")
        print(f"  {title}")
        print(f"{'─' * 60}")


def _ok(msg: str) -> None:
    if _HAS_RICH:
        console.print(f"  [bold green][OK][/bold green] {msg}")
    else:
        print(f"  [OK] {msg}")


def _warn(msg: str) -> None:
    if _HAS_RICH:
        console.print(f"  [bold yellow][!!][/bold yellow] {msg}")
    else:
        print(f"  [!!] {msg}")


def _err(msg: str) -> None:
    if _HAS_RICH:
        console.print(f"  [bold red][ERR][/bold red] {msg}")
    else:
        print(f"  [ERR] {msg}")


def _info(msg: str) -> None:
    if _HAS_RICH:
        console.print(f"  [dim]->[/dim] {msg}")
    else:
        print(f"  -> {msg}")


# ── Path setup ───────────────────────────────────────────────────────────────
_ROOT = Path(__file__).parent
_AGENTS_DIR = _ROOT / "skills" / "universal-maintainer" / "agents"
sys.path.insert(0, str(_AGENTS_DIR.parent))  # make prompts/ importable
sys.path.insert(0, str(_AGENTS_DIR))


def _import_agents():
    """Lazy import of agents – gives friendly errors if deps are missing."""
    try:
        from agents.inspector_agent        import DeepInspectorAgent
        from agents.diagnostic_agent       import DiagnosticAgent
        from agents.sandbox_agent          import SandboxAgent
        from agents.capsule_compiler       import CapsuleCompiler
        from agents.tree_sitter_inspector  import TreeSitterInspector
        from agents.pr_agent               import InteractivePRAgent
        return (
            DeepInspectorAgent,
            DiagnosticAgent,
            SandboxAgent,
            CapsuleCompiler,
            TreeSitterInspector,
            InteractivePRAgent,
        )
    except ImportError as exc:
        _err(f"Import failed: {exc}")
        _err("Run:  pip install -r requirements.txt")
        sys.exit(1)


# ── Argument parsing ─────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="main.py",
        description=(
            "Universal Maintenance Agent – runs a 4-agent autonomous "
            "maintenance audit on any software repository."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --repo /path/to/project
  python main.py --repo https://github.com/rishrek/LinkWatch
  GROQ_API_KEY=gsk_xxx python main.py --repo ./myproject --output ./results
        """,
    )
    parser.add_argument(
        "--repo", "-r",
        required=True,
        metavar="PATH_OR_URL",
        help="Local filesystem path or GitHub URL to the target repository.",
    )
    parser.add_argument(
        "--output", "-o",
        default="output",
        metavar="DIR",
        help="Output directory for the Dependency Exit Capsule (default: ./output).",
    )
    parser.add_argument(
        "--skip-sandbox",
        action="store_true",
        default=False,
        help="Skip patch application and test execution (faster, read-only audit).",
    )
    parser.add_argument(
        "--json-only",
        action="store_true",
        default=False,
        help="Only write JSON capsule, skip Markdown generation.",
    )
    parser.add_argument(
        "--no-pr",
        action="store_true",
        default=False,
        help="Skip the interactive Git branch and GitHub PR creation workflow.",
    )
    parser.add_argument(
        "--auto-pr",
        action="store_true",
        default=False,
        help="Auto-confirm Git branch and PR creation without interactive user prompts.",
    )
    return parser.parse_args()


# ── Timing utility ───────────────────────────────────────────────────────────

class _Timer:
    def __init__(self) -> None:
        self._start = time.perf_counter()
        self._splits: list[tuple[str, float]] = []

    def split(self, label: str) -> None:
        self._splits.append((label, time.perf_counter() - self._start))

    def summary(self) -> dict[str, str]:
        result: dict[str, str] = {}
        prev = 0.0
        for label, t in self._splits:
            result[label] = f"{t - prev:.2f}s"
            prev = t
        result["total"] = f"{time.perf_counter() - self._start:.2f}s"
        return result


# ── Results table (Rich) ─────────────────────────────────────────────────────

def _print_summary(
    facts: dict,
    diagnosis: object,
    sandbox_result: object,
    json_path: Path,
    md_path: Path,
    timing: dict[str, str],
    pr_result: object | None = None,
) -> None:
    if not _HAS_RICH:
        _ok(f"JSON Capsule: {json_path}")
        _ok(f"Markdown Report: {md_path}")
        if pr_result and getattr(pr_result, "pr_url", None):
            _ok(f"PR URL: {pr_result.pr_url}")
        return

    diag_dict = diagnosis.to_dict() if hasattr(diagnosis, "to_dict") else {}
    sb_dict   = sandbox_result.to_dict() if hasattr(sandbox_result, "to_dict") else {}

    tbl = Table(title="Run Summary", show_lines=True, border_style="bright_cyan")
    tbl.add_column("Metric", style="bold")
    tbl.add_column("Value", style="bright_white")

    tbl.add_row("Repository",    facts.get("repo_path", "?"))
    tbl.add_row("Stack",         ", ".join(facts.get("stack", ["unknown"])))
    tbl.add_row("Manifests",     str(len(facts.get("manifests_found", []))))
    tbl.add_row("Dependencies",  str(sum(len(v) for v in facts.get("dependencies", {}).values())))
    tbl.add_row("Import Usages", str(len(facts.get("import_usages", []))))
    tbl.add_row("AST Syntax Errors", str(len(facts.get("syntax_errors", []))))
    tbl.add_row("Risk Indicators",   str(len(diag_dict.get("risk_indicators", []))))
    tbl.add_row("Proposed Patches",  str(len(diag_dict.get("recommended_patches", []))))
    tbl.add_row("LLM Backend",       diag_dict.get("backend_used", "unknown"))
    tbl.add_row("Tests Passed",      "✓" if sb_dict.get("success") else "✗")
    tbl.add_row("Test Attempts",     str(sb_dict.get("attempts", 0)))
    tbl.add_row("Rolled Back",       str(sb_dict.get("patches_rolled_back", False)))
    if pr_result:
        tbl.add_row("PR Workflow", getattr(pr_result, "status", "n/a"))
        if getattr(pr_result, "pr_url", None):
            tbl.add_row("PR URL", pr_result.pr_url)
        elif getattr(pr_result, "branch_name", None):
            tbl.add_row("PR Branch", pr_result.branch_name)

    for phase, dur in timing.items():
        tbl.add_row(f"⏱ {phase}", dur)

    console.print(tbl)
    console.print()
    console.print(f"  [green]JSON[/green] → {json_path}")
    console.print(f"  [green]MD[/green]   → {md_path}")


# ── Main orchestrator ─────────────────────────────────────────────────────────

def main() -> int:
    _banner()
    args = _parse_args()
    timer = _Timer()

    (
        DeepInspectorAgent,
        DiagnosticAgent,
        SandboxAgent,
        CapsuleCompiler,
        TreeSitterInspector,
        InteractivePRAgent,
    ) = _import_agents()

    # ── Phase 1: Deep Inspection ─────────────────────────────────────────────
    _section("Phase 1 · Deep Inspector Agent")
    _info(f"Target: {args.repo}")

    inspector = DeepInspectorAgent()
    try:
        facts_obj = inspector.inspect(args.repo)
        facts     = facts_obj.to_dict()
    except Exception as exc:
        _err(f"Inspector failed: {exc}")
        if os.environ.get("DEBUG"):
            traceback.print_exc()
        return 1

    _ok(f"Stack detected: {facts.get('stack')}")
    _ok(f"Manifests found: {len(facts.get('manifests_found', []))}")
    _ok(f"Dependencies parsed: {sum(len(v) for v in facts.get('dependencies', {}).values())}")
    _ok(f"Import usages mapped: {len(facts.get('import_usages', []))}")
    _ok(f"AST files scanned: {facts.get('ast_findings', {}).get('scanned_files', 0)}")
    _ok(f"AST syntax errors: {len(facts.get('syntax_errors', []))}")
    if facts.get("errors"):
        for e in facts["errors"]:
            _warn(e)
    timer.split("1. Inspection")

    # ── Phase 2: Diagnostic Reasoning ───────────────────────────────────────
    _section("Phase 2 · Diagnostic & Reasoning Agent (CoV)")

    diagnostic = DiagnosticAgent()
    try:
        diagnosis = diagnostic.diagnose(facts)
    except Exception as exc:
        _err(f"Diagnostic agent failed: {exc}")
        if os.environ.get("DEBUG"):
            traceback.print_exc()
        return 1

    _ok(f"Backend used: {diagnosis.backend_used}")
    _ok(f"Risk indicators: {len(diagnosis.risk_indicators)}")
    _ok(f"Proposed patches: {len(diagnosis.recommended_patches)}")
    for risk in diagnosis.risk_indicators[:5]:
        _info(f"  🔴 {risk}")
    timer.split("2. Diagnosis")

    # ── Phase 3: Sandbox Verification ────────────────────────────────────────
    _section("Phase 3 · Sandbox Verification & Self-Healing Agent")

    if args.skip_sandbox:
        _warn("--skip-sandbox flag set – skipping patch application and tests.")
        from agents.sandbox_agent import SandboxResult
        sandbox_result = SandboxResult(
            success=True,
            attempts=0,
            test_command="skipped",
            stdout="Sandbox skipped by user flag.",
        )
    else:
        sandbox = SandboxAgent(
            repo_path=facts.get("repo_path", args.repo),
            diagnostic_agent=diagnostic,
        )
        try:
            sandbox_result = sandbox.verify(diagnosis, facts)
        except Exception as exc:
            _err(f"Sandbox agent failed: {exc}")
            if os.environ.get("DEBUG"):
                traceback.print_exc()
            from agents.sandbox_agent import SandboxResult
            sandbox_result = SandboxResult(error=str(exc))

    if sandbox_result.success:
        _ok("Tests passed!")
    else:
        _warn(f"Tests did not pass after {sandbox_result.attempts} attempt(s).")
        if sandbox_result.patches_rolled_back:
            _info("All patches rolled back successfully.")
    timer.split("3. Sandbox")

    # ── Phase 4: Capsule Compilation ─────────────────────────────────────────
    _section("Phase 4 · Dependency Exit Capsule Compiler")

    output_dir = str(Path(args.output).resolve())
    compiler = CapsuleCompiler(output_dir=output_dir)
    try:
        json_path, md_path = compiler.compile(facts, diagnosis, sandbox_result)
    except Exception as exc:
        _err(f"Capsule compiler failed: {exc}")
        if os.environ.get("DEBUG"):
            traceback.print_exc()
        return 1

    _ok("Dependency Exit Capsule written.")
    timer.split("4. Compilation")

    # ── Phase 5: Interactive Git & PR Agent ──────────────────────────────────
    pr_result = None
    if not args.no_pr and diagnosis.recommended_patches:
        _section("Phase 5 · Interactive Git & GitHub PR Agent")
        pr_agent = InteractivePRAgent(facts.get("repo_path", args.repo))
        try:
            pr_result = pr_agent.create_pr_workflow(
                problem_summary=diagnosis.problem_summary,
                patches=diagnosis.recommended_patches,
                interactive=not args.auto_pr,
                auto_confirm=args.auto_pr,
            )
        except Exception as exc:
            _err(f"PR agent failed: {exc}")
            if os.environ.get("DEBUG"):
                traceback.print_exc()
        timer.split("5. PR Workflow")

    # ── Final summary ────────────────────────────────────────────────────────
    _section("Run Complete")
    _print_summary(facts, diagnosis, sandbox_result, json_path, md_path, timer.summary(), pr_result=pr_result)

    return 0


if __name__ == "__main__":
    sys.exit(main())
