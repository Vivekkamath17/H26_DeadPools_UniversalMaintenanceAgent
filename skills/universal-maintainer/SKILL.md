---
name: universal-maintainer
description: >
  An enterprise-grade, multi-agent skill that performs dynamic
  maintenance, AST code inspection via Tree-Sitter, AI fix generation via
  Chain-of-Verification (Gemini / Groq / Ollama), sandbox verification,
  Dependency Exit Capsule generation, and interactive GitHub PR workflows.
version: 1.1.0
triggers:
  - run maintenance audit
  - check repository compatibility
  - generate dependency exit capsule
  - create maintenance pr
inputs:
  repo_path: "Local path or GitHub repository URL"
outputs:
  - output/dependency_exit_capsule.json
  - output/dependency_exit_capsule.md
---

# Universal Maintainer Agent Skill

## Multi-Agent Architecture

1. **Phase 1 · Deep Inspector & Tree-Sitter AST Agent:**
   - Detects stacks and parses dependency manifests (`pyproject.toml`, `requirements.txt`, `package.json`, `go.mod`, `Cargo.toml`).
   - Executes multi-language AST inspection via `tree_sitter_inspector.py` (Python, JavaScript, TypeScript) to locate syntax errors, malformed tokens, and import ranges.
2. **Phase 2 · Diagnostic & Reasoning Agent (CoV):**
   - Chains verification (Draft -> Sub-question verification -> Refined diagnosis).
   - Supported backends: **Gemini** (`GEMINI_API_KEY`), **Groq** (`GROQ_API_KEY`), **Ollama** (`OLLAMA_BASE_URL`), or deterministic heuristic fallback.
3. **Phase 3 · Sandbox Verification & Self-Healing Agent:**
   - Applies unified diffs in isolation, detects test suites (`pytest`, `npm test`, `cargo test`, `go test`), and runs a self-healing reflection loop (up to 3 retries) with automated git rollback on terminal failure.
4. **Phase 4 · Dependency Exit Capsule Compiler:**
   - Validates JSON output strictly against `exit_capsule_schema.json` and produces an advisory-labeled Markdown report.
5. **Phase 5 · Interactive PR Agent:**
   - Enforces an explicit user confirmation gate (`[y/N]`).
   - On confirmation, creates a local fix branch, commits staged fixes, and publishes via GitHub API (`PyGithub` / `GITHUB_TOKEN`) or GitHub CLI (`gh`).

## Environment Variables

| Variable | Purpose |
|---|---|
| `GEMINI_API_KEY` | Gemini API key (Priority 1: `gemini-2.5-flash`) |
| `GEMINI_MODEL` | Override Gemini model name |
| `GROQ_API_KEY` | Groq API key (Priority 2: `llama3-8b-8192`) |
| `GROQ_MODEL` | Override Groq model name |
| `OLLAMA_BASE_URL` | Ollama server URL (Priority 3: `http://localhost:11434`) |
| `OLLAMA_MODEL` | Override Ollama model tag |
| `GITHUB_TOKEN` | GitHub PAT token for automated PR creation in Phase 5 |

## Usage

```bash
# Install dependencies
pip install -r requirements.txt

# Run complete audit against a remote repository with Gemini
$env:GEMINI_API_KEY = "your-api-key"
python main.py --repo https://github.com/rishrek/LinkWatch

# Run fast read-only audit without sandbox or PR prompts
python main.py --repo https://github.com/rishrek/LinkWatch --skip-sandbox --no-pr

# Run with non-interactive auto-PR confirmation
python main.py --repo ./myproject --auto-pr
```

## Output Artifacts

* `output/dependency_exit_capsule.json` – Machine-readable capsule validated against `exit_capsule_schema.json`.
* `output/dependency_exit_capsule.md` – Human-readable report separating observed facts from AI-generated advisory recommendations.
