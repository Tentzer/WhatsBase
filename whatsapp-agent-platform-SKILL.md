---
name: whatsapp-agent-platform
description: Architecture rules, conventions, and workflows for the WhatsApp AI Agent Builder Platform (FastAPI + Supabase + Next.js monorepo with a Builder agent and a Conversation agent). ALWAYS use this skill for ANY task in this repository — building new features, fixing bugs, adding tools to either agent, changing the database schema, touching the Green API integration, modifying retrieval/RAG, working on the onboarding wizard or frontend, onboarding a new tenant, debugging a misbehaving WhatsApp bot, or deploying. Use it even for small changes, because this project has strict invariants (tenant isolation, agent separation, adapter boundaries) that are easy to silently break.
---

# WhatsApp AI Agent Builder Platform

A multi-tenant SaaS: business owners upload products/photos/prices on the site, the **Builder agent** constructs their knowledge base + system prompt, and the **Conversation agent** serves their customers over WhatsApp. `SPEC.md` at the repo root is the source of truth for product decisions — read it when a task touches product behavior, not just code.

## The mental model (internalize before any task)

There are two AI components and they are NOT the same thing:

| | Builder agent | Conversation agent |
|---|---|---|
| Lives in | `backend/app/builder/` | `backend/app/runtime/` |
| Triggered by | Owner submits/updates onboarding data | Every incoming customer WhatsApp message |
| Style | Autonomous tool-calling agent | Plain tool-calling loop |
| Writes | products, embeddings, agents row, build_runs | conversations, messages only |
| Model | Vision: `gpt-4o-mini`; reasoning: per model registry | `claude-sonnet-4-6` per model registry |

A "tenant's agent" is **data, not a process**: a system prompt + rules in the `agents` table, embeddings tagged with `tenant_id`, and a `whatsapp_instances` row. Creating/updating an agent means writing rows. Never design anything that spawns per-tenant processes, containers, or deployments.

## Invariants — never violate, never "temporarily" bypass

1. **`builder/` and `runtime/` never import each other.** The database is their only interface. If a task seems to require crossing this line, the design is wrong — stop and reconsider (usually the answer is: Builder writes a new column/row that runtime reads).
2. **Every domain query filters by `tenant_id`.** A missing tenant filter means one business's bot answers with another business's products — the worst possible bug in this product. When writing or reviewing any query touching products, embeddings, business_info, conversations, or messages: verify the tenant filter exists, and add a test if the query is new.
3. **Green API never leaks outside `backend/app/adapters/whatsapp/`.** No Green API URLs, payload shapes, or client imports anywhere else. All other code uses the adapter interface (`send_text`, `send_image`, `get_incoming`) and the normalized `IncomingMessage`. This is what makes a future migration to the official WhatsApp Cloud API a one-module change.
4. **All model selections live in `backend/app/core/models.py`** (the model registry: provider + model name + params per role). Never hardcode a model name anywhere else.
5. **Builds are gated and idempotent.** A tenant's agent reaches `status=live` only after `run_self_test` passes inside the build. Re-running a build upserts products by stable key and atomically swaps that tenant's embeddings (stage → swap). Never let a retry duplicate data or a failed build leave a half-built live agent.
6. **No new agent frameworks.** The conversation loop is a plain while-loop over the Anthropic Messages API with native tool use. Do not introduce LangChain, LangGraph, CrewAI, etc. — even for "just one feature."
7. **Hebrew + English are both first-class.** Product fields and captions exist in `_he` and `_en` variants; the conversation agent mirrors the customer's language; frontend layouts use CSS logical properties and must work in `dir="rtl"`. Any new user-facing surface must handle both.
8. **The agent never invents prices or stock.** Price/stock answers must come from tool results. Guardrails live in the per-tenant system prompt template (`builder/`) and runtime checks (`runtime/guardrails.py`) — update both together.

## How to do common tasks

### Add a tool to the Conversation agent
1. Implement the function in `runtime/tools/`, accepting `tenant_id` explicitly.
2. Register its schema in the tool definitions next to the loop; keep descriptions short and behavioral.
3. If it sends anything to the customer, it must go through the WhatsApp adapter via the outgoing queue job — never call the adapter synchronously inside the loop.
4. Update the system prompt template if the agent needs guidance on when to use it.
5. Add a Langfuse span; add/extend a test for the tool's tenant filtering.

### Add a capability to the Builder agent
Same pattern in `builder/tools/`. Additionally: every new tool's effects must be idempotent (upsert, not insert), and if it creates content the self-test should cover, extend `validation.py` question generation. Record what the tool did in the build report.

### Change the database schema
1. Modify SQLAlchemy models, generate an Alembic migration, review it by hand (autogenerate misses pgvector and RLS details).
2. New domain tables get `tenant_id` + index, timestamps, and a Supabase RLS policy.
3. If the change affects what the Builder writes or the runtime reads, check both sides in the same change — schema drift between them is invariant #1's failure mode.

### Work on retrieval
Hybrid search = pgvector cosine over `embeddings.vector` + jsonb metadata filters, ALWAYS scoped by `tenant_id`. When tuning: change one thing at a time (k, threshold, filter logic), and validate against the self-test question set before and after. Embedding dimension is fixed by the registry model (3072 for text-embedding-3-large) — changing the embedding model requires a re-index migration plan, not just a registry edit.

### Onboard or debug a tenant (also post-launch operations)
- Onboard without the frontend: `python -m app.builder.cli --tenant <id> --assets <dir>`.
- A tenant's bot misbehaving? Order of investigation: (1) Langfuse trace for the conversation turn (every message row stores `agent_trace_id`), (2) the tenant's `agents.system_prompt` and rules, (3) retrieval results for the failing query with that tenant_id, (4) the latest `build_runs.report` — bad builds produce bad bots.
- Bot not responding at all? Check `whatsapp_instances.status` and `intake_mode`; in webhook mode verify Green API's webhook URL and recent deliveries; in polling mode verify the polling worker is running. Then check Redis/arq queue health.

### Frontend work
Next.js App Router + shadcn/ui, talks ONLY to the FastAPI REST API (`backend/app/api/`) — never directly to Postgres. Keep API contracts typed: when an endpoint changes, update the frontend types in the same change. Test every new screen in `dir="rtl"` before calling it done. Scope discipline: no dashboard/analytics/billing surfaces unless explicitly requested.

## Local development & testing

- Local stack: `docker compose up redis` (from `/infra`), then API + arq worker + Next dev server. Use `INTAKE_MODE=polling` locally — no public URL or ngrok needed.
- Demo dataset lives in `demo_assets/`; the full path (build → WhatsApp Q&A) must always work end-to-end with it. Treat breaking the demo path as breaking the build.
- Tests that matter (run before declaring any backend task done): adapter message normalization, debouncer, retrieval tenant filtering, builder idempotency, validation gate. `pytest backend/tests` — keep it green; don't chase coverage elsewhere.
- Every LLM call and agent run is traced in Langfuse with `tenant_id` tags. When adding LLM calls, wire the tracing decorator — untraced calls are invisible during production debugging.

## Deployment

Railway runs the API service, the arq worker service, and Redis; Vercel runs the frontend. Production uses `INTAKE_MODE=webhook`. Secrets come from environment variables listed in `/infra/.env.example` — when adding a config value, add it there and to both Railway services in the same change. Never commit keys; never log tokens (Green API tokens in `whatsapp_instances` are encrypted at rest).

## When the user asks for something that conflicts with this skill

Say so explicitly, explain which invariant it touches and why it exists, and propose the compliant alternative. If the user confirms they want to change the architecture itself, update `SPEC.md` and this skill in the same change so the rules and the code never diverge.