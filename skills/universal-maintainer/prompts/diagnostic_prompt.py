"""
diagnostic_prompt.py
────────────────────
Chain-of-Verification (CoV) prompt builder for the DiagnosticAgent.

The CoV pattern works in three stages embedded within a single request:
  1. Draft answer  – the LLM produces an initial diagnosis.
  2. Verification  – the LLM lists checkable sub-questions about its draft.
  3. Final answer  – grounded, refined answer based on verification results.

We encode all three stages in one system + user prompt so that even single-
turn APIs (Groq, Ollama /api/chat) benefit from the pattern.
"""

from __future__ import annotations
from typing import Any


def build_diagnostic_prompt(observed_facts: dict[str, Any]) -> list[dict[str, str]]:
    """Return an OpenAI-compatible messages list for the DiagnosticAgent."""

    system_prompt = (
        "You are an expert software maintenance engineer and security auditor. "
        "You reason in a structured Chain-of-Verification (CoV) pattern:\n"
        "  STEP 1 – Draft: Produce an initial diagnosis of the codebase issues.\n"
        "  STEP 2 – Verify: List 3-5 specific sub-questions that could falsify "
        "            your draft, then answer each one using ONLY the facts provided.\n"
        "  STEP 3 – Final: Refine your diagnosis based on the verification step.\n\n"
        "Output ONLY valid JSON with the following top-level keys:\n"
        "  problem_summary       (string)\n"
        "  risk_indicators       (array of strings)\n"
        "  recommended_patches   (array of {file, description, unified_diff})\n"
        "  suggested_tests       (array of strings)\n"
        "  compatibility_gaps    (array of strings)\n"
        "  unresolved_concerns   (array of strings)\n"
        "  cov_verification_log  (string – your internal verification reasoning)\n"
        "Do NOT include markdown fences or any text outside the JSON object."
    )

    facts_block = _format_facts(observed_facts)

    user_prompt = (
        "Below are deterministic facts extracted from the target repository "
        "by a static analysis inspector (no LLM was involved in their collection). "
        "Diagnose all maintenance issues and produce the JSON output described in "
        "the system prompt.\n\n"
        f"=== OBSERVED FACTS ===\n{facts_block}\n=== END FACTS ==="
    )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": user_prompt},
    ]


def _format_facts(facts: dict[str, Any]) -> str:
    """Serialize observed facts into a compact, readable text block."""
    import json
    return json.dumps(facts, indent=2, default=str)
