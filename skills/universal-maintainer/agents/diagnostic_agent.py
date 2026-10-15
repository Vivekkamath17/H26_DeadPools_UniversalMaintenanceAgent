"""
diagnostic_agent.py
────────────────────
Diagnostic & Reasoning Agent – open-weight LLM with CoV prompting.

LLM Backend Priority
────────────────────
1. Gemini  (if GEMINI_API_KEY is set)   ← NEW
2. Groq    (if GROQ_API_KEY is set)
3. Ollama  (if Ollama server responds)
4. Heuristic-only fallback (deterministic, no LLM)

The agent accepts ObservedFacts and produces a DiagnosisResult containing
risk indicators, proposed patches (as unified diffs), suggested tests, and
an internal Chain-of-Verification log.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any

# ── Prompt templates ─────────────────────────────────────────────────────────
import sys
from pathlib import Path

# Allow running standalone as well as via the package
_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
sys.path.insert(0, str(_PROMPTS_DIR.parent))

try:
    from prompts.diagnostic_prompt import build_diagnostic_prompt
    from prompts.reflection_prompt import build_reflection_prompt
except ImportError:
    # fallback stubs if running standalone
    def build_diagnostic_prompt(facts):  # type: ignore[misc]
        return [{"role": "user", "content": f"Diagnose:\n{json.dumps(facts, default=str)}"}]

    def build_reflection_prompt(diagnosis, patch, log, attempt, max_attempts):  # type: ignore[misc]
        return [{"role": "user", "content": f"Reflect on failed patch:\n{log}"}]

# ── Optional rich logging ────────────────────────────────────────────────────
try:
    from rich.console import Console
    _console = Console()
    def log(msg: str, style: str = "magenta") -> None:
        _console.print(f"[{style}][Diagnostic][/{style}] {msg}")
except ImportError:
    def log(msg: str, style: str = "magenta") -> None:  # type: ignore[misc]
        print(f"[Diagnostic] {msg}")


# ── Result dataclass ─────────────────────────────────────────────────────────

@dataclass
class DiagnosisResult:
    problem_summary: str = ""
    risk_indicators: list[str] = field(default_factory=list)
    recommended_patches: list[dict[str, str]] = field(default_factory=list)
    # Each patch: {file, description, unified_diff}
    suggested_tests: list[str] = field(default_factory=list)
    compatibility_gaps: list[str] = field(default_factory=list)
    unresolved_concerns: list[str] = field(default_factory=list)
    cov_verification_log: str = ""
    backend_used: str = "none"
    raw_response: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "problem_summary": self.problem_summary,
            "risk_indicators": self.risk_indicators,
            "recommended_patches": self.recommended_patches,
            "suggested_tests": self.suggested_tests,
            "compatibility_gaps": self.compatibility_gaps,
            "unresolved_concerns": self.unresolved_concerns,
            "cov_verification_log": self.cov_verification_log,
            "backend_used": self.backend_used,
        }


# ── Main Agent Class ─────────────────────────────────────────────────────────

class DiagnosticAgent:
    """
    Open-weight LLM reasoning agent with Chain-of-Verification prompting.

    Constructor env vars (checked in priority order)
    ─────────────────────────────────────────────────
    GROQ_API_KEY      – activates Groq backend
    GROQ_MODEL        – model name (default: llama3-8b-8192)
    OLLAMA_BASE_URL   – Ollama server base URL (default: http://localhost:11434)
    OLLAMA_MODEL      – model tag (default: llama3:8b)
    """

    _GROQ_DEFAULT_MODEL   = "llama3-8b-8192"
    _OLLAMA_DEFAULT_URL   = "http://localhost:11434"
    _OLLAMA_DEFAULT_MODEL = "llama3:8b"
    _GEMINI_DEFAULT_MODEL = "gemini-flash-lite-latest"   # fast + resilient; override with GEMINI_MODEL

    def __init__(self) -> None:
        self._gemini_api_key = os.environ.get("GEMINI_API_KEY", "")
        self._gemini_model   = os.environ.get("GEMINI_MODEL", self._GEMINI_DEFAULT_MODEL)
        self._groq_api_key   = os.environ.get("GROQ_API_KEY", "")
        self._groq_model     = os.environ.get("GROQ_MODEL", self._GROQ_DEFAULT_MODEL)
        self._ollama_url     = os.environ.get("OLLAMA_BASE_URL", self._OLLAMA_DEFAULT_URL)
        self._ollama_model   = os.environ.get("OLLAMA_MODEL", self._OLLAMA_DEFAULT_MODEL)
        self._backend        = self._detect_backend()
        log(f"LLM backend: {self._backend}")

    # ── Backend detection ────────────────────────────────────────────────────

    def _detect_backend(self) -> str:
        if self._gemini_api_key:
            return "gemini"
        if self._groq_api_key:
            return "groq"
        if self._ollama_reachable():
            return "ollama"
        log("No LLM backend available – falling back to heuristic mode.", "yellow")
        return "heuristic"

    def _ollama_reachable(self) -> bool:
        try:
            import urllib.request
            with urllib.request.urlopen(
                f"{self._ollama_url}/api/tags", timeout=3
            ) as resp:
                return resp.status == 200
        except Exception:
            return False

    # ── Public methods ───────────────────────────────────────────────────────

    def diagnose(self, observed_facts: dict[str, Any]) -> DiagnosisResult:
        """Primary entry point: diagnose a repository from its ObservedFacts."""
        log("Building Chain-of-Verification prompt …")
        messages = build_diagnostic_prompt(observed_facts)
        raw = self._call_llm(messages)
        result = self._parse_response(raw)
        result.backend_used = self._backend
        log(
            f"Diagnosis complete. Risks={len(result.risk_indicators)}, "
            f"Patches={len(result.recommended_patches)}",
            "green"
        )
        return result

    def reflect(
        self,
        original_diagnosis: dict[str, Any],
        applied_patch: str,
        failure_log: str,
        attempt: int,
        max_attempts: int,
    ) -> DiagnosisResult:
        """Reflection loop entry: re-diagnose after a failed sandbox run."""
        log(f"Starting reflection (attempt {attempt}/{max_attempts}) …", "yellow")
        messages = build_reflection_prompt(
            original_diagnosis, applied_patch, failure_log, attempt, max_attempts
        )
        raw = self._call_llm(messages)
        result = self._parse_response(raw)
        result.backend_used = self._backend
        log(
            f"Reflection complete. Revised patches: {len(result.recommended_patches)}",
            "green"
        )
        return result

    # ── LLM dispatch ────────────────────────────────────────────────────────

    def _call_llm(self, messages: list[dict[str, str]]) -> str:
        if self._backend == "gemini":
            return self._call_gemini(messages)
        if self._backend == "groq":
            return self._call_groq(messages)
        if self._backend == "ollama":
            return self._call_ollama(messages)
        return self._heuristic_response()

    # ·· Gemini ················────────────────────────────────────────────
    def _call_gemini(self, messages: list[dict[str, str]]) -> str:
        """
        Calls Google Gemini via the official `google-genai` SDK (google.genai).
        Merges system + user messages into one prompt string since the
        generate_content API accepts a single contents argument.
        """
        try:
            from google import genai                        # type: ignore
            from google.genai import types as genai_types   # type: ignore
        except ImportError:
            log("google-genai not installed. Run: pip install google-genai", "red")
            log("Falling back to heuristic mode.", "yellow")
            self._backend = "heuristic"
            return self._heuristic_response()

        try:
            client = genai.Client(api_key=self._gemini_api_key)

            # Merge system + user parts into one prompt
            system_parts = [m["content"] for m in messages if m["role"] == "system"]
            user_parts   = [m["content"] for m in messages if m["role"] == "user"]

            full_prompt = ""
            if system_parts:
                full_prompt += "[SYSTEM INSTRUCTIONS]\n" + "\n".join(system_parts) + "\n\n"
            full_prompt += "\n".join(user_parts)

            candidate_models = [self._gemini_model]
            for fb in ["gemini-flash-lite-latest", "gemini-3.8-flash", "gemini-3.5-flash-lite"]:
                if fb not in candidate_models:
                    candidate_models.append(fb)

            import time as _time
            max_retries = 2

            for model_candidate in candidate_models:
                log(f"Calling Gemini [{model_candidate}] ...")
                for attempt in range(1, max_retries + 1):
                    try:
                        response = client.models.generate_content(
                            model=model_candidate,
                            contents=full_prompt,
                            config=genai_types.GenerateContentConfig(
                                temperature=0.2,
                                max_output_tokens=8192,
                                response_mime_type="application/json",
                            ),
                        )
                        if response.text:
                            self._gemini_model = model_candidate
                            return response.text
                    except Exception as call_exc:
                        err_msg = str(call_exc)
                        if ("503" in err_msg or "429" in err_msg or "UNAVAILABLE" in err_msg) and attempt < max_retries:
                            delay = attempt * 2
                            log(f"Gemini {model_candidate} busy ({err_msg[:40]}...). Retrying in {delay}s ...", "yellow")
                            _time.sleep(delay)
                        elif "404" in err_msg or "NOT_FOUND" in err_msg or "no longer available" in err_msg:
                            log(f"Gemini {model_candidate} not available on this tier. Trying next model...", "yellow")
                            break
                        else:
                            log(f"Gemini {model_candidate} error: {err_msg[:60]}. Trying next candidate...", "yellow")
                            break

            log("All Gemini candidate models failed - switching to heuristic.", "yellow")
            self._backend = "heuristic"
            return self._heuristic_response()

        except Exception as exc:
            log(f"Gemini client initialization failed: {exc} - switching to heuristic.", "red")
            self._backend = "heuristic"
            return self._heuristic_response()

    # ·· Groq ··················────────────────────────────────────────────
    def _call_groq(self, messages: list[dict[str, str]]) -> str:
        try:
            import groq  # type: ignore
            client = groq.Groq(api_key=self._groq_api_key)
            log(f"Calling Groq [{self._groq_model}] …")
            completion = client.chat.completions.create(
                model=self._groq_model,
                messages=messages,  # type: ignore[arg-type]
                temperature=0.2,
                max_tokens=4096,
            )
            return completion.choices[0].message.content or ""
        except Exception as exc:
            log(f"Groq call failed: {exc} – switching to heuristic.", "red")
            self._backend = "heuristic"
            return self._heuristic_response()

    # ·· Ollama ················────────────────────────────────────────────
    def _call_ollama(self, messages: list[dict[str, str]]) -> str:
        import urllib.request, json as _json
        payload = {
            "model": self._ollama_model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": 0.2},
        }
        body = _json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self._ollama_url}/api/chat",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        log(f"Calling Ollama [{self._ollama_model}] …")
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = _json.loads(resp.read().decode("utf-8"))
            return data.get("message", {}).get("content", "")
        except Exception as exc:
            log(f"Ollama call failed: {exc} – switching to heuristic.", "red")
            self._backend = "heuristic"
            return self._heuristic_response()

    # ·· Heuristic fallback ····────────────────────────────────────────────
    def _heuristic_response(self) -> str:
        """
        Deterministic heuristic diagnosis when no LLM is available.
        Produces a JSON-compatible string with basic risk analysis.
        """
        return json.dumps({
            "problem_summary": (
                "No LLM backend available. Heuristic analysis only: "
                "review pinned dependencies, missing error handling, "
                "and outdated manifest versions manually."
            ),
            "risk_indicators": [
                "No LLM backend configured (GROQ_API_KEY or Ollama not detected)",
                "Dependency versions not semantically evaluated",
                "Security advisories not checked",
            ],
            "recommended_patches": [],
            "suggested_tests": [
                "Run the project's existing test suite manually",
                "Use `pip-audit` / `npm audit` / `cargo audit` for CVE checks",
            ],
            "compatibility_gaps": [
                "Full compatibility analysis requires LLM backend"
            ],
            "unresolved_concerns": [
                "Configure GROQ_API_KEY or run Ollama to enable AI analysis"
            ],
            "cov_verification_log": "Heuristic mode – no CoV performed.",
        })

    # ── Response parsing ─────────────────────────────────────────────────────

    def _parse_response(self, raw: str) -> DiagnosisResult:
        """Extract JSON from LLM output, stripping any markdown fences."""
        result = DiagnosisResult(raw_response=raw)

        cleaned = raw.strip()
        # Strip ```json ... ``` or ``` ... ``` wrappers
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            if len(lines) >= 2 and lines[0].startswith("```") and lines[-1].startswith("```"):
                cleaned = "\n".join(lines[1:-1]).strip()
        else:
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(r"\s*```$", "", cleaned.strip())

        data = None
        # Try direct JSON parse
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            # Fallback: search for outermost balanced { ... }
            first_brace = cleaned.find("{")
            last_brace = cleaned.rfind("}")
            if first_brace != -1 and last_brace > first_brace:
                try:
                    data = json.loads(cleaned[first_brace:last_brace + 1])
                except json.JSONDecodeError:
                    pass

        if not data or not isinstance(data, dict):
            log("⚠ Could not parse LLM response as JSON – using raw text.", "yellow")
            result.problem_summary = raw[:500]
            result.unresolved_concerns = ["LLM response was not valid JSON"]
            return result

        result.problem_summary       = data.get("problem_summary", "")
        result.risk_indicators       = data.get("risk_indicators", [])
        result.recommended_patches   = data.get("recommended_patches", [])
        result.suggested_tests       = data.get("suggested_tests", [])
        result.compatibility_gaps    = data.get("compatibility_gaps", [])
        result.unresolved_concerns   = data.get("unresolved_concerns", [])
        result.cov_verification_log  = data.get("cov_verification_log", "")
        return result


# ── CLI self-test ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import json as _json
    sample_facts: dict[str, Any] = {
        "stack": ["Python"],
        "dependencies": {"requirements.txt": {"requests": ">=2.0", "flask": "==1.1.0"}},
        "import_usages": [],
        "errors": [],
    }
    agent = DiagnosticAgent()
    result = agent.diagnose(sample_facts)
    print(_json.dumps(result.to_dict(), indent=2))
