"""
reflection_prompt.py
────────────────────
Builds the reflection prompt used by the SandboxAgent when a patch fails.

The reflection prompt feeds the original diagnosis, the applied patch, and the
captured test failure logs back to the DiagnosticAgent so it can produce a
corrected, narrower patch.
"""

from __future__ import annotations
from typing import Any


def build_reflection_prompt(
    original_diagnosis: dict[str, Any],
    applied_patch: str,
    failure_log: str,
    attempt: int,
    max_attempts: int,
) -> list[dict[str, str]]:
    """Return an OpenAI-compatible messages list for the reflection loop."""

    system_prompt = (
        "You are an expert software maintenance engineer performing a root-cause "
        "analysis on a failed automated patch. Your job is ONLY to fix what broke.\n\n"
        "Respond with valid JSON containing:\n"
        "  revised_problem_summary  (string)\n"
        "  root_cause_analysis      (string – why the previous patch failed)\n"
        "  recommended_patches      (array of {file, description, unified_diff})\n"
        "  suggested_tests          (array of strings)\n"
        "  unresolved_concerns      (array of strings)\n"
        "Do NOT include markdown fences or any text outside the JSON object."
    )

    import json
    user_prompt = (
        f"=== REFLECTION ATTEMPT {attempt}/{max_attempts} ===\n\n"
        "--- ORIGINAL DIAGNOSIS ---\n"
        f"{json.dumps(original_diagnosis, indent=2, default=str)}\n\n"
        "--- APPLIED PATCH (unified diff) ---\n"
        f"{applied_patch}\n\n"
        "--- TEST FAILURE LOG ---\n"
        f"{failure_log}\n\n"
        "Produce a corrected patch JSON as described in the system prompt."
    )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": user_prompt},
    ]
