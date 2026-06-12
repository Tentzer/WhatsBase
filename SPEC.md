# Build spec: WhatsApp AI Agent Builder Platform

You are building a multi-tenant SaaS platform. Read this entire spec before writing any code, then propose a plan for Milestone 1 and wait for my approval before implementing.

## What we are building

A platform where a business owner signs up on a website, uploads their product photos, prices, and business context, and gets a working AI sales agent on WhatsApp. Think "Base44, but the output is a WhatsApp chatbot instead of an app."

Two AI components, strictly separated:

1. **Builder agent** (`backend/app/builder/`) — an autonomous agent with tools. Triggered when an owner submits onboarding data. It inspects whatever was uploaded (photos, price lists, free text), captions and structures products with a vision model, builds the tenant's knowledge base (embeddings), generates the tenant's system prompt and rules, binds the WhatsApp instance, and runs a mandatory self-test before the agent goes live. Runs once per onboarding/update.
2. **Conversation agent** (`backend/app/runtime/`) — handles every incoming WhatsApp message from end customers. Loads the tenant's config and knowledge base produced by the Builder, answers questions, searches products, sends photos with prices. One shared runtime serves all tenants; per-tenant behavior comes entirely from data in the database.

These modules must never import each other. The database is their only interface: Builder writes, runtime reads.

## Hard constraints

- **A live demo happens this Sunday.** Milestone order below is non-negotiable: the end-to-end demo path (ingest catalog → customer asks on WhatsApp → bot replies with correct photos + prices) must work before any dashboard/polish work begins.
- Multi-tenant from day one: every domain table carries `tenant_id`; never assume a single tenant in code, even though the demo uses one.
- All model choices live in ONE config module (`backend/app/core/models.py`): provider, model name, and parameters per role (agent / vision / embeddings). Swapping any model must be a one-line change.
- The WhatsApp provider (Green API) is hidden behind an adapter interface. No Green API types or URLs may leak outside the adapter module.
- Hebrew + English support from day one: the agent mirrors the customer's language, product captions are generated in both languages, the web UI supports RTL.

## Locked tech stack (do not substitute)

| Layer | Choice |
|---|---|
| Backend | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 (async) + Alembic |
| Database | Supabase: Postgres + pgvector, Supabase Auth, Supabase Storage for images |
| Queue | Redis + `arq` (async workers). Redis via docker-compose locally, Railway plugin in prod |
| WhatsApp | Green API (`whatsapp-api-client-python`), wrapped in our adapter |
| Conversation agent model | Anthropic API, `claude-sonnet-4-6`, native tool use, plain tool-calling loop (NO LangChain/LangGraph/CrewAI) |
| Vision captioning | OpenAI `gpt-4o-mini` (batch, structured JSON output) |
| Embeddings | OpenAI `text-embedding-3-large` (multilingual, covers Hebrew) |
| Frontend | Next.js 15 (App Router) + TypeScript + Tailwind + shadcn/ui, Supabase Auth on the client |
| Observability | Langfuse cloud (Python SDK decorators on every LLM call and agent run) |
| Deploy | Railway: FastAPI service + arq worker service + Redis. Vercel: Next.js. |

## Repository layout (monorepo)

```
/backend
  app/
    core/        # config, models.py (model registry), db, supabase client, langfuse setup
    adapters/
      whatsapp/  # base.py (interface), green_api.py, polling.py
    builder/     # autonomous builder agent: agent.py, tools/, validation.py, report.py
    runtime/     # conversation agent: loop.py, tools/, memory.py, guardrails.py
    retrieval/   # hybrid search over pgvector
    intake/      # webhook router, debouncer, arq tasks
    api/         # REST routes consumed by the frontend
  alembic/
  tests/
/frontend        # Next.js app
/infra           # docker-compose.yml (redis), railway/vercel configs, .env.example
SPEC.md          # this file — keep it updated as decisions change
```

## Data model (Postgres, all tables have id, tenant_id where applicable, created_at, updated_at)

- `tenants` — business name, status, plan
- `users` — Supabase auth users linked to a tenant
- `whatsapp_instances` — tenant_id, green_api_instance_id, token (encrypted), phone, status, intake_mode
- `agents` — tenant_id, generated system_prompt, tone, language_policy, rules (jsonb), escalation settings, status (building | live | failed), version
- `products` — tenant_id, name_he, name_en, description_he, description_en, category, attributes (jsonb: colors, materials, style…), price, currency, in_stock, source (owner_input | builder_extracted)
- `product_images` — product_id, storage_path, public_url, caption_he, caption_en
- `embeddings` — tenant_id, ref_type (product | business_info), ref_id, content, vector `halfvec(3072)` (stored as half-precision so an HNSW index is buildable at the registry's native 3072 dims — the `vector` type caps HNSW at 2000; registry stays text-embedding-3-large @ 3072), HNSW index with `halfvec_cosine_ops`, plus a GIN index on a metadata jsonb column for hybrid filtering. A `status` column (staging | active) supports the atomic stage→swap rebuild.
- `business_info` — tenant_id, topic (hours | location | policy | faq | other), content_he, content_en
- `conversations` — tenant_id, customer_phone, status, last_message_at
- `messages` — conversation_id, direction, type (text | image), content, media_url, agent_trace_id (Langfuse)
- `build_runs` — tenant_id, status, input_manifest (jsonb), report (jsonb), error, started/finished timestamps

## Component specs

### 1. WhatsApp adapter (`adapters/whatsapp/`)
- `base.py`: abstract interface — `send_text(chat_id, text)`, `send_image(chat_id, image_url, caption)`, `get_incoming() -> list[IncomingMessage]`, `ack(notification_id)`. Normalized `IncomingMessage` dataclass (instance_id, chat_id, sender, type, text, media…).
- `green_api.py`: implementation using the official Python client. Per-tenant credentials loaded from `whatsapp_instances`.
- Two intake modes behind `INTAKE_MODE` env/config per instance:
  - `webhook` (production): FastAPI route `/webhooks/greenapi/{instance_id}` validates, normalizes, enqueues, returns 200 immediately.
  - `polling` (local dev + demo insurance): an asyncio loop per active instance calling `receiveNotification`/`deleteNotification`, feeding the SAME queue. Demo must be runnable fully locally in polling mode with zero public URL.

### 2. Intake & queue (`intake/`)
- arq task queue on Redis. Job types: `process_incoming_message`, `run_build`, `send_outgoing`.
- **Debouncing**: when a message arrives, wait 2.5s; if more messages from the same (tenant, customer) arrive, merge the burst into one agent invocation.
- Retries with backoff on transient failures; dead-letter logging. Idempotency key per Green API notification id (process exactly once).

### 3. Builder agent (`builder/`) — autonomous, with a hard gate
- Implemented as a tool-calling loop (Anthropic SDK) with tools: `list_uploaded_assets`, `caption_image(asset_id)` (vision model → structured JSON: name, category, colors, materials, style, descriptions in he+en), `create_or_update_product(data)`, `add_business_info(topic, content)`, `generate_system_prompt(draft)`, `index_embeddings(scope)`, `run_self_test(questions)`, `finalize_build(report)`.
- The Builder decides its own plan based on what the owner uploaded (photos only, photos + CSV price list, free text…). It must handle messy/partial input gracefully and record assumptions in the build report.
- **Validation gate (mandatory)**: `finalize_build` is rejected unless `run_self_test` passed — the self-test asks the freshly built knowledge base ≥5 generated questions (e.g. "do you have a white sofa?", one price question, one out-of-scope question) and verifies retrieval returns the right products and the agent declines out-of-scope properly. Agent status becomes `live` only after the gate passes; otherwise `failed` with the report explaining why.
- **Idempotent**: re-running a build for a tenant upserts products by stable keys and replaces that tenant's embeddings atomically (build into a staging set, swap on success). Never duplicate on retry.
- Every run writes a `build_runs` row with a human-readable report (what was found, what was created, what was assumed, self-test results).

### 4. Conversation agent (`runtime/`) — plain tool-calling loop
- A while-loop over the Anthropic Messages API with native tool use. Max 6 tool iterations per turn, then graceful fallback.
- Tools: `search_products(query, filters)` (hybrid retrieval), `get_business_info(topic)`, `send_product_cards(product_ids)` (worker sends image+caption per product: photo, name, price), `handoff_to_human(reason)` (mark conversation, notify owner — stub the notification for now).
- Context per turn: tenant's generated system prompt + rules, last 12 messages from `messages`, current time/day (for "are you open?").
- Guardrails (in the system prompt template + code): only discuss this business's catalog and info; never invent prices or stock; mirror the customer's language (Hebrew in → Hebrew out); on anger or explicit request → handoff; never reveal it serves other businesses.
- Every turn traced in Langfuse with tenant_id and conversation_id tags; trace id stored on the message row.

### 5. Retrieval (`retrieval/`)
- Hybrid: pgvector cosine similarity over `embeddings.vector` + structured filters from the metadata jsonb (category, colors, price range, in_stock), always filtered by tenant_id.
- The agent passes natural-language query + optional structured filters; return top-k product records (with image URLs) ready for the tools above.

### 6. Frontend (`/frontend`) — strictly scoped for this week
Build ONLY:
1. Auth (Supabase) + tenant creation.
2. Onboarding wizard: (a) business info form, (b) product upload — drag-and-drop photos + per-product price/name fields + optional CSV, (c) WhatsApp connection — form for Green API instance id/token + connection check, (d) "Build my agent" → triggers build, shows live build progress and the build report.
3. Test chat page: simple chat UI calling the runtime through a REST endpoint (same agent, no WhatsApp), so the owner can try the bot before going live.
- Full RTL support: `dir` switches with locale; all layouts must be RTL-safe (use logical CSS properties). UI copy in English first; structure ready for Hebrew strings.
- NO dashboard, analytics, billing, or settings pages this week.

### 7. Observability
- Langfuse SDK initialized in `core/`; decorate every LLM call, every builder run (one trace per build), every conversation turn. Tag traces with tenant_id. Log token costs.

## Environment variables (.env.example must list all)
`ANTHROPIC_API_KEY, OPENAI_API_KEY, SUPABASE_URL, SUPABASE_SERVICE_KEY, SUPABASE_ANON_KEY, DATABASE_URL, REDIS_URL, LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST, INTAKE_MODE, APP_BASE_URL, TOKEN_ENCRYPTION_KEY, GREEN_API_INSTANCE_ID, GREEN_API_TOKEN, ALLOWED_TEST_NUMBERS`

## Milestones — build strictly in this order
1. **M1 Skeleton**: monorepo scaffold, docker-compose (redis), Supabase schema + Alembic migrations, core config + model registry, Langfuse wiring, health endpoints. 
2. **M2 WhatsApp adapter**: interface + Green API impl + polling mode + echo bot (incoming message → echo reply) proving the full message loop locally.
3. **M3 Builder agent**: tools, autonomous loop, validation gate, idempotent indexing. CLI command `python -m app.builder.cli --tenant X --assets ./demo_assets` so builds run without the frontend.
4. **M4 Conversation agent + retrieval**: hybrid search, tool loop, product cards over WhatsApp. **END OF M4 = DEMO PATH COMPLETE — this must land with buffer before Sunday.**
5. **M5 Frontend**: wizard + test chat, wired to the API.
6. **M6 Deploy**: Railway (api + worker + redis) with webhook mode, Vercel frontend. Keep the local polling-mode demo working as Sunday fallback.

## Working rules for you
- Propose a short plan per milestone; wait for approval; implement; then a brief summary of what changed.
- Pytest for: adapter normalization, debouncer, retrieval filters, builder idempotency, and the validation gate. Don't chase coverage elsewhere yet.
- No dependencies beyond the stack above without asking. No premature abstractions beyond what this spec defines.
- Seed a demo dataset: `demo_assets/` with ~10 furniture products (use placeholder images), a CSV price list, and business info — so the whole demo path runs end-to-end with one command.
- If anything in this spec is ambiguous or looks wrong, stop and ask before building around it.

## Definition of done (the Sunday demo script)
1. Run `docker compose up redis`, start API + worker locally in polling mode.
2. Onboard a demo furniture business (via wizard if M5 done, else builder CLI): photos + prices + business info → build runs → build report shows self-test passed → agent live.
3. From a real phone, WhatsApp the connected number: "היי, יש לכם ספה לבנה?" → bot replies in Hebrew with 2–3 matching sofa photos, names, and prices.
4. Ask "How much is the white one?" in English → bot answers in English with the correct price.
5. Ask something out of scope → bot politely declines and offers human handoff.
