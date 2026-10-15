"""
tree_sitter_inspector.py
─────────────────────────
Multi-language AST Inspector using Tree-Sitter.

Responsibilities:
* Multi-language syntax and import parsing (Python, JavaScript, TypeScript).
* Graceful fallback when Tree-Sitter or language grammars are unavailable.
* Deep detection of syntax errors (ERROR nodes, missing tokens) with exact byte/line ranges.
* Precise extraction of explicit import declarations and dependencies.
* Feeds structured AST findings directly into ObservedFacts.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ── Logging helper ───────────────────────────────────────────────────────────
try:
    import io as _io
    import sys
    from rich.console import Console
    _safe_file = _io.TextIOWrapper(
        _io.open(1, "wb", closefd=False), encoding="utf-8", errors="replace", line_buffering=True
    ) if sys.platform == "win32" else None
    console = Console(file=_safe_file, highlight=False, emoji=False)
    def log(msg: str, style: str = "cyan") -> None:
        console.print(f"[{style}][TreeSitter][/{style}] {msg}")
except ImportError:
    def log(msg: str, style: str = "cyan") -> None:  # type: ignore[misc]
        print(f"[TreeSitter] {msg}")


# ── Data structures ──────────────────────────────────────────────────────────

@dataclass
class SyntaxErrorFinding:
    """Represents a syntax anomaly or parse error identified by Tree-Sitter."""
    file_path: str
    line_number: int          # 1-indexed
    column_number: int        # 0-indexed
    start_byte: int
    end_byte: int
    error_node_type: str      # e.g. "ERROR", "MISSING"
    snippet: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "line_number": self.line_number,
            "column_number": self.column_number,
            "start_byte": self.start_byte,
            "end_byte": self.end_byte,
            "error_node_type": self.error_node_type,
            "snippet": self.snippet,
            "message": self.message,
        }


@dataclass
class ASTImportFinding:
    """Represents an import declaration mapped with exact AST byte ranges."""
    symbol: str
    file_path: str
    line_number: int          # 1-indexed
    start_byte: int
    end_byte: int
    import_statement: str
    language: str
    module: str = ""
    is_relative: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "start_byte": self.start_byte,
            "end_byte": self.end_byte,
            "import_statement": self.import_statement,
            "language": self.language,
            "module": self.module,
            "is_relative": self.is_relative,
        }


# ── TreeSitterInspector Agent ────────────────────────────────────────────────

class TreeSitterInspector:
    """
    Robust multi-language AST inspector backed by Tree-Sitter.
    Gracefully degrades if parsers are unavailable.
    """

    _SKIP_DIRS: frozenset[str] = frozenset({
        ".git", ".hg", ".svn", "__pycache__", "node_modules",
        ".venv", "venv", "env", ".env", "dist", "build",
        "target", "vendor", ".cargo",
    })

    def __init__(self) -> None:
        self._languages: dict[str, Any] = {}
        self._parsers: dict[str, Any] = {}
        self._initialized = False
        self._init_tree_sitter()

    def _init_tree_sitter(self) -> None:
        """Initialize available tree-sitter parsers safely."""
        try:
            import tree_sitter
            from tree_sitter import Language, Parser
        except ImportError:
            log("tree-sitter core package not installed. AST features will use fallback.", "yellow")
            return

        # Python parser
        try:
            import tree_sitter_python
            py_lang = Language(tree_sitter_python.language())
            self._languages["python"] = py_lang
            self._parsers["python"] = Parser(py_lang)
        except Exception as exc:
            log(f"tree-sitter-python unavailable: {exc}", "yellow")

        # JavaScript parser
        try:
            import tree_sitter_javascript
            js_lang = Language(tree_sitter_javascript.language())
            self._languages["javascript"] = js_lang
            self._parsers["javascript"] = Parser(js_lang)
        except Exception:
            pass

        # TypeScript parser
        try:
            import tree_sitter_typescript
            # tree_sitter_typescript provides language_typescript and language_tsx
            ts_lang_func = getattr(tree_sitter_typescript, "language_typescript", None) or getattr(tree_sitter_typescript, "language", None)
            if ts_lang_func:
                ts_lang = Language(ts_lang_func())
                self._languages["typescript"] = ts_lang
                self._parsers["typescript"] = Parser(ts_lang)
        except Exception:
            pass

        self._initialized = len(self._parsers) > 0
        if self._initialized:
            log(f"Parsers active for: {list(self._parsers.keys())}", "green")
        else:
            log("No tree-sitter language parsers loaded.", "yellow")

    @property
    def is_available(self) -> bool:
        return self._initialized

    def get_supported_languages(self) -> list[str]:
        return list(self._parsers.keys())

    # ── File Analysis ────────────────────────────────────────────────────────

    def parse_file(self, abs_path: str, rel_path: str) -> tuple[list[SyntaxErrorFinding], list[ASTImportFinding]]:
        """
        Parse a single file using the appropriate language parser.
        Returns: (syntax_errors, ast_imports)
        """
        ext = Path(abs_path).suffix.lower()
        lang_key = self._detect_language(ext)

        if not lang_key or lang_key not in self._parsers:
            return [], []

        try:
            with open(abs_path, "rb") as fh:
                code_bytes = fh.read()
        except Exception as exc:
            log(f"Failed to read {rel_path}: {exc}", "yellow")
            return [], []

        parser = self._parsers[lang_key]
        try:
            tree = parser.parse(code_bytes)
        except Exception as exc:
            log(f"Parse exception for {rel_path}: {exc}", "yellow")
            return [], []

        syntax_errors: list[SyntaxErrorFinding] = []
        if tree.root_node.has_error:
            syntax_errors = self._collect_syntax_errors(tree.root_node, code_bytes, rel_path)

        ast_imports: list[ASTImportFinding] = []
        if lang_key == "python":
            ast_imports = self._extract_python_ast_imports(tree.root_node, code_bytes, rel_path)
        elif lang_key in ("javascript", "typescript"):
            ast_imports = self._extract_js_ast_imports(tree.root_node, code_bytes, rel_path, lang_key)

        return syntax_errors, ast_imports

    def _detect_language(self, ext: str) -> str | None:
        if ext == ".py":
            return "python"
        if ext in (".js", ".jsx", ".mjs", ".cjs"):
            return "javascript"
        if ext in (".ts", ".tsx"):
            return "typescript" if "typescript" in self._parsers else "javascript"
        return None

    # ── Syntax Error Extraction ──────────────────────────────────────────────

    def _collect_syntax_errors(
        self,
        node: Any,
        code_bytes: bytes,
        rel_path: str,
        max_errors: int = 50,
    ) -> list[SyntaxErrorFinding]:
        """Traverse AST nodes recursively to extract ERROR or MISSING nodes."""
        errors: list[SyntaxErrorFinding] = []

        def traverse(curr: Any) -> None:
            if len(errors) >= max_errors:
                return

            if curr.type == "ERROR" or curr.is_missing:
                start_byte = curr.start_byte
                end_byte = max(curr.end_byte, start_byte + 1)
                snippet_bytes = code_bytes[max(0, start_byte - 20):min(len(code_bytes), end_byte + 30)]
                snippet = snippet_bytes.decode("utf-8", errors="replace").replace("\r", "").strip()

                line_num = curr.start_point.row + 1   # 1-indexed
                col_num = curr.start_point.column

                msg = (
                    f"Syntax error ({curr.type}) at line {line_num}:{col_num}. "
                    f"Malformed token: {code_bytes[curr.start_byte:curr.end_byte].decode('utf-8', errors='replace')!r}"
                )

                errors.append(
                    SyntaxErrorFinding(
                        file_path=rel_path,
                        line_number=line_num,
                        column_number=col_num,
                        start_byte=curr.start_byte,
                        end_byte=curr.end_byte,
                        error_node_type=curr.type if curr.type == "ERROR" else "MISSING",
                        snippet=snippet,
                        message=msg,
                    )
                )

            for child in curr.children:
                traverse(child)

        traverse(node)
        return errors

    # ── Python AST Import Extraction ─────────────────────────────────────────

    def _extract_python_ast_imports(
        self,
        root_node: Any,
        code_bytes: bytes,
        rel_path: str,
    ) -> list[ASTImportFinding]:
        """Extract all Python imports using Tree-Sitter AST."""
        findings: list[ASTImportFinding] = []

        def get_text(node: Any) -> str:
            return code_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace").strip()

        def visit(node: Any) -> None:
            # 1. Plain import statement: `import a, b as c`
            if node.type == "import_statement":
                stmt_text = get_text(node)
                line_no = node.start_point.row + 1
                for child in node.children:
                    if child.type == "dotted_name":
                        symbol = get_text(child)
                        findings.append(
                            ASTImportFinding(
                                symbol=symbol,
                                file_path=rel_path,
                                line_number=line_no,
                                start_byte=node.start_byte,
                                end_byte=node.end_byte,
                                import_statement=stmt_text,
                                language="python",
                                module=symbol,
                                is_relative=False,
                            )
                        )
                    elif child.type == "aliased_import":
                        name_node = child.child_by_field_name("name")
                        symbol = get_text(name_node) if name_node else get_text(child)
                        findings.append(
                            ASTImportFinding(
                                symbol=symbol,
                                file_path=rel_path,
                                line_number=line_no,
                                start_byte=node.start_byte,
                                end_byte=node.end_byte,
                                import_statement=stmt_text,
                                language="python",
                                module=symbol,
                                is_relative=False,
                            )
                        )

            # 2. From import statement: `from foo.bar import baz` or `from . import x`
            elif node.type == "import_from_statement":
                stmt_text = get_text(node)
                line_no = node.start_point.row + 1

                # Detect module or relative dots
                module_name = ""
                is_rel = False
                for child in node.children:
                    if child.type == "relative_import":
                        is_rel = True
                        module_name = get_text(child)
                    elif child.type == "dotted_name":
                        # If this is the module name before 'import'
                        if not module_name:
                            module_name = get_text(child)

                # Extract imported symbols
                for child in node.children:
                    if child.type in ("dotted_name", "identifier") and child != node.child_by_field_name("module_name"):
                        # Ensure we don't treat the module name itself as the imported symbol
                        sym_name = get_text(child)
                        if sym_name and sym_name != module_name and sym_name not in ("from", "import"):
                            full_sym = f"{module_name}.{sym_name}" if module_name and not is_rel else sym_name
                            findings.append(
                                ASTImportFinding(
                                    symbol=full_sym,
                                    file_path=rel_path,
                                    line_number=line_no,
                                    start_byte=node.start_byte,
                                    end_byte=node.end_byte,
                                    import_statement=stmt_text,
                                    language="python",
                                    module=module_name,
                                    is_relative=is_rel,
                                )
                            )
                    elif child.type == "aliased_import":
                        name_node = child.child_by_field_name("name")
                        sym_name = get_text(name_node) if name_node else get_text(child)
                        full_sym = f"{module_name}.{sym_name}" if module_name and not is_rel else sym_name
                        findings.append(
                            ASTImportFinding(
                                symbol=full_sym,
                                file_path=rel_path,
                                line_number=line_no,
                                start_byte=node.start_byte,
                                end_byte=node.end_byte,
                                import_statement=stmt_text,
                                language="python",
                                module=module_name,
                                is_relative=is_rel,
                            )
                        )

            for child in node.children:
                visit(child)

        visit(root_node)
        return findings

    # ── JS/TS AST Import Extraction ──────────────────────────────────────────

    def _extract_js_ast_imports(
        self,
        root_node: Any,
        code_bytes: bytes,
        rel_path: str,
        lang: str,
    ) -> list[ASTImportFinding]:
        """Extract imports, require() calls, and exports from JavaScript / TypeScript AST."""
        findings: list[ASTImportFinding] = []

        def get_text(node: Any) -> str:
            return code_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace").strip()

        def visit(node: Any) -> None:
            # 1. `import ... from 'module'`
            if node.type == "import_statement":
                stmt_text = get_text(node)
                line_no = node.start_point.row + 1
                source_node = node.child_by_field_name("source")
                source_val = get_text(source_node).strip("'\"`") if source_node else ""
                findings.append(
                    ASTImportFinding(
                        symbol=source_val or stmt_text,
                        file_path=rel_path,
                        line_number=line_no,
                        start_byte=node.start_byte,
                        end_byte=node.end_byte,
                        import_statement=stmt_text,
                        language=lang,
                        module=source_val,
                        is_relative=source_val.startswith((".", "/")),
                    )
                )

            # 2. `require('module')` call expression
            elif node.type == "call_expression":
                func_node = node.child_by_field_name("function")
                if func_node and get_text(func_node) in ("require", "import"):
                    args_node = node.child_by_field_name("arguments")
                    if args_node and args_node.children:
                        for arg in args_node.children:
                            if arg.type in ("string", "template_string"):
                                raw_val = get_text(arg).strip("'\"`")
                                stmt_text = get_text(node)
                                line_no = node.start_point.row + 1
                                findings.append(
                                    ASTImportFinding(
                                        symbol=raw_val,
                                        file_path=rel_path,
                                        line_number=line_no,
                                        start_byte=node.start_byte,
                                        end_byte=node.end_byte,
                                        import_statement=stmt_text,
                                        language=lang,
                                        module=raw_val,
                                        is_relative=raw_val.startswith((".", "/")),
                                    )
                                )

            # 3. `export ... from 'module'`
            elif node.type == "export_statement":
                source_node = node.child_by_field_name("source")
                if source_node:
                    source_val = get_text(source_node).strip("'\"`")
                    stmt_text = get_text(node)
                    line_no = node.start_point.row + 1
                    findings.append(
                        ASTImportFinding(
                            symbol=source_val,
                            file_path=rel_path,
                            line_number=line_no,
                            start_byte=node.start_byte,
                            end_byte=node.end_byte,
                            import_statement=stmt_text,
                            language=lang,
                            module=source_val,
                            is_relative=source_val.startswith((".", "/")),
                        )
                    )

            for child in node.children:
                visit(child)

        visit(root_node)
        return findings

    # ── Directory Scanner ────────────────────────────────────────────────────

    def scan_directory(self, repo_path: str) -> dict[str, Any]:
        """
        Scan all supported source files in the repository.
        Returns a dict of findings ready to be merged into ObservedFacts:
          - syntax_errors: list of error dicts with file, line, byte range, message
          - ast_imports: list of import dicts
          - tree_sitter_active: bool
          - languages_detected: list of strings
        """
        all_syntax_errors: list[dict[str, Any]] = []
        all_ast_imports: list[dict[str, Any]] = []
        scanned_files = 0

        if not self._initialized:
            return {
                "tree_sitter_active": False,
                "syntax_errors": [],
                "ast_imports": [],
                "scanned_files": 0,
            }

        for root, dirs, files in os.walk(repo_path):
            dirs[:] = [d for d in dirs if d not in self._SKIP_DIRS]
            for file_name in files:
                abs_path = os.path.join(root, file_name)
                rel_path = os.path.relpath(abs_path, repo_path)
                ext = Path(file_name).suffix.lower()

                if self._detect_language(ext):
                    scanned_files += 1
                    errors, imports = self.parse_file(abs_path, rel_path)
                    all_syntax_errors.extend(e.to_dict() for e in errors)
                    all_ast_imports.extend(i.to_dict() for i in imports)

        log(
            f"AST scan finished. Files: {scanned_files}, "
            f"Syntax Errors: {len(all_syntax_errors)}, Imports: {len(all_ast_imports)}",
            "green" if not all_syntax_errors else "yellow",
        )

        return {
            "tree_sitter_active": True,
            "syntax_errors": all_syntax_errors,
            "ast_imports": all_ast_imports,
            "scanned_files": scanned_files,
            "languages_supported": self.get_supported_languages(),
        }
