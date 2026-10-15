"""
pr_agent.py
───────────
Interactive PR Agent with strict user confirmation gates.

Responsibilities:
* Inspect proposed / verified maintenance patches.
* Display a formatted patch summary and change preview to the user.
* Enforce explicit user gate: requires interactive confirmation [y/N] before any action.
* If confirmed:
    - Create a dedicated Git branch (fix/agent-maintenance-<timestamp>).
    - Stage modified files and create a clean, descriptive commit.
    - Check for GITHUB_TOKEN or GitHub CLI (`gh`) to push and open a Pull Request.
    - Gracefully provide exact manual push commands if credentials are not present.
"""

from __future__ import annotations

import datetime
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ── Logging helper ───────────────────────────────────────────────────────────
try:
    import io as _io
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    _safe_file = _io.TextIOWrapper(
        _io.open(1, "wb", closefd=False), encoding="utf-8", errors="replace", line_buffering=True
    ) if sys.platform == "win32" else None
    console = Console(file=_safe_file, highlight=False, emoji=False)
    def log(msg: str, style: str = "cyan") -> None:
        console.print(f"[{style}][PRAgent][/{style}] {msg}")
except ImportError:
    def log(msg: str, style: str = "cyan") -> None:  # type: ignore[misc]
        print(f"[PRAgent] {msg}")


@dataclass
class PRResult:
    """Outcome of the interactive PR workflow."""
    status: str            # "aborted_by_user", "committed_locally", "pr_created", "error"
    branch_name: str = ""
    commit_sha: str = ""
    pr_url: str = ""
    message: str = ""
    files_changed: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "branch_name": self.branch_name,
            "commit_sha": self.commit_sha,
            "pr_url": self.pr_url,
            "message": self.message,
            "files_changed": self.files_changed,
        }


class InteractivePRAgent:
    """
    Autonomous Git & GitHub PR workflow agent guarded by an explicit user confirmation gate.
    """

    def __init__(self, repo_dir: str) -> None:
        self.repo_dir = str(Path(repo_dir).resolve())

    def create_pr_workflow(
        self,
        problem_summary: str,
        patches: list[dict[str, Any]],
        pr_title: str | None = None,
        pr_body: str | None = None,
        interactive: bool = True,
        auto_confirm: bool = False,
    ) -> PRResult:
        """
        Main entry point for interactive PR creation.
        """
        if not patches:
            log("No patches to commit or publish. Skipping PR workflow.", "yellow")
            return PRResult(status="no_patches", message="No patches provided.")

        title = pr_title or "fix(maintenance): autonomous dependency & syntax repairs"
        body = pr_body or self._generate_pr_body(problem_summary, patches)

        # ── Step 1: Display change summary to the user ───────────────────────
        self._display_summary(title, problem_summary, patches)

        # ── Step 2: Explicit User Gate ───────────────────────────────────────
        confirmed = False
        if auto_confirm:
            log("Auto-confirm flag enabled: proceeding without user prompt.", "yellow")
            confirmed = True
        elif interactive:
            confirmed = self._prompt_user()
        else:
            log("Non-interactive mode and auto-confirm disabled. Aborting PR workflow for safety.", "yellow")
            return PRResult(status="aborted_non_interactive", message="Interactive prompt not available.")

        if not confirmed:
            log("PR workflow aborted by user. Zero remote or git changes made.", "yellow")
            return PRResult(
                status="aborted_by_user",
                message="User declined to create a branch or open a pull request.",
            )

        # ── Step 3: Git Branch and Commit ────────────────────────────────────
        return self._execute_git_workflow(title, body, patches)

    # ── User Prompt Gate ─────────────────────────────────────────────────────

    def _display_summary(self, title: str, problem_summary: str, patches: list[dict[str, Any]]) -> None:
        """Present a clear preview of the proposed branch and PR."""
        try:
            from rich.console import Console
            from rich.table import Table
            c = Console()
            t = Table(title="Proposed Maintenance Patches", show_header=True, header_style="bold cyan")
            t.add_column("File", style="yellow")
            t.add_column("Description", style="white")

            for p in patches:
                f_name = p.get("file", "unknown")
                desc = p.get("description", "Automated patch")
                t.add_row(f_name, desc[:80])
            c.print(t)
            c.print(f"[bold cyan]PR Title:[/] {title}")
        except Exception:
            print("\nProposed Maintenance Patches:")
            for p in patches:
                print(f"  • {p.get('file')}: {p.get('description', '')[:70]}")
            print(f"PR Title: {title}\n")

    def _prompt_user(self) -> bool:
        """Prompt the user with [y/N] strictly requiring affirmative consent."""
        prompt_text = "\n[?] Do you want to create a branch, commit these fixes, and open a PR on GitHub? [y/N]: "
        try:
            # Check if stdin is an interactive TTY
            if not sys.stdin.isatty():
                log("Stdin is not an interactive terminal. Defaulting to safe abort.", "yellow")
                return False

            reply = input(prompt_text).strip().lower()
            return reply in ("y", "yes")
        except (KeyboardInterrupt, EOFError):
            print("\nAborted.")
            return False

    # ── Git Execution ────────────────────────────────────────────────────────

    def _execute_git_workflow(
        self,
        title: str,
        body: str,
        patches: list[dict[str, Any]],
    ) -> PRResult:
        """Create a new local branch, stage changes, commit, and attempt PR creation."""
        # 1. Verify git repository
        if not self._run_git(["rev-parse", "--is-inside-work-tree"]).get("success"):
            log("Target directory is not a valid git repository. Initializing local git...", "yellow")
            self._run_git(["init"])

        # 2. Identify default/base branch
        base_branch = "main"
        r_branch = self._run_git(["rev-parse", "--abbrev-ref", "HEAD"])
        if r_branch.get("success") and r_branch.get("stdout"):
            current = r_branch["stdout"].strip()
            if current and current != "HEAD":
                base_branch = current

        # 3. Create unique fix branch
        timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        branch_name = f"fix/agent-maintenance-{timestamp}"
        log(f"Creating branch: {branch_name} (base: {base_branch}) ...")

        r_co = self._run_git(["checkout", "-b", branch_name])
        if not r_co.get("success"):
            # If already on branch or error
            log(f"Could not create branch {branch_name}: {r_co.get('stderr')}", "red")
            return PRResult(status="error", message=f"Git checkout failed: {r_co.get('stderr')}")

        # 4. Apply patches if not already applied
        self._apply_patches_if_needed(patches)

        # 5. Stage modified files
        self._run_git(["add", "-A"])

        # Check what files are changed
        r_status = self._run_git(["diff", "--cached", "--name-only"])
        changed_files = [f for f in r_status.get("stdout", "").splitlines() if f.strip()]

        if not changed_files:
            log("No modified files staged for commit. Working tree is clean.", "yellow")
            return PRResult(
                status="committed_locally",
                branch_name=branch_name,
                message="Working tree already clean; no new commit created.",
            )

        # 6. Commit changes locally
        commit_msg = f"{title}\n\nAutomated maintenance by Universal Maintenance Agent.\n\nChanges:\n"
        for p in patches:
            commit_msg += f"- {p.get('file')}: {p.get('description', '')}\n"

        log(f"Committing {len(changed_files)} changed file(s) ...")
        r_commit = self._run_git(["commit", "-m", commit_msg])
        if not r_commit.get("success"):
            log(f"Commit failed: {r_commit.get('stderr')}", "red")
            return PRResult(status="error", message=f"Git commit failed: {r_commit.get('stderr')}")

        r_sha = self._run_git(["rev-parse", "HEAD"])
        commit_sha = r_sha.get("stdout", "").strip()[:8]
        log(f"Committed locally as {commit_sha} on branch '{branch_name}'.", "green")

        # 7. Attempt GitHub PR Creation
        pr_result = self._publish_to_github(branch_name, base_branch, title, body, changed_files, commit_sha)
        return pr_result

    def _apply_patches_if_needed(self, patches: list[dict[str, Any]]) -> None:
        """Apply unified diffs from patches if not yet reflected on disk."""
        for p in patches:
            diff_text = p.get("unified_diff", "").strip()
            if not diff_text:
                continue
            # Try git apply
            proc = subprocess.run(
                ["git", "-C", self.repo_dir, "apply", "--ignore-whitespace", "--recount", "-"],
                input=diff_text,
                text=True,
                capture_output=True,
            )
            if proc.returncode == 0:
                log(f"Applied patch to {p.get('file', 'file')}", "green")

    # ── Remote Publishing ────────────────────────────────────────────────────

    def _publish_to_github(
        self,
        branch_name: str,
        base_branch: str,
        title: str,
        body: str,
        changed_files: list[str],
        commit_sha: str,
    ) -> PRResult:
        """Attempt to push branch and open PR via GITHUB_TOKEN or gh CLI."""
        token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        remote_url = self._get_remote_url()

        # Check if remote URL points to GitHub
        owner_repo = self._parse_github_owner_repo(remote_url)

        # A. Try PyGithub if GITHUB_TOKEN is present and owner_repo is known
        if token and owner_repo:
            log(f"GITHUB_TOKEN found. Pushing branch and creating PR on GitHub ({owner_repo}) ...")
            try:
                # Push branch
                push_url = f"https://x-access-token:{token}@github.com/{owner_repo}.git"
                r_push = subprocess.run(
                    ["git", "-C", self.repo_dir, "push", "-u", push_url, branch_name],
                    capture_output=True, text=True, timeout=60,
                )
                if r_push.returncode == 0:
                    from github import Github, Auth
                    gh = Github(auth=Auth.Token(token))
                    repo = gh.get_repo(owner_repo)
                    pr = repo.create_pull(
                        title=title,
                        body=body,
                        head=branch_name,
                        base=base_branch,
                    )
                    log(f"Pull Request created successfully! URL: {pr.html_url}", "green")
                    return PRResult(
                        status="pr_created",
                        branch_name=branch_name,
                        commit_sha=commit_sha,
                        pr_url=pr.html_url,
                        message=f"PR created: {pr.html_url}",
                        files_changed=changed_files,
                    )
                else:
                    log(f"git push failed: {r_push.stderr.strip()}", "yellow")
            except Exception as exc:
                log(f"PyGithub PR creation encountered an issue: {exc}", "yellow")

        # B. Try GitHub CLI (gh)
        if shutil.which("gh") and owner_repo:
            log("Attempting PR creation via GitHub CLI (`gh pr create`) ...")
            try:
                # First push branch to origin
                subprocess.run(
                    ["git", "-C", self.repo_dir, "push", "-u", "origin", branch_name],
                    capture_output=True, text=True, timeout=60,
                )
                r_gh = subprocess.run(
                    [
                        "gh", "pr", "create",
                        "--title", title,
                        "--body", body,
                        "--head", branch_name,
                        "--base", base_branch,
                    ],
                    cwd=self.repo_dir,
                    capture_output=True, text=True, timeout=60,
                )
                if r_gh.returncode == 0:
                    pr_url = r_gh.stdout.strip()
                    log(f"Pull Request created successfully via gh CLI! URL: {pr_url}", "green")
                    return PRResult(
                        status="pr_created",
                        branch_name=branch_name,
                        commit_sha=commit_sha,
                        pr_url=pr_url,
                        message=f"PR created via gh: {pr_url}",
                        files_changed=changed_files,
                    )
            except Exception as exc:
                log(f"gh CLI failed: {exc}", "yellow")

        # C. Fallback: Changes committed locally, provide exact manual commands
        log("No remote GITHUB_TOKEN or authenticated gh CLI detected.", "yellow")
        log(f"Local branch '{branch_name}' is safely committed at {commit_sha}.", "green")
        print("\nTo push this branch and create a PR manually, run:")
        print(f"  git push -u origin {branch_name}")
        print(f'  gh pr create --title "{title}" --body "Automated maintenance fixes"\n')

        return PRResult(
            status="committed_locally",
            branch_name=branch_name,
            commit_sha=commit_sha,
            message=(
                f"Changes committed to branch '{branch_name}' ({commit_sha}). "
                "Set GITHUB_TOKEN to enable automatic remote PR creation."
            ),
            files_changed=changed_files,
        )

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _generate_pr_body(self, problem_summary: str, patches: list[dict[str, Any]]) -> str:
        lines = [
            "## 🤖 Automated Maintenance Pull Request",
            "",
            "### Summary of Identified Issues",
            problem_summary.strip() or "General codebase and dependency maintenance.",
            "",
            "### Verified Patches Included",
        ]
        for p in patches:
            lines.append(f"- **`{p.get('file', 'manifest')}`**: {p.get('description', 'Patch')}")
        lines.extend([
            "",
            "---",
            "*Generated autonomously by [Universal Maintenance Agent](https://agentskills.io)*",
        ])
        return "\n".join(lines)

    def _get_remote_url(self) -> str:
        r = self._run_git(["remote", "get-url", "origin"])
        return r.get("stdout", "").strip() if r.get("success") else ""

    def _parse_github_owner_repo(self, url: str) -> str | None:
        if not url:
            return None
        # Match github.com/owner/repo or git@github.com:owner/repo
        m = re.search(r"github\.com[/:]([\w.-]+)/([\w.-]+?)(?:\.git)?$", url)
        if m:
            return f"{m.group(1)}/{m.group(2)}"
        return None

    def _run_git(self, args: list[str]) -> dict[str, Any]:
        try:
            p = subprocess.run(
                ["git", "-C", self.repo_dir] + args,
                capture_output=True, text=True, timeout=30,
            )
            return {
                "success": p.returncode == 0,
                "returncode": p.returncode,
                "stdout": p.stdout,
                "stderr": p.stderr,
            }
        except Exception as exc:
            return {"success": False, "error": str(exc)}
