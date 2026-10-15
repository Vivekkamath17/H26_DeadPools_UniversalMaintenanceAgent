"""
sandbox_agent.py
────────────────
Sandbox Verification & Test Agent.

Responsibilities
────────────────
* Apply proposed unified diffs in a controlled subprocess environment.
* Detect and run the correct test command for the project stack.
* Self-Healing Loop: on test failure, feed logs back to DiagnosticAgent for
  reflection and re-attempt (up to MAX_RETRIES times).
* Rollback Safety: revert all modified files to their original state on
  terminal failure via git checkout (or manual backup restoration).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ── Optional rich logging ────────────────────────────────────────────────────
try:
    from rich.console import Console
    _console = Console()
    def log(msg: str, style: str = "blue") -> None:
        _console.print(f"[{style}][Sandbox][/{style}] {msg}")
except ImportError:
    def log(msg: str, style: str = "blue") -> None:  # type: ignore[misc]
        print(f"[Sandbox] {msg}")


MAX_RETRIES = 3

# ── Result dataclass ─────────────────────────────────────────────────────────

@dataclass
class SandboxResult:
    success: bool = False
    attempts: int = 0
    test_command: str = ""
    stdout: str = ""
    stderr: str = ""
    exit_code: int = -1
    patches_applied: list[str] = field(default_factory=list)
    patches_rolled_back: bool = False
    reflection_logs: list[dict[str, Any]] = field(default_factory=list)
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "attempts": self.attempts,
            "test_command": self.test_command,
            "stdout": self.stdout[-4000:] if len(self.stdout) > 4000 else self.stdout,
            "stderr": self.stderr[-4000:] if len(self.stderr) > 4000 else self.stderr,
            "exit_code": self.exit_code,
            "patches_applied": self.patches_applied,
            "patches_rolled_back": self.patches_rolled_back,
            "reflection_logs": self.reflection_logs,
            "error": self.error,
        }


# ── Main Agent Class ─────────────────────────────────────────────────────────

class SandboxAgent:
    """
    Controlled patch application, test execution, and self-healing loop.

    Parameters
    ──────────
    repo_path        – absolute path to the cloned/local repository
    diagnostic_agent – DiagnosticAgent instance for reflection calls
    """

    # Maps stack name → test command candidates (tried in order)
    _TEST_COMMANDS: dict[str, list[list[str]]] = {
        "Python":  [["pytest", "--tb=short", "-q"],
                    ["python", "-m", "pytest", "--tb=short", "-q"],
                    ["python", "-m", "unittest", "discover"]],
        "NodeJS":  [["npm", "test", "--", "--watchAll=false"],
                    ["yarn", "test"],
                    ["npx", "jest", "--no-coverage"]],
        "Rust":    [["cargo", "test"]],
        "Go":      [["go", "test", "./..."]],
        "Java":    [["mvn", "test", "-q"],
                    ["gradle", "test"]],
        "Ruby":    [["bundle", "exec", "rspec"],
                    ["rake", "test"]],
    }

    def __init__(self, repo_path: str, diagnostic_agent: Any) -> None:
        self._repo_path = Path(repo_path)
        self._diagnostic = diagnostic_agent
        self._backups: dict[str, str] = {}  # rel_path → temp backup file

    # ── Public entry point ───────────────────────────────────────────────────

    def verify(
        self,
        diagnosis: Any,           # DiagnosisResult
        observed_facts: dict[str, Any],
    ) -> SandboxResult:
        """Apply patches and run tests, with up to MAX_RETRIES reflection loops."""
        result = SandboxResult()
        stacks: list[str] = observed_facts.get("stack", [])
        test_cmd = self._detect_test_command(stacks)
        result.test_command = " ".join(test_cmd) if test_cmd else "none"

        current_diagnosis = diagnosis

        for attempt in range(1, MAX_RETRIES + 1):
            result.attempts = attempt
            log(f"Attempt {attempt}/{MAX_RETRIES} – applying patches …")

            patches = getattr(current_diagnosis, "recommended_patches", [])
            applied = self._apply_patches(patches)
            result.patches_applied.extend(applied)

            if not test_cmd:
                log("No test command detected – skipping test execution.", "yellow")
                result.success = True
                result.stdout = "No test suite detected."
                result.exit_code = 0
                self._cleanup_backups()
                return result

            log(f"Running: {result.test_command}")
            stdout, stderr, rc = self._run_command(test_cmd)
            result.stdout    = stdout
            result.stderr    = stderr
            result.exit_code = rc

            if rc == 0:
                log(f"Tests passed on attempt {attempt}! ✓", "green")
                result.success = True
                self._cleanup_backups()
                return result

            # Tests failed
            failure_log = f"=== STDOUT ===\n{stdout}\n=== STDERR ===\n{stderr}"
            log(f"Tests failed (exit {rc}) – attempting reflection …", "yellow")

            result.reflection_logs.append({
                "attempt": attempt,
                "exit_code": rc,
                "failure_summary": stderr[:1000],
            })

            if attempt < MAX_RETRIES:
                # Feed failure back to DiagnosticAgent
                try:
                    patch_text = self._patches_to_text(patches)
                    current_diagnosis = self._diagnostic.reflect(
                        original_diagnosis=current_diagnosis.to_dict()
                            if hasattr(current_diagnosis, "to_dict")
                            else vars(current_diagnosis),
                        applied_patch=patch_text,
                        failure_log=failure_log,
                        attempt=attempt,
                        max_attempts=MAX_RETRIES,
                    )
                    # Roll back before applying revised patches
                    self._rollback(result)
                except Exception as exc:
                    log(f"Reflection call failed: {exc}", "red")
                    break

        # All attempts exhausted – rollback
        log("Max retries reached – performing rollback.", "red")
        self._rollback(result)
        result.patches_rolled_back = True
        result.error = f"Tests failed after {MAX_RETRIES} attempts. Rolled back."
        return result

    # ── Patch application ────────────────────────────────────────────────────

    def _apply_patches(self, patches: list[dict[str, str]]) -> list[str]:
        """Apply each patch's unified_diff to the target file. Returns applied list."""
        applied: list[str] = []
        for patch in patches:
            unified_diff = patch.get("unified_diff", "")
            fname        = patch.get("file", "")
            if not unified_diff or not fname:
                continue
            target = self._repo_path / fname
            if not target.exists():
                log(f"Patch target not found: {fname} – skipping.", "yellow")
                continue
            self._backup_file(fname, target)
            success = self._apply_unified_diff(str(target), unified_diff)
            if success:
                applied.append(fname)
                log(f"  ✓ Patched {fname}")
            else:
                log(f"  ✗ Failed to apply patch for {fname}", "yellow")
        return applied

    def _backup_file(self, rel_path: str, abs_path: Path) -> None:
        """Save a copy of the original file before patching."""
        if rel_path in self._backups:
            return  # already backed up
        fd, tmp = tempfile.mkstemp(prefix="umai_backup_")
        os.close(fd)
        shutil.copy2(str(abs_path), tmp)
        self._backups[rel_path] = tmp

    def _apply_unified_diff(self, filepath: str, unified_diff: str) -> bool:
        """
        Apply a unified diff to a file.
        Strategy:
          1. Try `patch` CLI (Unix/WSL).
          2. Fall back to Python difflib-based application.
        """
        # Write diff to temp file
        fd, diff_file = tempfile.mkstemp(suffix=".patch", prefix="umai_")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(unified_diff)
            result = subprocess.run(
                ["patch", "-p1", filepath, diff_file],
                capture_output=True, text=True, cwd=str(self._repo_path)
            )
            if result.returncode == 0:
                return True
        except FileNotFoundError:
            pass  # patch not available
        finally:
            try:
                os.unlink(diff_file)
            except OSError:
                pass

        # Python fallback: line-by-line hunk application
        return self._python_apply_diff(filepath, unified_diff)

    def _python_apply_diff(self, filepath: str, unified_diff: str) -> bool:
        """
        Minimal unified diff applicator in pure Python.
        Handles the common @@ -a,b +c,d @@ hunk format.
        """
        import re as _re
        try:
            with open(filepath, encoding="utf-8", errors="replace") as fh:
                original_lines = fh.readlines()

            result_lines = original_lines[:]
            offset = 0

            for hunk in _re.finditer(
                r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@.*?\n(.*?)(?=^@@|\Z)",
                unified_diff, _re.DOTALL | _re.MULTILINE
            ):
                orig_start = int(hunk.group(1)) - 1 + offset
                orig_count = int(hunk.group(2) or 1)
                hunk_lines = hunk.group(5).splitlines(keepends=True)

                removes = [l[1:] for l in hunk_lines if l.startswith("-")]
                adds    = [l[1:] for l in hunk_lines if l.startswith("+")]

                # Verify context matches
                actual = result_lines[orig_start:orig_start + orig_count]
                if actual[:len(removes)] == removes or not removes:
                    result_lines[orig_start:orig_start + orig_count] = adds
                    offset += len(adds) - orig_count

            with open(filepath, "w", encoding="utf-8") as fh:
                fh.writelines(result_lines)
            return True
        except Exception as exc:
            log(f"Python diff applicator failed: {exc}", "red")
            return False

    # ── Test command detection ───────────────────────────────────────────────

    def _detect_test_command(self, stacks: list[str]) -> list[str]:
        for stack in stacks:
            candidates = self._TEST_COMMANDS.get(stack, [])
            for cmd in candidates:
                exe = shutil.which(cmd[0])
                if exe:
                    log(f"Detected test command: {' '.join(cmd)}")
                    return cmd
        # Generic fallback scan
        for fallback, cmd in [
            ("pytest",  ["pytest", "--tb=short", "-q"]),
            ("python",  ["python", "-m", "pytest"]),
            ("npm",     ["npm", "test"]),
            ("cargo",   ["cargo", "test"]),
            ("go",      ["go", "test", "./..."]),
        ]:
            if shutil.which(fallback):
                # Only use if test config file exists
                markers = {
                    "pytest":  ["pytest.ini", "setup.cfg", "pyproject.toml", "conftest.py"],
                    "python":  ["setup.py", "pyproject.toml"],
                    "npm":     ["package.json"],
                    "cargo":   ["Cargo.toml"],
                    "go":      ["go.mod"],
                }
                for marker in markers.get(fallback, []):
                    if (self._repo_path / marker).exists():
                        log(f"Fallback test command: {' '.join(cmd)}")
                        return cmd
        log("No test command detected.", "yellow")
        return []

    # ── Subprocess runner ────────────────────────────────────────────────────

    def _run_command(
        self,
        cmd: list[str],
        timeout: int = 300,
    ) -> tuple[str, str, int]:
        """Run command in repo_path, return (stdout, stderr, returncode)."""
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=str(self._repo_path),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            stdout, stderr = proc.communicate(timeout=timeout)
            return stdout, stderr, proc.returncode
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate()
            return stdout or "", stderr or "", -1
        except FileNotFoundError as exc:
            return "", str(exc), -1
        except Exception as exc:
            return "", str(exc), -1

    # ── Rollback ─────────────────────────────────────────────────────────────

    def _rollback(self, result: SandboxResult) -> None:
        """
        Revert modified files.
        Priority: git checkout → manual backup restoration.
        """
        log("Rolling back changes …", "yellow")

        # Attempt git-based rollback first
        if self._git_rollback():
            log("Git rollback successful.", "green")
            self._cleanup_backups()
            result.patches_rolled_back = True
            return

        # Manual backup restoration
        restored = 0
        for rel_path, backup_tmp in list(self._backups.items()):
            target = self._repo_path / rel_path
            try:
                shutil.copy2(backup_tmp, str(target))
                restored += 1
            except Exception as exc:
                log(f"Could not restore {rel_path}: {exc}", "red")
        self._cleanup_backups()
        log(f"Manually restored {restored} file(s).", "green")
        result.patches_rolled_back = True

    def _git_rollback(self) -> bool:
        """Run `git checkout -- .` in the repo directory."""
        try:
            r = subprocess.run(
                ["git", "checkout", "--", "."],
                cwd=str(self._repo_path),
                capture_output=True, text=True, timeout=30
            )
            return r.returncode == 0
        except Exception:
            return False

    def _cleanup_backups(self) -> None:
        for tmp in self._backups.values():
            try:
                os.unlink(tmp)
            except OSError:
                pass
        self._backups.clear()

    # ── Helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _patches_to_text(patches: list[dict[str, str]]) -> str:
        parts: list[str] = []
        for p in patches:
            parts.append(
                f"--- {p.get('file', 'unknown')}\n"
                f"{p.get('unified_diff', '')}"
            )
        return "\n\n".join(parts)


# ── CLI self-test ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys, json as _json
    from diagnostic_agent import DiagnosisResult

    class _MockDiag:
        def reflect(self, *a, **kw):
            return DiagnosisResult()

    repo = sys.argv[1] if len(sys.argv) > 1 else "."
    agent = SandboxAgent(repo, _MockDiag())
    dummy = DiagnosisResult()
    result = agent.verify(dummy, {"stack": []})
    print(_json.dumps(result.to_dict(), indent=2))
