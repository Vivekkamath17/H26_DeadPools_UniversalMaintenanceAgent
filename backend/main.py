"""
backend/main.py
───────────────
FastAPI Backend for the Universal Maintenance Agent Platform.
Serves REST endpoints and Server-Sent Events (SSE) for the React frontend.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any, AsyncGenerator

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel, HttpUrl
from sse_starlette.sse import EventSourceResponse

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

# ── Path setup (import agents from parent skills folder) ─────────────────────
_ROOT       = Path(__file__).parent.parent
_AGENTS_DIR = _ROOT / "skills" / "universal-maintainer" / "agents"
sys.path.insert(0, str(_AGENTS_DIR.parent))
sys.path.insert(0, str(_AGENTS_DIR))

# ── In-memory run registry ────────────────────────────────────────────────────
# run_id → {status, events_queue, capsule, started_at}
_RUNS: dict[str, dict[str, Any]] = {}

# ── FastAPI app ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="Universal Maintenance Agent API",
    version="1.0.0",
    description="Autonomous multi-agent repository maintenance platform (Track 2).",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Request/Response Schemas ──────────────────────────────────────────────────

class RunRequest(BaseModel):
    url: str
    provider: str = "gemini"
    skip_sandbox: bool = True
    dependency: str = ""

class RunCreatedResponse(BaseModel):
    run_id: str
    status: str
    started_at: float

# ── Helper: push event into a run's queue ────────────────────────────────────

def _push(run_id: str, event_type: str, data: dict[str, Any]) -> None:
    if run_id in _RUNS:
        queue: asyncio.Queue = _RUNS[run_id]["queue"]
        payload = {"type": event_type, "ts": time.time(), **data}
        try:
            queue.put_nowait(json.dumps(payload))
        except asyncio.QueueFull:
            pass

# ── Agent pipeline (async background task) ───────────────────────────────────

async def _run_pipeline(run_id: str, request: RunRequest) -> None:
    """Executes the 5-phase multi-agent pipeline and streams events via SSE."""
    import traceback

    _RUNS[run_id]["status"] = "running"

    def _emit(phase: str, agent: str, status: str, msg: str, data: dict | None = None) -> None:
        _push(run_id, "agent_update", {
            "phase": phase,
            "agent": agent,
            "status": status,
            "message": msg,
            "data": data or {},
        })

    try:
        # ── Phase 1: Deep Inspector ───────────────────────────────────────────
        _emit("1", "Inspector + Tree-Sitter AST", "running", f"Cloning & inspecting {request.url} ...")

        from agents.inspector_agent import DeepInspectorAgent
        loop = asyncio.get_event_loop()
        inspector = DeepInspectorAgent()
        facts_obj = await loop.run_in_executor(None, inspector.inspect, request.url)
        facts = facts_obj.to_dict()

        _emit("1", "Inspector + Tree-Sitter AST", "done",
              f"Stack: {facts.get('stack')} | Deps: {sum(len(v) for v in facts.get('dependencies', {}).values())} | "
              f"Imports: {len(facts.get('import_usages', []))} | AST Errors: {len(facts.get('syntax_errors', []))}",
              {"stack": facts.get("stack"), "manifests": facts.get("manifests_found"),
               "syntax_errors": facts.get("syntax_errors", [])})

        # ── Phase 2: Diagnostic Reasoning ────────────────────────────────────
        _emit("2", "Diagnostic Agent (CoV)", "running", f"Calling {request.provider.title()} with Chain-of-Verification ...")

        # Set provider env if overridden
        if request.provider == "gemini":
            os.environ.setdefault("GEMINI_API_KEY", os.getenv("GEMINI_API_KEY", ""))

        from agents.diagnostic_agent import DiagnosticAgent
        diagnostic = DiagnosticAgent()
        diagnosis = await loop.run_in_executor(None, diagnostic.diagnose, facts)

        _emit("2", "Diagnostic Agent (CoV)", "done",
              f"Backend: {diagnosis.backend_used} | Risks: {len(diagnosis.risk_indicators)} | Patches: {len(diagnosis.recommended_patches)}",
              {"backend_used": diagnosis.backend_used,
               "risk_count": len(diagnosis.risk_indicators),
               "patch_count": len(diagnosis.recommended_patches),
               "risks": diagnosis.risk_indicators[:5]})

        # ── Phase 3: Sandbox ──────────────────────────────────────────────────
        from agents.sandbox_agent import SandboxResult
        if request.skip_sandbox:
            _emit("3", "Sandbox Agent", "skipped", "Sandbox verification skipped by user flag.")
            sandbox_result = SandboxResult(
                success=True,
                attempts=0,
                test_command="skipped",
                stdout="Skipped by user.",
                stderr="",
                exit_code=0,
            )
        else:
            _emit("3", "Sandbox Agent", "running", "Applying patches and running test suite ...")
            from agents.sandbox_agent import SandboxAgent
            sandbox = SandboxAgent(repo_path=facts.get("repo_path", request.url), diagnostic_agent=diagnostic)
            sandbox_result = await loop.run_in_executor(None, sandbox.verify, diagnosis, facts)
            status = "done" if sandbox_result.success else "warning"
            _emit("3", "Sandbox Agent", status,
                  f"Tests {'passed' if sandbox_result.success else 'did not pass'} after {sandbox_result.attempts} attempt(s).",
                  {"success": sandbox_result.success, "attempts": sandbox_result.attempts,
                   "stdout": (sandbox_result.stdout or "")[-600:],
                   "rolled_back": sandbox_result.patches_rolled_back})

        # ── Phase 4: Capsule Compiler ─────────────────────────────────────────
        _emit("4", "Capsule Compiler", "running", "Assembling and validating Dependency Exit Capsule ...")
        output_dir = str(_ROOT / "output")

        from agents.capsule_compiler import CapsuleCompiler
        compiler = CapsuleCompiler(output_dir=output_dir)
        json_path, md_path = await loop.run_in_executor(None, compiler.compile, facts, diagnosis, sandbox_result)

        with open(json_path, "r", encoding="utf-8") as f:
            capsule = json.load(f)

        # Inject recommended_patches array into capsule so frontend can render diffs
        diag_dict = diagnosis.to_dict()
        capsule["recommended_patches"] = diag_dict.get("recommended_patches", [])
        capsule["cov_log"]             = diag_dict.get("cov_verification_log", "")

        _RUNS[run_id]["capsule"] = capsule
        _RUNS[run_id]["md_path"] = str(md_path)
        _RUNS[run_id]["facts"]   = facts
        _RUNS[run_id]["diagnosis_dict"] = diag_dict
        _RUNS[run_id]["sandbox_dict"]   = sandbox_result.to_dict()

        _emit("4", "Capsule Compiler", "done",
              "Exit Capsule validated and saved.",
              {"json_path": str(json_path), "md_path": str(md_path)})

        # ── Finalize ──────────────────────────────────────────────────────────
        _RUNS[run_id]["status"] = "completed"
        _push(run_id, "completed", {"run_id": run_id, "capsule_ready": True})

    except Exception as exc:
        _RUNS[run_id]["status"] = "error"
        _push(run_id, "error", {"message": str(exc), "traceback": traceback.format_exc()})
    finally:
        # Signal stream end
        _push(run_id, "done", {"run_id": run_id})

# ── REST Endpoints ────────────────────────────────────────────────────────────

@app.post("/runs", response_model=RunCreatedResponse)
async def create_run(request: RunRequest, background_tasks: BackgroundTasks) -> RunCreatedResponse:
    """Start a new maintenance agent pipeline run."""
    run_id = str(uuid.uuid4())
    now = time.time()
    _RUNS[run_id] = {
        "status": "queued",
        "started_at": now,
        "request": request.model_dump(),
        "queue": asyncio.Queue(maxsize=500),
        "capsule": None,
    }
    background_tasks.add_task(_run_pipeline, run_id, request)
    return RunCreatedResponse(run_id=run_id, status="queued", started_at=now)


@app.get("/runs/{run_id}/events")
async def run_events(run_id: str) -> EventSourceResponse:
    """Server-Sent Events stream for real-time agent progress."""
    if run_id not in _RUNS:
        raise HTTPException(status_code=404, detail="Run not found")

    async def generator() -> AsyncGenerator[str, None]:
        queue: asyncio.Queue = _RUNS[run_id]["queue"]
        while True:
            try:
                payload = await asyncio.wait_for(queue.get(), timeout=30.0)
                yield payload
                data = json.loads(payload)
                if data.get("type") == "done":
                    break
            except asyncio.TimeoutError:
                yield json.dumps({"type": "heartbeat", "ts": time.time()})

    return EventSourceResponse(generator())


@app.get("/runs/{run_id}/capsule")
async def get_capsule(run_id: str) -> dict[str, Any]:
    """Return the completed Dependency Exit Capsule JSON."""
    if run_id not in _RUNS:
        raise HTTPException(status_code=404, detail="Run not found")
    run = _RUNS[run_id]
    if run.get("capsule"):
        return run["capsule"]
    if run["status"] == "error":
        raise HTTPException(status_code=500, detail="Run ended in error")
    if run["status"] not in ("completed",):
        raise HTTPException(status_code=409, detail=f"Run status: {run['status']}")
    raise HTTPException(status_code=404, detail="Capsule not found")


@app.get("/runs/{run_id}/status")
async def get_status(run_id: str) -> dict[str, Any]:
    """Return run status and metadata."""
    if run_id not in _RUNS:
        raise HTTPException(status_code=404, detail="Run not found")
    run = _RUNS[run_id]
    return {
        "run_id": run_id,
        "status": run["status"],
        "started_at": run["started_at"],
        "request": run.get("request"),
        "capsule_ready": run["capsule"] is not None,
    }


@app.get("/runs/{run_id}/export", response_class=HTMLResponse)
async def export_html(run_id: str) -> HTMLResponse:
    """Export a beautiful, self-contained standalone HTML report."""
    if run_id not in _RUNS:
        raise HTTPException(status_code=404, detail="Run not found")
    run = _RUNS[run_id]
    if not run.get("capsule"):
        raise HTTPException(status_code=202, detail="Capsule not ready yet")

    capsule     = run["capsule"]
    facts       = run.get("facts", {})
    diagnosis   = run.get("diagnosis_dict", {})
    sandbox     = run.get("sandbox_dict", {})

    risk_items  = "".join(
        f'<li class="risk-item"><span class="badge red">RISK</span> {r}</li>'
        for r in diagnosis.get("risk_indicators", [])
    )
    patch_items = "".join(
        f'<li class="patch-item"><span class="badge amber">PATCH</span> '
        f'<strong>{p.get("file","")}</strong>: {p.get("description","")}'
        f'<pre class="diff">{p.get("unified_diff","No diff available")}</pre></li>'
        for p in diagnosis.get("recommended_patches", [])
    )
    dep_rows = ""
    for manifest, deps in facts.get("dependencies", {}).items():
        for pkg, ver in deps.items():
            dep_rows += f"<tr><td>{manifest}</td><td><code>{pkg}</code></td><td>{ver or 'unspecified'}</td></tr>"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>Dependency Exit Capsule — {facts.get("repo_path","")}</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:'JetBrains Mono',monospace,system-ui;background:#0d1117;color:#e6edf3;line-height:1.6}}
  .header{{background:linear-gradient(135deg,#1a2d45,#0d2135);padding:2rem 3rem;border-bottom:2px solid #10b981}}
  .header h1{{font-size:1.8rem;color:#10b981;margin-bottom:.5rem}}
  .header .meta{{color:#8b949e;font-size:.85rem}}
  .verdict-banner{{padding:1rem 3rem;font-size:1.1rem;font-weight:700;
    background:{'#0d3320' if sandbox.get('success') else '#3d1a1a'};
    color:{'#10b981' if sandbox.get('success') else '#f87171'};
    border-bottom:2px solid {'#10b981' if sandbox.get('success') else '#f87171'}}}
  .container{{max-width:1100px;margin:2rem auto;padding:0 1.5rem}}
  .section{{margin-bottom:2rem;background:#161b22;border:1px solid #30363d;border-radius:8px;overflow:hidden}}
  .section-header{{background:#21262d;padding:.75rem 1.25rem;font-weight:700;font-size:.9rem;
    color:#58a6ff;border-bottom:1px solid #30363d;display:flex;align-items:center;gap:.5rem}}
  .section-body{{padding:1.25rem}}
  .badge{{display:inline-block;padding:.2rem .6rem;border-radius:4px;font-size:.75rem;font-weight:700;margin-right:.4rem}}
  .badge.red{{background:#3d1a1a;color:#f87171}}
  .badge.amber{{background:#3d2c0a;color:#f59e0b}}
  .badge.green{{background:#0d3320;color:#10b981}}
  .badge.blue{{background:#0a2540;color:#3b82f6}}
  ul{{list-style:none;padding:0}}
  li{{padding:.5rem 0;border-bottom:1px solid #21262d}}
  li:last-child{{border-bottom:none}}
  table{{width:100%;border-collapse:collapse;font-size:.85rem}}
  th{{background:#21262d;padding:.5rem .75rem;text-align:left;color:#8b949e;font-weight:600}}
  td{{padding:.5rem .75rem;border-bottom:1px solid #21262d}}
  code{{background:#21262d;padding:.1rem .35rem;border-radius:3px;font-size:.8rem;color:#79c0ff}}
  pre.diff{{background:#0d1117;border:1px solid #30363d;border-radius:4px;padding:.75rem;
    margin-top:.5rem;overflow-x:auto;font-size:.8rem;white-space:pre-wrap}}
  .stats-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:1rem;margin-bottom:1.5rem}}
  .stat-card{{background:#21262d;border:1px solid #30363d;border-radius:6px;padding:1rem;text-align:center}}
  .stat-val{{font-size:2rem;font-weight:700;color:#10b981}}
  .stat-label{{font-size:.75rem;color:#8b949e;margin-top:.25rem}}
  .footer{{text-align:center;padding:2rem;color:#484f58;font-size:.8rem}}
</style>
</head>
<body>
<div class="header">
  <h1>🔍 Dependency Exit Capsule</h1>
  <div class="meta">
    Repository: {facts.get("repo_path","")} &nbsp;|&nbsp;
    Stack: {", ".join(facts.get("stack",["unknown"]))} &nbsp;|&nbsp;
    LLM Backend: <strong>{diagnosis.get("backend_used","heuristic")}</strong> &nbsp;|&nbsp;
    Generated: {time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())}
  </div>
</div>
<div class="verdict-banner">
  {'✅ VERIFIED — Sandbox tests passed' if sandbox.get('success') else '⚠️ UNVERIFIED — Sandbox not executed or tests failed'}
</div>
<div class="container">
  <div class="stats-grid">
    <div class="stat-card"><div class="stat-val">{sum(len(v) for v in facts.get("dependencies",{{}}).values())}</div><div class="stat-label">Dependencies</div></div>
    <div class="stat-card"><div class="stat-val">{len(facts.get("syntax_errors",[]))}</div><div class="stat-label">AST Syntax Errors</div></div>
    <div class="stat-card"><div class="stat-val" style="color:{'#f87171' if diagnosis.get('risk_indicators') else '#10b981'}">{len(diagnosis.get("risk_indicators",[]))}</div><div class="stat-label">Risk Indicators</div></div>
    <div class="stat-card"><div class="stat-val" style="color:#f59e0b">{len(diagnosis.get("recommended_patches",[]))}</div><div class="stat-label">Proposed Patches</div></div>
    <div class="stat-card"><div class="stat-val">{len(facts.get("import_usages",[]))}</div><div class="stat-label">Import Usages Mapped</div></div>
    <div class="stat-card"><div class="stat-val">{sandbox.get("attempts",0)}</div><div class="stat-label">Sandbox Attempts</div></div>
  </div>

  <div class="section">
    <div class="section-header">🔴 Risk Indicators <span class="badge red">AI ADVISORY</span></div>
    <div class="section-body"><ul>{risk_items or '<li style="color:#8b949e">No risk indicators identified.</li>'}</ul></div>
  </div>

  <div class="section">
    <div class="section-header">📋 Declared Dependencies <span class="badge blue">OBSERVED FACT</span></div>
    <div class="section-body">
      <table><tr><th>Manifest</th><th>Package</th><th>Version</th></tr>{dep_rows}</table>
    </div>
  </div>

  <div class="section">
    <div class="section-header">🔧 Proposed Patches <span class="badge amber">AI RECOMMENDED</span></div>
    <div class="section-body"><ul>{patch_items or '<li style="color:#8b949e">No automated patches proposed.</li>'}</ul></div>
  </div>

  <div class="section">
    <div class="section-header">🧠 AI Chain-of-Verification Analysis <span class="badge amber">AI ADVISORY</span></div>
    <div class="section-body">
      <p style="color:#8b949e;font-size:.85rem">{diagnosis.get("cov_log","") or capsule.get("ai_generated_analysis_or_recommendations","Not available.")}</p>
    </div>
  </div>

  <div class="section">
    <div class="section-header">🧪 Sandbox Execution Results <span class="badge green">EMPIRICAL</span></div>
    <div class="section-body">
      <table>
        <tr><th>Field</th><th>Value</th></tr>
        <tr><td>Command</td><td><code>{sandbox.get("test_command","skipped")}</code></td></tr>
        <tr><td>Exit Code</td><td><code>{sandbox.get("exit_code",-1)}</code></td></tr>
        <tr><td>Success</td><td><span class="badge {'green' if sandbox.get('success') else 'red'}">{sandbox.get("success")}</span></td></tr>
        <tr><td>Attempts</td><td>{sandbox.get("attempts",0)}</td></tr>
        <tr><td>Rolled Back</td><td>{sandbox.get("patches_rolled_back",False)}</td></tr>
      </table>
    </div>
  </div>
</div>
<div class="footer">Generated by Universal Maintenance Agent v1.1.0 · Agent Skills Open Standard · Track 2</div>
</body>
</html>"""
    return HTMLResponse(content=html)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": "1.0.0"}
