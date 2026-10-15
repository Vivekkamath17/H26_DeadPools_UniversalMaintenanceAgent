"""
inspector_agent.py
──────────────────
Deep Inspector Agent – fully deterministic, zero LLM calls.

Responsibilities
────────────────
* Clone remote GitHub repos or validate local paths.
* Auto-detect project stack from manifest files.
* Parse manifests to extract declared dependency versions.
* Walk source trees via AST (Python) or regex (other langs) to map
  every imported symbol back to its exact file path and line number.
* Return a structured `ObservedFacts` dict consumed by the DiagnosticAgent.
"""

from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ── Optional imports ────────────────────────────────────────────────────────
try:
    import toml  # type: ignore
    _HAS_TOML = True
except ImportError:
    _HAS_TOML = False

try:
    from agents.tree_sitter_inspector import TreeSitterInspector
except ImportError:
    try:
        from tree_sitter_inspector import TreeSitterInspector
    except ImportError:
        TreeSitterInspector = None  # type: ignore[assignment]

try:
    import io as _io
    from rich.console import Console
    _safe_file = _io.TextIOWrapper(
        _io.open(1, "wb", closefd=False), encoding="utf-8", errors="replace", line_buffering=True
    ) if sys.platform == "win32" else None
    console = Console(file=_safe_file, highlight=False, emoji=False)
    def log(msg: str, style: str = "cyan") -> None:
        console.print(f"[{style}][Inspector][/{style}] {msg}")
except ImportError:
    def log(msg: str, style: str = "cyan") -> None:  # type: ignore[misc]
        print(f"[Inspector] {msg}")


# ── Data structures ──────────────────────────────────────────────────────────

@dataclass
class ImportUsage:
    """Records a single import statement found in source."""
    symbol: str
    file_path: str
    line_number: int
    import_statement: str


@dataclass
class ObservedFacts:
    """All deterministic facts extracted from the target repository."""
    repo_path: str
    stack: list[str] = field(default_factory=list)
    manifests_found: list[str] = field(default_factory=list)
    dependencies: dict[str, dict[str, str]] = field(default_factory=dict)
    # {manifest_name: {package: version}}
    import_usages: list[dict[str, Any]] = field(default_factory=list)
    file_tree_summary: dict[str, int] = field(default_factory=dict)
    # {extension: file_count}
    git_info: dict[str, str] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    syntax_errors: list[dict[str, Any]] = field(default_factory=list)
    ast_findings: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "repo_path": self.repo_path,
            "stack": self.stack,
            "manifests_found": self.manifests_found,
            "dependencies": self.dependencies,
            "import_usages": self.import_usages,
            "file_tree_summary": self.file_tree_summary,
            "git_info": self.git_info,
            "errors": self.errors,
            "syntax_errors": self.syntax_errors,
            "ast_findings": self.ast_findings,
        }


# ── Main Agent Class ─────────────────────────────────────────────────────────

class DeepInspectorAgent:
    """
    Deterministic, LLM-free static analysis agent.

    Usage
    ─────
    agent = DeepInspectorAgent()
    facts = agent.inspect("https://github.com/owner/repo")
    # or
    facts = agent.inspect("/local/path/to/project")
    """

    # Directories we never descend into
    _SKIP_DIRS: frozenset[str] = frozenset({
        ".git", ".hg", ".svn", "__pycache__", "node_modules",
        ".venv", "venv", "env", ".env", "dist", "build",
        "target", "vendor", ".cargo",
    })

    def __init__(self, clone_base: str | None = None) -> None:
        self._tmp_dir: tempfile.TemporaryDirectory | None = None
        self._clone_base = clone_base  # custom base for cloned repos

    # ── Public entry point ───────────────────────────────────────────────────

    def inspect(self, repo_path_or_url: str) -> ObservedFacts:
        """Run full inspection and return ObservedFacts."""
        local_path = self._resolve_path(repo_path_or_url)
        facts = ObservedFacts(repo_path=local_path)

        log(f"Resolved repo path → {local_path}")

        self._collect_git_info(local_path, facts)
        self._detect_stack(local_path, facts)
        self._parse_manifests(local_path, facts)
        self._walk_source_tree(local_path, facts)
        self._run_tree_sitter_inspection(local_path, facts)

        log(f"Inspection complete. Stack: {facts.stack}", "green")
        return facts

    # ── Path resolution ──────────────────────────────────────────────────────

    def _resolve_path(self, path_or_url: str) -> str:
        if self._is_github_url(path_or_url):
            return self._clone_repo(path_or_url)
        p = Path(path_or_url).expanduser().resolve()
        if not p.exists():
            raise FileNotFoundError(f"Repository path does not exist: {p}")
        return str(p)

    @staticmethod
    def _is_github_url(s: str) -> bool:
        return s.startswith(("http://", "https://", "git@", "git://"))

    def _clone_repo(self, url: str) -> str:
        base = self._clone_base or tempfile.mkdtemp(prefix="umai_clone_")
        repo_name = url.rstrip("/").split("/")[-1].removesuffix(".git")
        dest = os.path.join(base, repo_name)

        if os.path.exists(dest):
            log(f"Repo already cloned at {dest}, using cached copy.")
            return dest

        log(f"Cloning {url} → {dest} …")
        result = subprocess.run(
            ["git", "clone", "--depth=1", url, dest],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"git clone failed:\n{result.stderr}"
            )
        return dest

    # ── Git metadata ─────────────────────────────────────────────────────────

    def _collect_git_info(self, path: str, facts: ObservedFacts) -> None:
        cmds = {
            "branch": ["git", "-C", path, "rev-parse", "--abbrev-ref", "HEAD"],
            "commit": ["git", "-C", path, "rev-parse", "--short", "HEAD"],
            "remote": ["git", "-C", path, "remote", "get-url", "origin"],
        }
        for key, cmd in cmds.items():
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                if r.returncode == 0:
                    facts.git_info[key] = r.stdout.strip()
            except Exception:
                pass

    # ── Stack detection ──────────────────────────────────────────────────────

    _MANIFEST_STACK_MAP: dict[str, str] = {
        "package.json":      "NodeJS",
        "requirements.txt":  "Python",
        "pyproject.toml":    "Python",
        "setup.py":          "Python",
        "setup.cfg":         "Python",
        "Cargo.toml":        "Rust",
        "go.mod":            "Go",
        "pom.xml":           "Java",
        "build.gradle":      "Java",
        "build.gradle.kts":  "Java",
        "Gemfile":           "Ruby",
        "composer.json":     "PHP",
    }

    def _detect_stack(self, path: str, facts: ObservedFacts) -> None:
        stacks: set[str] = set()
        found_manifests: list[str] = []

        for root, dirs, files in os.walk(path):
            # Prune skip dirs in-place
            dirs[:] = [d for d in dirs if d not in self._SKIP_DIRS]
            for f in files:
                if f in self._MANIFEST_STACK_MAP:
                    rel = os.path.relpath(os.path.join(root, f), path)
                    found_manifests.append(rel)
                    stacks.add(self._MANIFEST_STACK_MAP[f])

        facts.stack = sorted(stacks)
        facts.manifests_found = sorted(found_manifests)
        log(f"Detected stacks: {facts.stack}")
        log(f"Manifests: {facts.manifests_found}")

    # ── Manifest parsing ─────────────────────────────────────────────────────

    def _parse_manifests(self, path: str, facts: ObservedFacts) -> None:
        for manifest_rel in facts.manifests_found:
            manifest_abs = os.path.join(path, manifest_rel)
            fname = os.path.basename(manifest_rel)
            try:
                deps = self._parse_single_manifest(fname, manifest_abs)
                if deps:
                    facts.dependencies[manifest_rel] = deps
                    log(f"Parsed {len(deps)} deps from {manifest_rel}")
            except Exception as exc:
                facts.errors.append(f"Manifest parse error [{manifest_rel}]: {exc}")
                log(f"⚠ Could not parse {manifest_rel}: {exc}", "yellow")

    def _parse_single_manifest(self, fname: str, fpath: str) -> dict[str, str]:
        if fname == "package.json":
            return self._parse_package_json(fpath)
        if fname == "requirements.txt":
            return self._parse_requirements_txt(fpath)
        if fname in ("pyproject.toml", "Cargo.toml"):
            return self._parse_toml(fname, fpath)
        if fname == "go.mod":
            return self._parse_go_mod(fpath)
        if fname in ("setup.py", "setup.cfg"):
            return self._parse_setup(fname, fpath)
        if fname == "pom.xml":
            return self._parse_pom_xml(fpath)
        if fname == "Gemfile":
            return self._parse_gemfile(fpath)
        return {}

    # ·· package.json ·········────────────────────────────────────────────────
    def _parse_package_json(self, fpath: str) -> dict[str, str]:
        with open(fpath, encoding="utf-8", errors="replace") as fh:
            data = json.load(fh)
        result: dict[str, str] = {}
        for section in ("dependencies", "devDependencies", "peerDependencies"):
            result.update(data.get(section, {}))
        return result

    # ·· requirements.txt ·····────────────────────────────────────────────────
    def _parse_requirements_txt(self, fpath: str) -> dict[str, str]:
        result: dict[str, str] = {}
        with open(fpath, encoding="utf-8", errors="replace") as fh:
            for raw_line in fh:
                line = raw_line.strip()
                if not line or line.startswith(("#", "-r", "--")):
                    continue
                m = re.match(r"^([A-Za-z0-9_\-\.]+)\s*([><=!~^].*)?$", line)
                if m:
                    result[m.group(1)] = (m.group(2) or "").strip()
        return result

    # ·· pyproject.toml / Cargo.toml ··────────────────────────────────────────
    def _parse_toml(self, fname: str, fpath: str) -> dict[str, str]:
        if not _HAS_TOML:
            # fallback: naïve regex
            return self._parse_toml_regex(fpath)
        with open(fpath, encoding="utf-8", errors="replace") as fh:
            data = toml.load(fh)
        if fname == "pyproject.toml":
            # PEP 621 / poetry
            deps: dict[str, str] = {}
            project = data.get("project", {})
            deps.update({
                re.split(r"[><=!~^]", d)[0].strip(): d
                for d in project.get("dependencies", [])
            })
            poetry_deps = data.get("tool", {}).get("poetry", {}).get("dependencies", {})
            deps.update({k: str(v) for k, v in poetry_deps.items() if k != "python"})
            return deps
        else:  # Cargo.toml
            result: dict[str, str] = {}
            for section in ("dependencies", "dev-dependencies", "build-dependencies"):
                for pkg, spec in data.get(section, {}).items():
                    result[pkg] = spec if isinstance(spec, str) else str(spec.get("version", ""))
            return result

    def _parse_toml_regex(self, fpath: str) -> dict[str, str]:
        result: dict[str, str] = {}
        with open(fpath, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                m = re.match(r'^([A-Za-z0-9_\-]+)\s*=\s*"([^"]+)"', line)
                if m:
                    result[m.group(1)] = m.group(2)
        return result

    # ·· go.mod ···············────────────────────────────────────────────────
    def _parse_go_mod(self, fpath: str) -> dict[str, str]:
        result: dict[str, str] = {}
        with open(fpath, encoding="utf-8", errors="replace") as fh:
            in_require = False
            for line in fh:
                line = line.strip()
                if line.startswith("require ("):
                    in_require = True
                    continue
                if in_require:
                    if line == ")":
                        in_require = False
                        continue
                    parts = line.split()
                    if len(parts) >= 2:
                        result[parts[0]] = parts[1]
                elif line.startswith("require "):
                    parts = line.split()
                    if len(parts) >= 3:
                        result[parts[1]] = parts[2]
        return result

    # ·· setup.py / setup.cfg ·────────────────────────────────────────────────
    def _parse_setup(self, fname: str, fpath: str) -> dict[str, str]:
        result: dict[str, str] = {}
        with open(fpath, encoding="utf-8", errors="replace") as fh:
            content = fh.read()
        for m in re.finditer(r"['\"]([A-Za-z0-9_\-\.]+)\s*([><=!~^][^'\"]*)?['\"]", content):
            pkg = m.group(1)
            ver = (m.group(2) or "").strip()
            if pkg and not pkg.startswith(("http", "git+")):
                result[pkg] = ver
        return result

    # ·· pom.xml ··············────────────────────────────────────────────────
    def _parse_pom_xml(self, fpath: str) -> dict[str, str]:
        result: dict[str, str] = {}
        with open(fpath, encoding="utf-8", errors="replace") as fh:
            content = fh.read()
        deps = re.findall(
            r"<dependency>.*?<artifactId>(.*?)</artifactId>.*?(?:<version>(.*?)</version>)?.*?</dependency>",
            content, re.DOTALL
        )
        for artifact, version in deps:
            result[artifact.strip()] = version.strip()
        return result

    # ·· Gemfile ··············────────────────────────────────────────────────
    def _parse_gemfile(self, fpath: str) -> dict[str, str]:
        result: dict[str, str] = {}
        with open(fpath, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                m = re.match(r"^\s*gem\s+['\"]([^'\"]+)['\"](?:,\s*['\"]([^'\"]+)['\"])?", line)
                if m:
                    result[m.group(1)] = m.group(2) or ""
        return result

    # ── Source tree walk ─────────────────────────────────────────────────────

    def _walk_source_tree(self, path: str, facts: ObservedFacts) -> None:
        ext_count: dict[str, int] = {}
        usages: list[dict[str, Any]] = []

        for root, dirs, files in os.walk(path):
            dirs[:] = [d for d in dirs if d not in self._SKIP_DIRS]
            for fname in files:
                ext = Path(fname).suffix.lower()
                ext_count[ext] = ext_count.get(ext, 0) + 1
                fabs = os.path.join(root, fname)
                frel = os.path.relpath(fabs, path)

                if ext == ".py":
                    usages.extend(self._extract_python_imports(fabs, frel))
                elif ext in (".js", ".ts", ".mjs", ".cjs"):
                    usages.extend(self._extract_js_imports(fabs, frel))
                elif ext == ".go":
                    usages.extend(self._extract_go_imports(fabs, frel))
                elif ext == ".rs":
                    usages.extend(self._extract_rust_imports(fabs, frel))

        facts.file_tree_summary = ext_count
        facts.import_usages = usages
        log(f"Found {len(usages)} import statements across {sum(ext_count.values())} files.")

    # ·· Python AST import extraction ·────────────────────────────────────────
    def _extract_python_imports(self, fabs: str, frel: str) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        try:
            with open(fabs, encoding="utf-8", errors="replace") as fh:
                source = fh.read()
            tree = ast.parse(source, filename=fabs)
        except SyntaxError:
            return results
        except Exception:
            return results

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    results.append({
                        "symbol": alias.name,
                        "file_path": frel,
                        "line_number": node.lineno,
                        "import_statement": f"import {alias.name}",
                    })
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    stmt = f"from {module} import {alias.name}"
                    results.append({
                        "symbol": f"{module}.{alias.name}" if module else alias.name,
                        "file_path": frel,
                        "line_number": node.lineno,
                        "import_statement": stmt,
                    })
        return results

    # ·· JS/TS regex import extraction ·───────────────────────────────────────
    def _extract_js_imports(self, fabs: str, frel: str) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        patterns = [
            re.compile(r"""(?:import|require)\s*\(?['"]([^'"]+)['"]\)?"""),
            re.compile(r"""from\s+['"]([^'"]+)['"]"""),
        ]
        try:
            with open(fabs, encoding="utf-8", errors="replace") as fh:
                for lineno, line in enumerate(fh, 1):
                    for pat in patterns:
                        for m in pat.finditer(line):
                            results.append({
                                "symbol": m.group(1),
                                "file_path": frel,
                                "line_number": lineno,
                                "import_statement": line.strip(),
                            })
        except Exception:
            pass
        return results

    # ·· Go import extraction ··───────────────────────────────────────────────
    def _extract_go_imports(self, fabs: str, frel: str) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        try:
            with open(fabs, encoding="utf-8", errors="replace") as fh:
                in_import = False
                for lineno, line in enumerate(fh, 1):
                    stripped = line.strip()
                    if stripped == "import (":
                        in_import = True
                        continue
                    if in_import:
                        if stripped == ")":
                            in_import = False
                            continue
                        m = re.search(r'"([^"]+)"', stripped)
                        if m:
                            results.append({
                                "symbol": m.group(1),
                                "file_path": frel,
                                "line_number": lineno,
                                "import_statement": stripped,
                            })
                    elif stripped.startswith("import "):
                        m = re.search(r'"([^"]+)"', stripped)
                        if m:
                            results.append({
                                "symbol": m.group(1),
                                "file_path": frel,
                                "line_number": lineno,
                                "import_statement": stripped,
                            })
        except Exception:
            pass
        return results

    # ·· Rust use extraction ···───────────────────────────────────────────────
    def _extract_rust_imports(self, fabs: str, frel: str) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        pat = re.compile(r"^\s*use\s+([\w::{}, *]+);")
        try:
            with open(fabs, encoding="utf-8", errors="replace") as fh:
                for lineno, line in enumerate(fh, 1):
                    m = pat.match(line)
                    if m:
                        results.append({
                            "symbol": m.group(1),
                            "file_path": frel,
                            "line_number": lineno,
                            "import_statement": line.strip(),
                        })
        except Exception:
            pass
        return results

    # ·· Tree-Sitter Integration ··············································
    def _run_tree_sitter_inspection(self, local_path: str, facts: ObservedFacts) -> None:
        """Run deep AST inspection with Tree-Sitter if available."""
        if TreeSitterInspector is None:
            return

        try:
            ts_inspector = TreeSitterInspector()
            if not ts_inspector.is_available:
                return

            log("Running Tree-Sitter AST inspection across codebase ...")
            report = ts_inspector.scan_directory(local_path)
            facts.ast_findings = report
            facts.syntax_errors = report.get("syntax_errors", [])

            # Surface syntax errors in facts.errors so DiagnosticAgent directly sees them
            for err in facts.syntax_errors:
                msg = f"AST Syntax Error in {err['file_path']}:{err['line_number']} -> {err['message']}"
                if msg not in facts.errors:
                    facts.errors.append(msg)

            # Augment import usages with AST-discovered imports
            existing_locs = {f"{u.get('file_path')}:{u.get('line_number')}" for u in facts.import_usages}
            for ast_imp in report.get("ast_imports", []):
                loc_key = f"{ast_imp.get('file_path')}:{ast_imp.get('line_number')}"
                if loc_key not in existing_locs:
                    facts.import_usages.append({
                        "symbol": ast_imp.get("symbol", ""),
                        "file_path": ast_imp.get("file_path", ""),
                        "line_number": ast_imp.get("line_number", 0),
                        "import_statement": ast_imp.get("import_statement", ""),
                        "ast_byte_range": [ast_imp.get("start_byte", 0), ast_imp.get("end_byte", 0)],
                    })
                    existing_locs.add(loc_key)

        except Exception as exc:
            log(f"Tree-Sitter inspection encountered an issue: {exc}", "yellow")


# ── CLI self-test ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys, json as _json
    target = sys.argv[1] if len(sys.argv) > 1 else "."
    agent = DeepInspectorAgent()
    facts = agent.inspect(target)
    print(_json.dumps(facts.to_dict(), indent=2, default=str))
