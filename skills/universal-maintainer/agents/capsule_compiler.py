"""
capsule_compiler.py
────────────────────
Dependency Exit Capsule Compiler.

Assembles findings from all three preceding agents into:
  * output/dependency_exit_capsule.json  – schema-validated machine artifact
  * output/dependency_exit_capsule.md   – human-readable report

Strictly separates observed facts (from InspectorAgent) from AI-generated
recommendations (from DiagnosticAgent) in the Markdown output.
"""

from __future__ import annotations

import datetime
import json
import os
from pathlib import Path
from typing import Any

# ── Optional deps ────────────────────────────────────────────────────────────
try:
    import jsonschema  # type: ignore
    _HAS_JSONSCHEMA = True
except ImportError:
    _HAS_JSONSCHEMA = False

try:
    from rich.console import Console
    _console = Console()
    def log(msg: str, style: str = "bright_cyan") -> None:
        _console.print(f"[{style}][Capsule][/{style}] {msg}")
except ImportError:
    def log(msg: str, style: str = "bright_cyan") -> None:  # type: ignore[misc]
        print(f"[Capsule] {msg}")


# ── Schema path ──────────────────────────────────────────────────────────────
_SCHEMA_PATH = Path(__file__).parent.parent / "references" / "exit_capsule_schema.json"


# ── Main Compiler Class ───────────────────────────────────────────────────────

class CapsuleCompiler:
    """
    Assembles, validates, and serialises the Dependency Exit Capsule.

    Parameters
    ──────────
    output_dir – directory where capsule files are written (default: ./output)
    """

    def __init__(self, output_dir: str = "output") -> None:
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._schema = self._load_schema()

    # ── Public entry point ───────────────────────────────────────────────────

    def compile(
        self,
        observed_facts: dict[str, Any],
        diagnosis: Any,        # DiagnosisResult
        sandbox_result: Any,   # SandboxResult
    ) -> tuple[Path, Path]:
        """
        Build and write the capsule. Returns (json_path, md_path).
        """
        log("Assembling Dependency Exit Capsule …")
        capsule = self._build_capsule(observed_facts, diagnosis, sandbox_result)
        capsule_validated = self._validate(capsule)

        json_path = self._write_json(capsule_validated)
        md_path   = self._write_markdown(capsule_validated, observed_facts, diagnosis)

        log(f"JSON capsule → {json_path}", "green")
        log(f"Markdown report → {md_path}", "green")
        return json_path, md_path

    # ── Capsule assembly ─────────────────────────────────────────────────────

    def _build_capsule(
        self,
        facts: dict[str, Any],
        diagnosis: Any,
        sandbox: Any,
    ) -> dict[str, Any]:
        diag_dict = (
            diagnosis.to_dict() if hasattr(diagnosis, "to_dict") else dict(diagnosis)
        )
        sb_dict = (
            sandbox.to_dict() if hasattr(sandbox, "to_dict") else dict(sandbox)
        )

        # Collect usage locations from facts
        usages: list[str] = []
        for u in facts.get("import_usages", []):
            loc = f"{u.get('file_path', '')}:{u.get('line_number', '')}"
            if loc not in usages:
                usages.append(loc)
        usages = usages[:50]  # cap list length

        # Dependency details block
        dep_details: dict[str, Any] = {
            "repo_path": facts.get("repo_path", ""),
            "stack": facts.get("stack", []),
            "git_info": facts.get("git_info", {}),
            "manifests_found": facts.get("manifests_found", []),
            "declared_dependencies": facts.get("dependencies", {}),
        }

        # Proposed changes – join patch descriptions into a readable string
        patches = diag_dict.get("recommended_patches", [])
        if patches:
            proposed = "\n\n".join(
                f"[{p.get('file', 'unknown')}] {p.get('description', '')}\n"
                f"```diff\n{p.get('unified_diff', '(no diff)')}\n```"
                for p in patches
            )
        else:
            proposed = "No automated patches were proposed."

        # Test results
        executed_tests: dict[str, Any] = {
            "command":          sb_dict.get("test_command", "none"),
            "exit_code":        sb_dict.get("exit_code", -1),
            "success":          sb_dict.get("success", False),
            "attempts":         sb_dict.get("attempts", 0),
            "rolled_back":      sb_dict.get("patches_rolled_back", False),
            "stdout_tail":      (sb_dict.get("stdout", "") or "")[-2000:],
            "stderr_tail":      (sb_dict.get("stderr", "") or "")[-2000:],
            "reflection_count": len(sb_dict.get("reflection_logs", [])),
        }

        compatibility_gaps: list[str] = diag_dict.get("compatibility_gaps", [])
        if sb_dict.get("error"):
            compatibility_gaps.append(f"Sandbox error: {sb_dict['error']}")

        unresolved: list[str] = diag_dict.get("unresolved_concerns", [])
        if facts.get("errors"):
            unresolved.extend(
                [f"Inspector error: {e}" for e in facts["errors"]]
            )

        return {
            "maintenance_problem_identified":      diag_dict.get("problem_summary", ""),
            "relevant_dependency_or_repo_details": dep_details,
            "risk_indicators":                     diag_dict.get("risk_indicators", []),
            "usage_locations":                     usages,
            "ai_generated_analysis_or_recommendations": diag_dict.get("cov_verification_log", ""),
            "proposed_changes_or_maintenance_approach": proposed,
            "suggested_tests_or_verification_steps":   diag_dict.get("suggested_tests", []),
            "executed_test_results":               executed_tests,
            "compatibility_or_maintenance_gaps":   compatibility_gaps,
            "unresolved_concerns_and_limitations": unresolved,
            # Extra metadata (not in schema – won't break validation)
            "_meta": {
                "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
                "backend_used": diag_dict.get("backend_used", "unknown"),
                "schema_version": "1.0.0",
            },
        }

    # ── Schema validation ────────────────────────────────────────────────────

    def _load_schema(self) -> dict[str, Any] | None:
        try:
            with open(_SCHEMA_PATH, encoding="utf-8") as fh:
                return json.load(fh)
        except Exception as exc:
            log(f"⚠ Could not load schema: {exc}", "yellow")
            return None

    def _validate(self, capsule: dict[str, Any]) -> dict[str, Any]:
        if not _HAS_JSONSCHEMA or not self._schema:
            log("Schema validation skipped (jsonschema not installed).", "yellow")
            return capsule
        try:
            jsonschema.validate(instance=capsule, schema=self._schema)
            log("Schema validation passed ✓", "green")
        except jsonschema.ValidationError as exc:
            log(f"⚠ Schema validation error: {exc.message}", "yellow")
        return capsule

    # ── JSON output ──────────────────────────────────────────────────────────

    def _write_json(self, capsule: dict[str, Any]) -> Path:
        json_path = self._output_dir / "dependency_exit_capsule.json"
        with open(json_path, "w", encoding="utf-8") as fh:
            json.dump(capsule, fh, indent=2, default=str)
        return json_path

    # ── Markdown output ──────────────────────────────────────────────────────

    def _write_markdown(
        self,
        capsule: dict[str, Any],
        facts: dict[str, Any],
        diagnosis: Any,
    ) -> Path:
        md_path = self._output_dir / "dependency_exit_capsule.md"
        diag_dict = (
            diagnosis.to_dict() if hasattr(diagnosis, "to_dict") else dict(diagnosis)
        )
        meta = capsule.get("_meta", {})
        dep  = capsule.get("relevant_dependency_or_repo_details", {})
        tests = capsule.get("executed_test_results", {})

        lines: list[str] = [
            "# Dependency Exit Capsule",
            "",
            f"> Generated: {meta.get('generated_at', 'unknown')}  ",
            f"> LLM Backend: `{meta.get('backend_used', 'unknown')}`  ",
            f"> Schema Version: `{meta.get('schema_version', '1.0.0')}`",
            "",
            "---",
            "",
            "## 1. Maintenance Problem Identified",
            "",
            capsule.get("maintenance_problem_identified", "_None identified._"),
            "",
            "---",
            "",
            "## 2. Repository & Dependency Details",
            "> ⚠️ **OBSERVED FACTS ONLY – no AI inference in this section**",
            "",
            f"- **Repository Path:** `{dep.get('repo_path', '')}`",
            f"- **Detected Stack:** `{', '.join(dep.get('stack', []))}`",
            "",
        ]

        # Git info
        git = dep.get("git_info", {})
        if git:
            lines += [
                "### Git Metadata",
                f"| Key | Value |",
                f"|-----|-------|",
            ]
            for k, v in git.items():
                lines.append(f"| {k} | `{v}` |")
            lines.append("")

        # Manifests
        manifests = dep.get("manifests_found", [])
        if manifests:
            lines += ["### Manifests Found", ""]
            for m in manifests:
                lines.append(f"- `{m}`")
            lines.append("")

        # Dependencies table
        all_deps = dep.get("declared_dependencies", {})
        if all_deps:
            lines += ["### Declared Dependencies", ""]
            for manifest, deps in all_deps.items():
                lines.append(f"**{manifest}**")
                lines.append("")
                lines.append("| Package | Version Constraint |")
                lines.append("|---------|-------------------|")
                for pkg, ver in list(deps.items())[:60]:
                    lines.append(f"| `{pkg}` | `{ver or 'unspecified'}` |")
                lines.append("")

        # Usage locations
        usages = capsule.get("usage_locations", [])
        if usages:
            lines += [
                "### Import Usage Locations (sample)",
                "",
                "| File:Line |",
                "|-----------|",
            ]
            for u in usages[:20]:
                lines.append(f"| `{u}` |")
            lines.append("")

        lines += [
            "---",
            "",
            "## 3. Risk Indicators",
            "> ⚠️ **AI-GENERATED SECTION** – treat as advisory, not ground truth",
            "",
        ]
        for risk in capsule.get("risk_indicators", ["_None identified._"]):
            lines.append(f"- 🔴 {risk}")
        lines.append("")

        lines += [
            "---",
            "",
            "## 4. AI-Generated Analysis (Chain-of-Verification Log)",
            "> ⚠️ **AI-GENERATED SECTION**",
            "",
            capsule.get("ai_generated_analysis_or_recommendations", "_Not available._"),
            "",
            "---",
            "",
            "## 5. Proposed Changes & Maintenance Approach",
            "> ⚠️ **AI-GENERATED SECTION** – Review all diffs before applying",
            "",
            capsule.get("proposed_changes_or_maintenance_approach", "_No changes proposed._"),
            "",
            "---",
            "",
            "## 6. Suggested Tests & Verification Steps",
            "",
        ]
        for test in capsule.get("suggested_tests_or_verification_steps", ["_None suggested._"]):
            lines.append(f"- [ ] {test}")
        lines.append("")

        lines += [
            "---",
            "",
            "## 7. Executed Test Results",
            "> ✅ **EMPIRICAL DATA** – captured from live subprocess execution",
            "",
            f"| Field | Value |",
            f"|-------|-------|",
            f"| Command | `{tests.get('command', 'none')}` |",
            f"| Exit Code | `{tests.get('exit_code', 'N/A')}` |",
            f"| Success | `{tests.get('success', False)}` |",
            f"| Attempts | `{tests.get('attempts', 0)}` |",
            f"| Rolled Back | `{tests.get('rolled_back', False)}` |",
            f"| Reflection Loops | `{tests.get('reflection_count', 0)}` |",
            "",
        ]
        if tests.get("stdout_tail"):
            lines += [
                "**Stdout (tail):**",
                "```",
                tests["stdout_tail"],
                "```",
                "",
            ]
        if tests.get("stderr_tail"):
            lines += [
                "**Stderr (tail):**",
                "```",
                tests["stderr_tail"],
                "```",
                "",
            ]

        lines += [
            "---",
            "",
            "## 8. Compatibility & Maintenance Gaps",
            "",
        ]
        for gap in capsule.get("compatibility_or_maintenance_gaps", ["_None identified._"]):
            lines.append(f"- ⚠️ {gap}")
        lines.append("")

        lines += [
            "---",
            "",
            "## 9. Unresolved Concerns & Limitations",
            "",
        ]
        for concern in capsule.get("unresolved_concerns_and_limitations", ["_None._"]):
            lines.append(f"- ❓ {concern}")
        lines.append("")

        lines += [
            "---",
            "",
            "_End of Dependency Exit Capsule_",
        ]

        with open(md_path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))
        return md_path


# ── CLI self-test ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys, json as _json
    compiler = CapsuleCompiler(output_dir="output")

    class _MockDiag:
        def to_dict(self): return {
            "problem_summary": "Self-test run",
            "risk_indicators": ["Test risk"],
            "recommended_patches": [],
            "suggested_tests": ["pytest"],
            "compatibility_gaps": [],
            "unresolved_concerns": [],
            "cov_verification_log": "Self-test",
            "backend_used": "heuristic",
        }

    class _MockSandbox:
        def to_dict(self): return {
            "test_command": "pytest",
            "exit_code": 0,
            "success": True,
            "attempts": 1,
            "patches_rolled_back": False,
            "stdout": "1 passed",
            "stderr": "",
            "reflection_logs": [],
            "error": "",
        }

    facts = {"repo_path": ".", "stack": ["Python"], "git_info": {}, "dependencies": {},
             "manifests_found": [], "import_usages": [], "errors": []}
    j, m = compiler.compile(facts, _MockDiag(), _MockSandbox())
    print(f"Written: {j}, {m}")
