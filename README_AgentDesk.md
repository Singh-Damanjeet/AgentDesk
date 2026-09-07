# AgentDesk

**Self-hosted AI customer support automation with grounded RAG, an embeddable website chat widget, ticketing, and traceable agent workflows.**

AgentDesk is a local-first customer support system designed to answer questions from your own knowledge base, create and manage support tickets, and safely hand off requests that need human or account-specific information.

It is built around a provider-independent LLM layer, so you can use **Google Gemini** or **OpenRouter** for generation and structured classification while keeping embeddings local.

---

## What AgentDesk does

- Upload support documentation in **PDF, DOCX, TXT, and Markdown**
- Parse, chunk, embed, index, re-index, and delete documents locally
- Answer support questions with **grounded RAG**
- Return **citations/sources** with supported answers
- Refuse to invent answers when the knowledge base has insufficient evidence
- Embed a website support widget with a single script tag
- Persist anonymous website conversations as support tickets
- Manage conversations from an Inbox
- Run support requests through a **LangGraph** workflow
- Record ordered **AgentRun / AgentStep** traces
- Detect account-specific questions and route them to human review instead of hallucinating customer state
- Switch between **Gemini** and **OpenRouter**
- Keep Sentence Transformers embeddings local

---

## Tech stack

| Layer | Technology |
| --- | --- |
| Backend | FastAPI, Python |
| Frontend | Next.js 16, React 19, TypeScript, Tailwind CSS |
| Database | SQLite, SQLAlchemy, Alembic |
| Agent workflow | LangGraph |
| LLM providers | Google Gemini, OpenRouter |
| Embeddings | Sentence Transformers |
| Vector search | Local vector store |
| Document parsing | pypdf, python-docx |
| HTTP client | httpx |
| Tests | pytest |

---

## Architecture

```text
External Website
      |
      v
widget.js + isolated chat iframe
      |
      v
Conversation / Ticket services
      |
      v
LangGraph support workflow
      |
      +--> Input Guard
      |
      +--> Structured Classification
      |       |
      |       +--> Account Data Guard --> Human Review
      |       |
      |       +--> Knowledge Retrieval
      |                |
      |                v
      |          Local Vector Store
      |                |
      |                v
      |             Generate
      |                |
      |                v
      |          Output Guard
      |
      v
Persist Message + Ticket + Agent Trace
      |
      v
AgentDesk Dashboard
```

Normal grounded requests follow:

```text
load_context
-> input_guard
-> classify
-> retrieve_knowledge
-> generate
-> output_guard
-> persist
```

Account-specific requests follow:

```text
load_context
-> input_guard
-> classify
-> account_data_guard
-> persist
```

AgentDesk V1 intentionally does **not** invent live account, refund, payment, subscription, shipment, or order status.

---

# Quick Start

## 1. Requirements

Install:

- **Python 3.12+** recommended
- **Node.js 20.9+**
- npm
- Git

You will also need an API key for at least one supported LLM provider:

- Google Gemini, or
- OpenRouter

> The LLM API key is entered through AgentDesk's setup/settings UI. Do not commit API keys to the repository.

An internet connection is required for LLM requests and may also be required the first time the local Sentence Transformers model is downloaded.

---

## 2. Clone the repository

```bash
git clone https://github.com/Singh-Damanjeet/AgentDesk.git
cd AgentDesk
```

If you want to test a development branch:

```bash
git checkout feat/v1-runtime-foundation
```

---

## 3. Create a Python virtual environment

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### Windows PowerShell

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
```

---

## 4. Install backend dependencies

From the AgentDesk repository root:

```bash
pip install -r backend/requirements.txt
```

---

## 5. Install frontend dependencies

```bash
cd frontend
npm install
cd ..
```

---

## 6. Start AgentDesk

From the repository root:

```bash
python run.py
```

AgentDesk uses fixed local ports:

- Dashboard: `http://localhost:3000`
- Backend: `http://127.0.0.1:8000`
- FastAPI docs: `http://127.0.0.1:8000/docs`

The launcher starts the backend and frontend and opens AgentDesk in your browser.

Press `Ctrl+C` in the terminal to stop AgentDesk.

---

# First-run setup

On a fresh installation, AgentDesk opens the setup wizard.

Complete:

1. **Company**
   - Company name
   - Support identity
   - Language/timezone settings

2. **AI Provider**
   - Gemini or OpenRouter
   - Model
   - API key
   - Test Connection

3. **Local Storage**

4. **Finish**

After setup, restarting AgentDesk should open the dashboard rather than the setup wizard.

---

# AI providers

## Google Gemini

Select:

```text
Provider: Gemini
Model: a supported Gemini model
API Key: your Gemini API key
```

The project has been tested with:

```text
gemini-3.6-flash
```

Use **Test Connection** before saving.

### Gemini quota errors

If a working key later returns:

```text
HTTP 429
RESOURCE_EXHAUSTED
```

the provider quota/rate limit has been exhausted. This is different from an invalid API key or invalid model.

Wait for quota to recover, use another valid provider configuration, or increase provider quota.

---

## OpenRouter

Select:

```text
Provider: OpenRouter
Model: <OpenRouter model slug>
API Key: sk-or-v1-...
```

AgentDesk sends requests through:

```text
https://openrouter.ai/api/v1/chat/completions
```

For AgentDesk's classifier, the selected OpenRouter model/provider route must support strict JSON-schema structured output.

AgentDesk's OpenRouter integration uses:

```text
response_format.type = json_schema
strict = true
provider.require_parameters = true
stream = false
```

**Test Connection validates the real structured classification path**, not only a simple text response.

If ordinary chat works but Test Connection says the model is incompatible, choose another OpenRouter model with JSON-schema structured-output support.

> OpenRouter free models and provider routes can change over time. Do not assume a model is compatible only because it can produce normal text.

---

# Knowledge Base

Open:

```text
Dashboard -> Knowledge Base
```

Supported formats:

- `.pdf`
- `.docx`
- `.txt`
- `.md`

Typical flow:

```text
Upload
-> Processing
-> Ready
```

Once ready, the document is available for local semantic retrieval.

AgentDesk supports safe upload handling, normalization, chunking, local embeddings, local vector indexing, re-indexing, and delete cleanup.

Re-indexing is designed not to create duplicate chunks.

---

# Test RAG

Open:

```text
Dashboard -> Knowledge Base -> Test
```

Ask a question that is explicitly covered by your uploaded documentation.

Example:

```text
How long do I have to request a refund?
```

A grounded response should use retrieved knowledge and show its source/citation.

For unsupported facts, AgentDesk should say it does not have enough evidence rather than inventing an answer.

Example:

```text
Does AcmeFlow have offices in Japan?
```

---

# Website Chat Widget

AgentDesk can be embedded into an external website using the widget loader.

Example:

```html
<script
  src="http://127.0.0.1:8000/widget.js"
  data-project="local-default"
></script>
```

Before embedding:

1. Open **Dashboard -> Website Chat**
2. Enable the widget
3. Add the exact website origin to **Allowed Origins**

For example:

```text
http://localhost:3002
```

Origins are checked exactly. Do not use an unrelated or wildcard origin.

---

## Run the included demo website

Keep AgentDesk running.

In another terminal:

```bash
cd demo-widget-site
python -m http.server 3002
```

Then open:

```text
http://localhost:3002
```

The demo validates that the support widget remains isolated from aggressive host-page CSS.

---

# Inbox and Tickets

Open:

```text
Dashboard -> Inbox
```

Website conversations create persistent support tickets.

The Inbox includes customer/anonymous messages, AI replies, ticket status, conversation history, channel information, and links to execution traces.

Account-specific requests are routed safely to human review when AgentDesk has no live customer-system integration.

---

# Agent Runs

Open:

```text
Dashboard -> Agent Runs
```

Each support request records an `AgentRun` and ordered `AgentStep` entries.

A normal knowledge-backed request may show:

```text
load_context
input_guard
classify
retrieve_knowledge
generate
output_guard
persist
```

An account-specific request may show:

```text
load_context
input_guard
classify
account_data_guard
persist
```

Trace metadata is designed to contain useful operational diagnostics without exposing API keys or raw secrets.

---

# Local data and security

AgentDesk V1 is local/self-hosted.

Security measures include:

- encrypted server-side LLM API key storage
- masked secrets in the UI
- no API keys in public widget responses
- no authorization headers in traces
- exact widget-origin validation
- narrow widget CORS handling
- safe document filenames/storage
- account-data hallucination guard
- prompt-injection defenses for retrieved content
- local embeddings

Runtime databases, secret files, uploaded knowledge, virtual environments, frontend build artifacts, and local environment files should remain ignored by Git.

> **Important:** V1 is intended for local/self-hosted use and evaluation. Do not expose the administrative dashboard directly to the public internet without adding appropriate authentication, network controls, and deployment hardening.

---

# Run the test suite

## Backend

```bash
cd backend
python -m pytest -v
```

## Database migrations

From `backend/`:

```bash
alembic current
alembic heads
alembic check
```

## Frontend

From `frontend/`:

```bash
npm run lint
npx tsc --noEmit
```

Production build:

```bash
npm run build
```

If your environment restricts Turbopack worker/network behavior, the project can also be validated with the Webpack production build:

```bash
npx next build --webpack
```

---

# Troubleshooting

## Port 8000 or 3000 is already in use

AgentDesk expects:

```text
Backend: 8000
Frontend: 3000
```

Check the process using the port.

macOS/Linux:

```bash
lsof -i :8000
lsof -i :3000
```

Stop the stale process and run:

```bash
python run.py
```

Do not silently move the frontend to another port because the local configuration expects port `3000`.

---

## Gemini returns 429 RESOURCE_EXHAUSTED

The key/model can be valid while the provider quota is exhausted.

Do not repeatedly retry requests. Wait for quota recovery or switch to another configured LLM provider.

---

## OpenRouter chat works but classification fails

AgentDesk requires structured JSON classification.

Use **Test Connection** with the selected model. Choose a model/provider route that supports JSON-schema `response_format`.

---

## Widget does not appear

Check:

- AgentDesk backend is running on `8000`
- Website Chat is enabled
- `data-project` is correct
- your website's **exact origin** is allowed
- the page can reach `/widget.js`

---

## First embedding request is slow

Sentence Transformers run locally. The first run may need to download/load the embedding model. Later requests should use the local cached model.

---

# Repository structure

```text
AgentDesk/
├── backend/
│   ├── alembic/
│   ├── app/
│   │   ├── agent/
│   │   ├── ai/
│   │   ├── api/
│   │   ├── knowledge/
│   │   ├── models/
│   │   ├── rag/
│   │   ├── services/
│   │   └── widget/
│   ├── tests/
│   ├── alembic.ini
│   └── requirements.txt
│
├── frontend/
│   ├── src/
│   └── package.json
│
├── demo-widget-site/
│   ├── index.html
│   ├── styles.css
│   └── README.md
│
└── run.py
```

Additional V1 hardening/demo files may include release-acceptance documentation, sample support documents, screenshots, and local helper scripts.

---

# Current V1 scope

AgentDesk V1 focuses on **read-only, grounded customer support automation**.

Included:

- native/local installation
- setup wizard
- Knowledge Base
- RAG
- citations
- tickets
- website widget
- LangGraph orchestration
- execution traces
- Gemini/OpenRouter provider abstraction
- local embeddings
- safety/human-review routing

Not included in V1:

- live business-system write actions
- account-data integrations
- approval workflows
- email automation
- OCR for scanned PDFs
- enterprise authentication/RBAC
- cloud deployment automation
- Docker/Kubernetes deployment configuration

These capabilities are intentionally outside the V1 release boundary.

---

# Development status

AgentDesk V1 has completed its main implementation and hardening work, including clean installation, restart persistence, Knowledge Base ingestion/re-index/delete, grounded RAG, account-data safety, widget isolation, origin security, execution tracing, and automated regression testing.

Some live-provider acceptance checks can be temporarily blocked by third-party API quota/rate limits. Provider quota failures are recorded separately from application failures.

---

## API reference

With AgentDesk running, FastAPI's interactive API documentation is available at:

```text
http://127.0.0.1:8000/docs
```

---

## Feedback

If you find a reproducible bug, open a GitHub issue with:

- operating system
- Python version
- Node.js version
- AgentDesk branch/commit
- steps to reproduce
- expected behavior
- actual behavior
- safe logs/trace metadata

Never include API keys, Authorization headers, or other secrets in issue reports.
