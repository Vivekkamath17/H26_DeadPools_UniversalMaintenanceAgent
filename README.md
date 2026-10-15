# Universal Maintenance Agent (UMA)
> Autonomous, verified, self-healing software maintenance powered by multi-model AI and deterministic sandboxing.

---

## 1. Problem and Solution Overview

### Problem Statement
Modern software engineering teams spend up to 42% of their development time maintaining legacy code, triaging flaky tests, migrating deprecated APIs, and handling dependency vulnerabilities. Traditional automated remediation tools suffer from critical shortcomings:
- **Hallucinated fixes**: Automated code generation frequently creates syntactically valid code that fails runtime assertions or breaks downstream semantics.
- **Blind PR submissions**: Developers distrust automated pull requests because there is no clear distinction between verified facts and AI-generated guesswork.
- **Fragile single-shot repair**: When an initial patch fails CI or regression tests, standard bots abandon the attempt rather than analyzing test failures and self-healing.
- **Vendor lock-in and high cost**: Strict reliance on proprietary APIs makes full-repo maintenance cost-prohibitive for large codebases.

### Solution Overview
The **Universal Maintenance Agent (UMA)** is an autonomous, agentic maintenance pipeline that inspects repositories, diagnoses root causes using Chain-of-Verification (CoV), executes candidate patches inside deterministic sandboxes with automated self-healing loops, and compiles verifiable **Maintenance Capsules** with explicit provenance tagging.

#### Provenance and Trust Architecture
UMA classifies every generated insight and artifact into a strict 4-tier provenance hierarchy:

| Provenance Tier | Tag | Meaning & Guarantee |
| :--- | :--- | :--- |
| **EXECUTED** | [EXECUTED] | Deterministically executed and verified by test runners in the sandbox. Zero hallucination risk. |
| **OBSERVED FACT** | [OBSERVED FACT] | Extracted directly from AST analysis, git commits, pyproject.toml, or lockfiles. |
| **AI ADVISORY** | [AI ADVISORY] | Synthesized by an LLM via verified reasoning (CoV); requires human review before production deployment. |
| **UNVERIFIED** | [UNVERIFIED] | Heuristic fallback output generated when LLM or sandbox execution is unavailable or inconclusive. |

#### Key Innovations
- **Chain-of-Verification (CoV) Diagnostic Engine**: Deconstructs issues into underlying hypotheses, verifies them against code evidence, and rejects hallucinations prior to patch synthesis.
- **Deterministic Sandbox & Self-Healing Loop**: Executes pytest suites inside isolated subprocesses. If a patch fails tests, the sandbox feeds the exact traceback back into the model to refine and heal the patch (up to 3 iterations).
- **Interactive Pull Request Synthesizer**: Produces production-ready GitHub PR descriptions with line-by-line diffs, verification receipts, and risk-weighted summaries.
- **Multi-Model Provider Hierarchy**: Seamlessly cascades from high-capability reasoning models (Google Gemini 2.5 Flash) to ultra-fast inference (Groq LLaMA-3.1-70B) down to local offline models (Ollama LLaMA 3 8B) or local heuristics.

---

## 2. Setup Instructions

### Prerequisites
| Tool / Runtime | Required Version | Description |
| :--- | :--- | :--- |
| **Python** | 3.10+ | Core agent runtime and backend service |
| **Node.js** | 18.0+ | Frontend web dashboard build toolchain |
| **Git** | 2.30+ | Repository cloning and VCS operations |
| **Ollama** *(Optional)* | 0.1.30+ | Local offline LLM execution |

### Step-by-Step Installation

#### 1. Clone the Repository
`ash
git clone git@github.com:Vivekkamath17/H26_DeadPools_UniversalMaintenanceAgent.git
cd H26_DeadPools_UniversalMaintenanceAgent
`

#### 2. Configure Python Virtual Environment
`ash
# Create virtual environment
python -m venv .venv

# Activate on Windows PowerShell:
.venv\Scripts\Activate.ps1

# Activate on Linux / macOS:
source .venv/bin/activate
`

#### 3. Install Python Dependencies
Install both the root package (agent pipeline) and backend service dependencies:
`ash
# Install core pipeline dependencies
pip install -r requirements.txt

# Install backend dependencies
pip install -r backend/requirements.txt
`

#### 4. Configure Environment Variables
Copy the template configuration and supply your API keys:
`ash
cp .env.example .env
`

Open .env in your editor and configure the desired LLM keys:
`env
# Primary LLM: Google Gemini
GEMINI_API_KEY=AIzaSy_YOUR_GEMINI_KEY_HERE
GEMINI_MODEL=gemini-2.5-flash

# Secondary LLM (Fallback): Groq Cloud
GROQ_API_KEY=gsk_YOUR_GROQ_KEY_HERE
GROQ_MODEL=llama-3.1-70b-versatile

# Tertiary LLM (Local / Offline): Ollama
OLLAMA_MODEL=llama3:8b
OLLAMA_BASE_URL=http://localhost:11434

# Sandbox Safety & Execution Limits
SANDBOX_TIMEOUT_SECONDS=60
MAX_SELF_HEAL_ATTEMPTS=3

# Target Repository under Maintenance
TARGET_REPO_PATH=.
`

#### 5. Install Frontend Dashboard Dependencies
`ash
cd frontend
npm install
cd ..
`

---

## 3. Usage Instructions

### Option A: One-Click Startup (Windows PowerShell)
The project includes a launch script that initializes both the FastAPI backend and the Vite frontend:
`powershell
.\start.ps1
`
- Backend API will be available at: http://localhost:8000
- API Interactive Swagger docs: http://localhost:8000/docs
- Frontend Web Dashboard: http://localhost:5173

### Option B: Manual Multi-Terminal Startup

**Terminal 1 — Backend API Server:**
`ash
cd backend
python -m uvicorn main:app --reload --port 8000
`

**Terminal 2 — Frontend Application:**
`ash
cd frontend
npm run dev
`

### Option C: CLI Mode (Headless Pipeline Execution)
You can invoke the Universal Maintenance Agent directly from the command line on any local target repository:

`ash
# Run full maintenance pipeline on a target repository
python -m skills.universal_maintainer.cli --repo /path/to/target-repo

# Run with custom budget or iteration caps
python -m skills.universal_maintainer.cli --repo /path/to/target-repo --max-heal 3 --timeout 90

# Generate capsule output only (dry run without applying git changes)
python -m skills.universal_maintainer.cli --repo /path/to/target-repo --dry-run --output ./capsule.json
`

#### CLI Flags Reference
| Flag | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| --repo | Path | . | Target directory of the repository to inspect and maintain |
| --max-heal | Int | 3 | Maximum number of self-healing compile-test-repair iterations |
| --timeout | Int | 60 | Execution timeout in seconds per sandbox test run |
| --dry-run | Flag | False | Run analysis and tests without writing patches to disk |
| --output | Path | None | Path to save the compiled JSON MaintenanceCapsule |

### Using the Web Dashboard
1. Open http://localhost:5173 in your browser.
2. Enter the absolute path to your target repository in the repository input box.
3. Click **Start Maintenance Run**.
4. Monitor the live pipeline execution across 5 dedicated view tabs:
   - **Overview**: Stage progression, executive summary, health scores, and timing breakdown.
   - **Patches & Diffs**: Interactive unified diff viewer with line numbers and patch rationales.
   - **Verification & Tests**: Sandbox execution trace, pytest stdout/stderr, and self-healing log.
   - **Risk Analysis**: Heatmap of blast radius, breaking change risks, and dependency impacts.
   - **Pull Request Preview**: GitHub-ready markdown PR description ready for export.

---

## 4. Architecture

### High-Level System Architecture

`
+-----------------------------------------------------------------------------------+
|                            UMA Web Dashboard (React 19)                           |
|       Overview   |   Patches & Diffs   |   Sandbox Logs   |   PR Generator        |
+-----------------------------------------+-----------------------------------------+
                                          | HTTP / SSE
+-----------------------------------------v-----------------------------------------+
|                              FastAPI Backend Server                               |
|        /api/runs   |   /api/runs/{id}   |   /api/capsules   |   /api/models       |
+-----------------------------------------+-----------------------------------------+
                                          | Invokes
+-----------------------------------------v-----------------------------------------+
|                         UNIVERSAL MAINTENANCE AGENT PIPELINE                      |
|                                                                                   |
|  [Phase 1] Deep Inspector Agent                                                   |
|    |-> Git commit history, AST parse, flake8/ruff, pytest status, dep graph       |
|    v                                                                              |
|  [Phase 2] Diagnostic Agent (Chain-of-Verification)                               |
|    |-> Failure cluster analysis, hypothesis verification, verified patch proposal |
|    v                                                                              |
|  [Phase 3] Sandbox & Self-Healing Agent                                           |
|    |-> Isolated test execution -> Pass? -> Proceed                                |
|    |     |                                                                        |
|    |     +-> Fail -> Feedback loop -> Re-prompt LLM -> Retry (<= 3 iterations)    |
|    v                                                                              |
|  [Phase 4] Capsule Compiler                                                       |
|    |-> Merges test receipts, patch diffs, and provenance tags into signed capsule |
|    v                                                                              |
|  [Phase 5] Interactive PR Agent                                                   |
|    |-> Builds verified markdown PR description, test logs, and blast radius       |
+-----------------------------------------+-----------------------------------------+
                                          |
                     +--------------------+--------------------+
                     |                     |                    |
                     v                     v                    v
          +--------------------+ +-------------------+ +-----------------+
          | Google Gemini API  | | Groq Cloud LLaMA  | | Ollama (Local)  |
          |  (2.5 Flash / Pro) | |   (3.1-70B Vers)  | |   (LLaMA 3 8B)  |
          +--------------------+ +-------------------+ +-----------------+
`

### 5-Phase Agent Workflow
1. **DeepInspectorAgent**: Analyzes the repository structure, discovers unit tests (pytest), extracts error patterns from logs, inspects dependencies in pyproject.toml or 
equirements.txt, and generates an initial inspection report.
2. **DiagnosticAgent**: Implements **Chain-of-Verification (CoV)**:
   - Formulates primary failure hypotheses.
   - Executes verification questions against code evidence.
   - Generates unified diff patches with explicit rationale and confidence metrics.
3. **SandboxAgent**:
   - Creates a temporary working mirror or applies candidate patches in an isolated execution sandbox.
   - Runs deterministic test commands (pytest -v).
   - If tests fail, captures the failure stdout/stderr, reformulates the issue, and triggers **Self-Healing** (up to 3 attempts).
4. **CapsuleCompiler**:
   - Aggregates all observed facts, execution traces, diffs, and AI advisories into a single standardized MaintenanceCapsule JSON artifact.
   - Tags each datum with its definitive provenance badge ([EXECUTED], [OBSERVED FACT], [AI ADVISORY], [UNVERIFIED]).
5. **InteractivePRAgent**:
   - Converts the capsule into a developer-facing Pull Request with summaries, risk matrices, before-and-after behavior descriptions, and reproducible sandbox logs.

### Key Design Decisions
- **Isolation over In-Place Mutation**: Candidate patches are validated in isolated environments before being committed to source control.
- **Fail-Soft LLM Fallback**: If Gemini rate limits or network failures occur, the pipeline automatically falls back to Groq, then Ollama, and finally deterministic rule-based heuristics.
- **Strict Provenance Separation**: LLM commentary is strictly demarcated from verified test runner outputs to prevent developer confusion.

---

## 5. Dependencies

### Python Core Dependencies (
equirements.txt)
| Package | Version | Purpose |
| :--- | :--- | :--- |
| google-genai | >=0.8.0 | Official Google GenAI SDK for Gemini 2.5 Flash integration |
| groq | >=0.4.0 | High-throughput Groq Cloud inference client |
| pydantic | >=2.6.0 | Robust schema definition, serialization, and capsule validation |
| pytest | >=8.0.0 | Test discovery and deterministic sandbox test execution |
| gitpython | >=3.1.40 | Programmatic Git operations, diff calculation, and branch management |
| python-dotenv | >=1.0.0 | Environment variable loading from root .env |
| 
ich | >=13.7.0 | Terminal formatting, tables, and progress visualization |
| 
equests | >=2.31.0 | HTTP client for Ollama local endpoints and external webhooks |
| click | >=8.1.0 | CLI command construction and option parsing |

### Python Backend Service Dependencies (ackend/requirements.txt)
| Package | Version | Purpose |
| :--- | :--- | :--- |
| astAPI | >=0.110.0 | High-performance asynchronous REST API framework |
| uvicorn | >=0.28.0 | ASGI production-grade web server |
| pydantic | >=2.6.0 | Request and response model validation |
| python-multipart| >=0.0.9 | Form data and file upload support |
| sse-starlette | >=2.0.0 | Server-Sent Events (SSE) for streaming real-time run logs |

### Frontend Dependencies (rontend/package.json)
| Package | Version | Purpose |
| :--- | :--- | :--- |
| 
eact | ^19.0.0 | UI component library |
| 
eact-dom | ^19.0.0 | React DOM renderer |
| ite | ^6.0.0 | Next-generation frontend bundler and HMR server |
| 	ypescript | ^5.6.0 | Strict type checking and interface contracts |
| lucide-react | ^0.460.0 | Clean, modern iconography |
| 	ailwindcss | ^3.4.0 | Utility-first styling framework |

---

## 6. AI Model Details

UMA is built on an adaptable multi-model backend. Below are the complete specifications of the supported language models:

### Model 1: Google Gemini 2.5 Flash (Primary)
| Field | Details |
| :--- | :--- |
| **Model Name** | Gemini 2.5 Flash |
| **Model Version** | gemini-2.5-flash |
| **Model Source** | Google DeepMind |
| **Access Method** | Cloud REST API via official google-genai Python SDK using GEMINI_API_KEY |
| **Applicable Model License / Usage Terms** | Google Generative AI Terms of Service / Google Cloud Platform License Agreement |
| **Role of the Model in the Project** | **Primary Reasoning Engine**: Performs initial repo log inspection, executes Chain-of-Verification (CoV) failure triage, synthesizes candidate unified diffs, analyzes sandbox test tracebacks for self-healing, and compiles PR release notes. |

### Model 2: Groq LLaMA 3.1 70B Versatile (Fallback 1)
| Field | Details |
| :--- | :--- |
| **Model Name** | LLaMA 3.1 70B Versatile |
| **Model Version** | llama-3.1-70b-versatile |
| **Model Source** | Meta AI (weights) hosted on Groq LPU Inference Cloud |
| **Access Method** | Cloud REST API via groq Python SDK using GROQ_API_KEY |
| **Applicable Model License / Usage Terms** | Meta Llama 3.1 Community License & Groq Terms of Service |
| **Role of the Model in the Project** | **High-Speed Secondary Fallback**: Deployed automatically when Gemini API quota is exhausted or latency-sensitive triage is requested. Conducts deep code reasoning and patch formatting. |

### Model 3: Ollama LLaMA 3 8B (Fallback 2 / Offline)
| Field | Details |
| :--- | :--- |
| **Model Name** | LLaMA 3 8B Instruct |
| **Model Version** | llama3:8b |
| **Model Source** | Meta AI (served locally via Ollama runtime) |
| **Access Method** | Local HTTP REST endpoint (http://localhost:11434/api/generate) |
| **Applicable Model License / Usage Terms** | Meta Llama 3 Community License |
| **Role of the Model in the Project** | **Air-Gapped / Offline Fallback**: Allows complete repository inspection and basic patch synthesis without sending proprietary source code across external networks. |

### LLM Priority and Fallback Cascade
`
  [Pipeline Request]
          |
          v
  +-----------------------+   Success
  | Google Gemini 2.5     | -----------> [Patch Synthesis / CoV]
  +-----------------------+
          | (Quota Exceeded / Rate Limit / Auth Error)
          v
  +-----------------------+   Success
  | Groq LLaMA 3.1 70B    | -----------> [Patch Synthesis / CoV]
  +-----------------------+
          | (Network Failure / No API Key)
          v
  +-----------------------+   Success
  | Local Ollama LLaMA 3  | -----------> [Patch Synthesis / CoV]
  +-----------------------+
          | (Ollama Offline)
          v
  +-----------------------+
  | Rule-Based Heuristics | -----------> [Static Diff / [UNVERIFIED] Tag]
  +-----------------------+
`

---

## 7. Known Limitations

While UMA introduces verifiable self-healing maintenance, users should be aware of the following design constraints and current limitations:

### LLM & Diagnostic Limitations
- **Multi-File Architectural Refactors**: UMA excels at localized repairs (1 to 5 related files). Broad cross-repository architectural migrations spanning dozens of modules can exceed context windows and degradation of patch coherence.
- **Subtle Semantic Drift**: While patches pass the existing unit test suite, insufficient or missing test coverage in the target repo can allow semantic regressions to pass undetected into the [EXECUTED] tier.
- **Complex Mocking Frameworks**: Highly intricate test suites relying on multi-tier network mocks or dynamic monkeypatching can occasionally cause the diagnostic agent to formulate incorrect verification hypotheses.

### Sandbox & Execution Limitations
- **OS Dependency Constraints**: The local sandbox executes tests within the host Python environment. Repositories requiring native C/C++ compilation, GPU drivers, or specific system packages must have those prerequisites pre-installed on the host.
- **Long-Running Test Suites**: To prevent unbounded execution, sandbox runs enforce a default 60-second timeout. Test suites that normally take tens of minutes cannot complete without adjusting SANDBOX_TIMEOUT_SECONDS.
- **Destructive Test Suites**: Repositories whose test suites drop databases or modify host filesystems should be executed inside dedicated containers (e.g. Docker) rather than directly on bare-metal workstations.

### Ecosystem & Language Support
- **Python-Centric Testing**: The current sandbox test harness is natively optimized for pytest and unittest. Other language runtimes (Node.js/Jest, Go test, Rust cargo test) require adding custom test runner adapters.
- **Dependency Isolation**: Sandbox runs share the virtual environment of the runner. Conflicting transitive dependencies in the target repo may require isolated venv cloning.

### Interactive PR Agent Limitations
- **Automated Merge Conflicts**: The PR generator produces unified diffs based on the HEAD commit observed during inspection. If concurrent commits are pushed to the target branch during execution, git rebase conflicts must be manually resolved by developers.
