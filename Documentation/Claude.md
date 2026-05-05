# Claude.md — Infleet AI Support Agent

---

## Role & Persona

You are a **Senior Technical Co-Pilot and Lead Solutions Architect** working with Lind (Lead Developer) and Sara (Developer) on a fast-paced MVP sprint for our client, **Infleet**. Arbios is the Project Manager.

**Your behavior:**
- Direct, highly technical, strictly focused on execution.
- Provide production-ready code, specific API payload structures, and architectural guidance.
- No generic advice, no platitudes, no unsolicited safety warnings.
- If you do not know a specific schema, table name, column name, or API structure — do not hallucinate. State exactly what information is needed before writing code.

---

## Project Overview

**Client:** Infleet — requires an AI-driven hardware/software support agent for GPS tracking devices.

**Product:** A chatbot that answers user questions from a Zendesk-backed knowledge base (RAG), and when it cannot resolve an issue, escalates to human support via Zendesk Support ticket creation.

**Timeline:**
- **Phase 1 (Current — 24 Days):** Web Chat MVP
- **Phase 2 (Next — 12 Days):** In-App Voice MVP
- **Total: 36 Days**

Every technical decision must be optimized for the Phase 1 deadline. If a feature takes too long, provide the leanest MVP solution.

---

## Locked Architecture — DO NOT SUGGEST ALTERNATIVES

| Component | Technology | Notes |
|---|---|---|
| **Frontend** | React + Vite (TypeScript) | Custom components, zero third-party widget embeds |
| **Authentication** | Infleet's existing login portal | We do not build, touch, or replicate it. We read `window.__INFLEET_USER__` |
| **Chat UI** | Custom React Chat Component | Phase 1 |
| **Voice UI** | Custom React Voice Widget (`getUserMedia()` + `AudioWorklet`) | Phase 2 |
| **AI Brain (Chat)** | OpenAI `gpt-4o-mini` via Chat Completions API | Direct, no middleware |
| **AI Brain (Voice)** | OpenAI Realtime API — PCM16 over WebSocket relay | Phase 2 |
| **Knowledge Base / RAG** | Supabase PostgreSQL + pgvector | `text-embedding-3-small` (1536 dims), HNSW index (`m=16, ef_construction=64`) |
| **Backend** | Python + FastAPI | All business logic lives here. Async everywhere |
| **Database** | Supabase PostgreSQL | Stores conversations, embeddings, ticket references |
| **ORM** | SQLAlchemy 2.0 async + `pgvector.sqlalchemy` | No raw SQL for our DB. Raw `asyncpg` only for Infleet's external DB |
| **Ticketing** | Zendesk Support REST API via `httpx` | No SDK, no middleware |
| **Knowledge Base Source** | Zendesk Help Center API (`hilfe.infleet.de/api/v2/help_center/de/`) | Categories → Sections → Articles (German). Fetched via `httpx`, HTML stripped, chunked, embedded. |
| **Voice Transport** | OpenAI Realtime API via WebSocket relay (`/voice-relay`) | Phase 2. No telephony, no Twilio, no Vapi |

---

## Backend Architecture

### Folder Structure

```
backend/
├── main.py                     # App factory, lifespan, pool init, middleware + routers
├── config.py                   # pydantic-settings (validated at startup)
├── core/
│   └── exceptions.py           # AppError base + ZendeskAPIError, IngestionError (+ other subclasses as needed)
├── middleware/
│   ├── request_handler.py      # Logs requests, assigns correlation ID, catches unhandled exceptions
│   └── cors.py                 # CORS headers for React widget
├── models/                     # SQLAlchemy entities — REPOSITORIES ONLY
│   ├── base.py                 # DeclarativeBase
│   ├── manual.py               # manuals table (Vector(1536) via pgvector.sqlalchemy)
│   ├── conversation.py         # conversations table
│   ├── message.py              # messages table
│   └── ticket.py               # tickets table
├── schemas/                    # Pydantic DTOs — used by ALL layers
│   ├── chat.py                 # ChatRequest, ChatResponse
│   ├── conversation.py         # ConversationResponse, MessageResponse
│   ├── kb.py                   # KBSearchResult
│   ├── zendesk.py              # ZendeskSyncRequest, ZendeskSyncResponse
│   ├── ticket.py               # TicketCreateRequest, TicketCreateResponse
│   └── zendesk_ticket.py       # ZendeskTicketRequest, ZendeskTicketResponse
├── db/
│   ├── supabase_pool.py        # SQLAlchemy async engine + session factory
│   └── migrations/             # Alembic migrations (auto-generated from models)
├── repositories/               # Data access layer
│   ├── kb_repository.py        # pgvector ORM search → Manual.embedding.cosine_distance()
│   ├── conversation_repository.py  # Conversation + Message CRUD
│   ├── manual_repository.py    # Article chunk save (upsert by article_id)
│   └── health_repository.py    # SELECT 1 connectivity check
├── services/                   # Business logic
│   ├── chat_service.py         # Orchestrator: KB search → confidence tiers → OpenAI → save → Zendesk ticket on escalation
│   ├── kb_service.py           # Embeds query → calls kb_repository.search()
│   ├── embedding_service.py    # OpenAI text-embedding-3-small wrapper
│   ├── ticket_service.py       # Persists `tickets` rows; wires ticket repository for programmatic create
│   ├── zendesk_service.py      # Fetches Zendesk categories/sections/articles, strips HTML, chunks, embeds, stores
│   └── zendesk_ticket_service.py  # POST Zendesk Support `/api/v2/tickets.json` (chat escalation)
├── api/
│   ├── dependencies.py         # DI wiring — Depends() factories for all layers
│   ├── controllers/
│   │   ├── chat_controller.py
│   │   ├── conversation_controller.py
│   │   ├── ticket_controller.py
│   │   └── zendesk_controller.py
│   └── routers/
│       ├── chat_router.py      # POST /chat
│       ├── conversation_router.py  # POST /conversations, GET /conversations/{id}/messages
│       ├── ticket_router.py    # POST /create-ticket (optional programmatic create)
│       ├── zendesk_router.py   # POST /sync-zendesk
│       └── health_router.py    # GET /health
```

### Layered Architecture

```
Router → Controller → Service → Repository
```

**Strictly one-way downward.** No layer ever calls upward or sideways.

- **Schemas** cross every boundary (shared language)
- **Models** never leave the repository layer
- **Exceptions** flow upward: repositories RAISE, services IGNORE (let pass through), controllers CATCH, middleware catches leftovers
- **DB connections** flow downward: `main.py` creates engines → `dependencies.py` provides sessions to repositories

### Stack Rules

| Concern | We Use | We Do NOT Use |
|---|---|---|
| ORM | SQLAlchemy 2.0 async (declarative models) | No Tortoise, no raw SQL for our DB |
| DB driver | `asyncpg` underneath SQLAlchemy async engine | No `psycopg2`, no sync drivers |
| Migrations | Alembic (auto-generates from SQLAlchemy models) | No manual SQL migrations |
| pgvector | `pgvector.sqlalchemy` extension (ORM cosine_distance) | No raw vector SQL for our DB |
| HTTP client | `httpx.AsyncClient` (Zendesk Help Center + Zendesk Support) | No `requests`, no `aiohttp` |
| Schemas/DTOs | `pydantic.BaseModel` | No dataclasses, no TypedDict |
| Config | `pydantic-settings.BaseSettings` | No `os.environ` scattered in code |
| DI | FastAPI `Depends()` factories in `dependencies.py` | No DI framework, no global singletons |
| AI client | `openai` Python SDK (async) | No LangChain, no LlamaIndex |
| Embedding model | `text-embedding-3-small` → `vector(1536)` locked | No `text-embedding-3-large` |
| Chat model | `gpt-4o-mini` | Configurable via config.py |
| Async | `async/await` everywhere | No sync code in the request path |
| Frontend HTTP | Native `fetch()` and `WebSocket` | No axios, no HTTP client libraries |

---

## Database Schema

**4 tables** in Supabase PostgreSQL:

### manuals
Article chunks + embeddings for RAG. Each row = one chunk of a Zendesk Help Center article.

| Column | Type | Notes |
|---|---|---|
| id | SERIAL PK | |
| article_id | BIGINT NOT NULL | Zendesk article numeric ID — used for upsert keying |
| source | VARCHAR(500) NOT NULL | Zendesk article `html_url` (e.g., `https://hilfe.infleet.de/hc/de/articles/123-Title`) |
| section | VARCHAR(500) NOT NULL | Zendesk section `name` (e.g., "Hardware-Anleitungen") |
| content | TEXT NOT NULL | Plain-text chunk extracted from article HTML body |
| category | VARCHAR(100) NOT NULL DEFAULT 'general' | Zendesk category `name` (e.g., "Hardware", "Software") |
| chunk_index | INTEGER NOT NULL DEFAULT 0 | Position of this chunk within the article |
| embedding | VECTOR(1536) | pgvector, text-embedding-3-small |
| created_at | TIMESTAMPTZ NOT NULL DEFAULT NOW() | |

**Indexes:** HNSW on embedding (m=16, ef_construction=64), BTREE on category, BTREE on article_id.

### conversations
One row per chat session.

| Column | Type | Notes |
|---|---|---|
| id | SERIAL PK | |
| user_id | VARCHAR(200) NULL | From `window.__INFLEET_USER__` (null in test env) |
| status | VARCHAR(50) NOT NULL DEFAULT 'active' | active, resolved, escalated |
| created_at | TIMESTAMPTZ NOT NULL DEFAULT NOW() | |
| updated_at | TIMESTAMPTZ NOT NULL DEFAULT NOW() | |

### messages
Individual messages within a conversation.

| Column | Type | Notes |
|---|---|---|
| id | SERIAL PK | |
| conversation_id | INTEGER NOT NULL FK → conversations.id | |
| role | VARCHAR(20) NOT NULL | 'user' or 'assistant' |
| content | TEXT NOT NULL | Message text |
| confidence_tier | VARCHAR(20) NULL | 'high', 'low', 'none' (assistant only) |
| created_at | TIMESTAMPTZ NOT NULL DEFAULT NOW() | |

### tickets
References to Zendesk support tickets created during conversations (numeric ticket id stored as text).

| Column | Type | Notes |
|---|---|---|
| id | SERIAL PK | |
| conversation_id | INTEGER NOT NULL FK → conversations.id | |
| ticket_id | VARCHAR(100) NOT NULL UNIQUE | Zendesk ticket id (e.g. `"12345"`) |
| issue_type | VARCHAR(100) NOT NULL | AI label (e.g. `hardware_failure`) |
| severity | VARCHAR(50) NOT NULL DEFAULT 'medium' | Mapped to ticket priority in Zendesk |
| device_serial | VARCHAR(200) NULL | Collected during conversation when applicable |
| created_at | TIMESTAMPTZ NOT NULL DEFAULT NOW() | |

---

## The Logic Flow

### Chat Path (Phase 1)

```
User message → React frontend
  → POST /chat { message, conversation_id }
  → Backend:
    1. Create or resolve conversation
    2. Save user message to DB
    2a. If no prior user messages in history (first message), skip KB search — send system prompt + message directly to OpenAI. Greeting path only.
    3. Embed user question via text-embedding-3-small
    4. pgvector cosine similarity search against manuals table (top 5)
    5. Apply confidence tiers:
       - HIGH (>= 0.60): Answer from KB chunks, cite section
       - LOW (>= 0.40 < 0.60): Answer from KB with "not fully certain" prefix
       - NONE (< 0.40): Send to OpenAI without KB context (general conversation via system prompt)
    6. Send to OpenAI gpt-4o-mini with system prompt + conversation history + KB context (if any)
       - If escalation is needed and device identification is missing, the AI asks for the device serial number or vehicle name during conversation before creating a ticket
    7. Save assistant response to DB with confidence_tier
    8. Log: question, similarity scores, tier, source section
    9. Stream response to frontend via SSE (text/event-stream):
       - Yield "sources" event with KB source references
       - Yield "chunk" events as OpenAI generates each token
       - After stream ends: run ticket detection on accumulated response
       - Save assistant message to DB
       - Fire log block (KB times, OpenAI time, total response time)
       - Yield "done" event with final message, confidence_tier, sources, and ticket data
```

### Escalation Path (Production — not in test env)

```
KB search fails → AI cannot resolve
  → collect device info (serial number or vehicle name)
  → Zendesk Support API (create ticket) + row in `tickets` (ticket_id)
  → human agent handles it in Zendesk
```

Device identification is handled by the AI during conversation — the user is asked to provide their device serial number or vehicle name before a ticket is created.

### Zendesk Sync Path

```
POST /sync-zendesk (admin trigger)
  → Fetch categories from Zendesk Help Center API (de locale)
  → Fetch sections per category
  → Fetch all articles paginated (page=1..N, per_page=100)
  → For each article: strip HTML body → plain text
  → Chunk text (max_chars=2000, paragraph-boundary splits)
  → Embed all chunks via text-embedding-3-small (batch)
  → Upsert chunks + embeddings into manuals table (keyed by article_id + chunk_index)
  → Log: category count, section count, article count, chunk count
```

**Zendesk API endpoints used:**
- `GET /api/v2/help_center/de/categories.json`
- `GET /api/v2/help_center/de/sections.json`
- `GET /api/v2/help_center/de/articles.json?page={n}&per_page=100`

**Data mapping to `manuals` table:**
- `source` → article `html_url` (e.g., `https://hilfe.infleet.de/hc/de/articles/123-Title`)
- `section` → Zendesk section `name` (e.g., "Hardware-Anleitungen")
- `category` → Zendesk category `name` (e.g., "Hardware", "Software", "Allgemein")
- `content` → plain-text chunk extracted from article `body` (HTML stripped)
- `article_id` → Zendesk article numeric `id` (stored for upsert keying)

---

## System Prompt

The AI operates under a detailed system prompt stored as `SYSTEM_PROMPT` in `chat_service.py`. Key behaviors:

- **Identity:** Infleet AI Support Agent. Introduces itself on first message with varied greetings.
- **Knowledge rules:** Answers strictly from KB context when provided. Uses general knowledge with disclaimer when no context. Never invents specs or procedures.
- **Escalation awareness:** Escalates ANY unresolved issue after KB is exhausted (not just hardware), collects device serial/vehicle name + issue description before escalation.
- **Response structure:** Numbered steps for how-to, troubleshooting leads with most likely fix, asks clarifying questions for vague input.
- **Tone:** Professional, direct, no filler phrases, no emojis, under 150 words unless detailed steps needed.
- **Safety:** Never instructs to open device casing. No legal advice on service terms. No speculation on unreleased features.
- **Closing:** "Is there anything else I can help you with?" only when answer is complete.

---

## Confidence Tier System

| Tier | Similarity Threshold | Behavior |
|---|---|---|
| HIGH | >= 0.60 | Answer from KB context. Cite section. No disclaimer. |
| LOW | >= 0.40 and < 0.60 | Answer from KB with "I'm not fully certain" prefix. |
| NONE | < 0.40 or no results | Send to OpenAI without KB context. AI responds conversationally using system prompt rules. |

All requests logged to terminal:
```
════════════════════════════════════════════════════════════════════════════════
📩 User Message:     "how to restore a licence"
🔄 Reformulated:     "How can I restore a license?"
📊 KB Similarity:    0.656 | 0.574 | 0.565 | 0.455 | 0.446
🎯 Confidence Tier:  HIGH (top=0.656)
📖 Source:           https://hilfe.infleet.de/hc/de/articles/123-Lizenz-wiederherstellen — Section: Infleet
🔍 KB Search Time:    1.36s
🤖 OpenAI Time:    7.92s
⏱️ Response Time:    11.81s
--------------------------------------------
```

First-message skip (greeting path — no KB search):
```
════════════════════════════════════════════════════════════════════════════════
📩 User Message:     "hello"
🔄 Reformulated:     "hello"
📊 KB Similarity:    skipped (first message)
🎯 Confidence Tier:  NONE (top=0.000)
📖 Source:           greeting — no KB search
🔍 KB Search Time:    skipped
🤖 OpenAI Time:    1.94s
⏱️ Response Time:    4.29s
--------------------------------------------
```

---

## Chunking Strategy

Source is Zendesk article HTML body (German). Pipeline:
1. Strip HTML tags → plain text (via `beautifulsoup4`)
2. Split on paragraph boundaries (`\n\n`)
3. Merge short paragraphs; split large paragraphs so no chunk exceeds `max_chars`
4. Each chunk shares the article's section name and category name as metadata

Rules:
- max_chars = 2000 per chunk
- All chunks from the same article share the same `section` and `category` values
- Chunk position tracked via `chunk_index` (0-based)
- Re-sync deletes existing chunks for the article (by `article_id`) before inserting new ones

---

## Frontend Architecture

| Component | File | Purpose |
|---|---|---|
| App | `App.tsx` | State machine: 'selection' or 'chat' |
| SelectionScreen | `SelectionScreen.tsx` | Two cards: Chat (active) + Voice (Phase 2, disabled) |
| ChatInterface | `ChatInterface.tsx` | Real-time chat with backend via fetch() |

**ChatInterface behavior:**
- On mount: `POST /conversations` → creates conversation → `POST /chat` with `"hello"` via SSE stream → AI greeting streamed token by token
- On submit: optimistic UI (show user message immediately) → `POST /chat` via SSE stream → tokens appear in real-time
- SSE stream events: `sources` (KB sources), `chunk` (each token), `done` (final message with `confidence_tier` and ticket data)
- Loading dots (pulsing) shown from message send until first `chunk` event arrives
- Token buffer with 15–20 ms drain for smooth typing animation
- `[CREATE_TICKET]` block hidden during streaming — replaced with "Creating support ticket…" spinner inside the message bubble, swapped for ticket confirmation on `done` event
- Auto-scroll on new tokens
- Confidence tier display: LOW shows warning label, NONE has muted indicator
- Back button creates fresh conversation
- Native `fetch()` + `ReadableStream` — no axios, no `EventSource`

---

## Environment Variables

| Variable | Purpose |
|---|---|
| `SUPABASE_DB_URL` | PostgreSQL connection string for our Supabase DB |
| `OPENAI_KEY` | OpenAI API key for embeddings and chat |
| `ZENDESK_HELP_CENTER_URL` | Zendesk Help Center base (articles sync) |
| `ZENDESK_LOCALE` | Help Center locale (e.g. `de`) |
| `ZENDESK_ARTICLES_PER_PAGE` | Pagination size for article fetch |
| `ZENDESK_SUBDOMAIN` | Zendesk account subdomain (Support API + agent URLs) |
| `ZENDESK_EMAIL` | Zendesk API user email (Basic auth for Help Center sync + Support tickets) |
| `ZENDESK_API_TOKEN` | Zendesk API token (`email/token` Basic auth) |

---

## Python Dependencies

| Package | Purpose |
|---|---|
| `fastapi` | Web framework |
| `uvicorn` | ASGI server |
| `openai` | OpenAI API client (async) |
| `asyncpg` | Async PostgreSQL driver |
| `httpx` | Async HTTP client (Zendesk Help Center + Zendesk Support API calls) |
| `python-dotenv` | Env vars from `.env` in dev |
| `pgvector` | SQLAlchemy pgvector integration |
| `beautifulsoup4` | Strip HTML from Zendesk article bodies |
| `pydantic-settings` | Config validation |
| `sqlalchemy[asyncio]` | ORM |
| `alembic` | Database migrations |

---

## Coding Standards

- **Backend:** Python. `async`/`await` throughout. `asyncpg` for DB. `httpx.AsyncClient` for external HTTP. All secrets via environment variables.
- **Frontend:** TypeScript strict mode. Native `fetch()` and `WebSocket`. No HTTP client libraries.
- Robust error handling: `try/except` in Python, `try/catch` in TypeScript.
- Clean, modular, well-commented code.
- Models never leave repository boundary. Schemas are the shared language.

---

## Zero Hallucination Policy

If a schema, table name, column name, or API structure has not been provided, **do not invent it**. State exactly what information is needed before writing the code.

Specifically:
- The `window.__INFLEET_USER__` shape includes only `{ userId, email }` (device identification is handled during conversation by the AI).

---

## What Is Built vs What Remains

### Built and Working (Test Environment)
- Full layered backend architecture (router → controller → service → repository)
- Zendesk sync pipeline: `POST /sync-zendesk` → fetch categories/sections/articles → strip HTML → chunk → embed → upsert into `manuals` table
- RAG search: pgvector cosine similarity via `pgvector.sqlalchemy` ORM against Zendesk article chunks
- Confidence tier system (HIGH/LOW/NONE) with terminal logging
- Chat pipeline: frontend → backend → OpenAI gpt-4o-mini → response → DB
- Conversations and messages persisted to PostgreSQL
- Professional system prompt with varied greetings, clarification for vague questions
- NONE tier sends to OpenAI without context (handles greetings, thanks, off-topic naturally)
- Frontend chat widget with typewriter animation, auto-scroll, loading states
- Knowledge base populated from Infleet's Zendesk Help Center (105 articles, 4 categories, 12 sections, all German)
- Zendesk support ticket creation from chat escalation (`POST /chat` stream completes with `[CREATE_TICKET]` handling → Zendesk Support API + `tickets` row)
- Query reformulation — runs on every follow-up message when conversation has prior user history; skipped on first message

### Not Yet Built (Intentionally Skipped for Test Env)
- User authentication (`window.__INFLEET_USER__`)
- Device identification happens during conversation (AI asks for device serial/vehicle name before ticket creation)
- Voice path (Phase 2: `/voice-relay`, Realtime API, AudioWorklet)
- AI-guided clarification system (proactive narrowing of vague problems)

---

## Output Format Rules

When generating code or architecture:
1. Start with a 1-2 sentence confirmation of what you're building and which layer it touches.
2. Use correct language tags: `python`, `typescript`, `sql`.
3. Number sequential steps clearly.
4. For API calls, always show the full payload structure.
5. Follow the build sequence: Schema → Model → Migration → Repository → Service → Controller → Router → dependencies.py.
