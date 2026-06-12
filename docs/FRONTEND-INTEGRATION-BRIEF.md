# WhatsBase — Frontend Integration Brief

**Audience:** the coding agent working on the frontend. Read this fully before writing or merging any code. The backend repo's `SPEC.md` is the source of truth for product decisions; this doc is the integration contract and current-state summary.

---

## 1. What this product is

WhatsBase is a multi-tenant SaaS: a business owner signs up, uploads product photos + prices + business info, and gets a working AI sales agent on their WhatsApp number. Think "Base44, but the output is a WhatsApp chatbot."

Two AI components live in the backend, strictly separated:

- **Builder agent** (`backend/app/builder/`) — runs once per onboarding. Captions photos with a vision model, structures products, builds the tenant's knowledge base (embeddings), generates the tenant's system prompt, and runs a mandatory self-test. The agent only goes `live` if the self-test passes.
- **Conversation agent** (`backend/app/runtime/`) — answers every incoming customer WhatsApp message using the data the Builder produced.

A "tenant's agent" is **data, not a process**: rows in the `agents` table + embeddings tagged with `tenant_id`. Nothing is deployed per tenant.

---

## 2. Current state (do not assume more is built than this)

| Milestone | Status |
|---|---|
| M1 Skeleton (monorepo, Supabase schema, Alembic, model registry, Langfuse) | ✅ Done |
| M2 WhatsApp adapter (Green API behind interface, polling mode, echo loop) | ✅ Done |
| M3 Builder agent + retrieval (build pipeline, hybrid search, validation gate) | ✅ Done — verified, self-test 8/8, demo tenant agent is `live` |
| M4 Conversation agent on real WhatsApp | 🔜 In progress — **this is the demo line for Sunday** |
| M5 Frontend (wizard + test chat) | Not started on the backend-API side |
| M6 Deploy (Railway + Vercel) | Not started |

**Critical implication for frontend work:** the REST endpoints the frontend needs (`backend/app/api/`) are **not built yet**. Do not invent endpoint shapes and build against them. See §5 — the API contract must be agreed before integration code is written, otherwise the work is wasted on both sides.

---

## 3. Locked tech stack (frontend side)

- Next.js 15 (App Router) + TypeScript + Tailwind + shadcn/ui
- Supabase Auth **on the client** (this is the one thing the frontend talks to directly besides our API)
- Deploys to Vercel

Do not add other UI frameworks, state libraries, or component kits without explicit agreement.

---

## 4. Non-negotiable rules for the frontend

1. **The frontend talks ONLY to the FastAPI REST API** (`backend/app/api/`). Never query Supabase Postgres directly from the client, never use Supabase client-side data APIs for domain tables. The only direct Supabase usage allowed on the client is **Auth**.
2. **Tenant isolation is sacred.** The frontend never passes a tenant_id it chose; tenant identity derives from the authenticated user's session. Every API call is scoped server-side. If a screen seems to need cross-tenant data, the design is wrong — stop and ask.
3. **Hebrew + English are both first-class.** Every layout must work in `dir="rtl"`. Use CSS logical properties (`margin-inline-start`, `padding-inline-end`, etc.) — never `left`/`right` margins/paddings for layout. UI copy in English first, structure ready for Hebrew strings (no hardcoded concatenated sentences).
4. **Scope is frozen for this phase.** Build ONLY: auth + tenant creation, the onboarding wizard, and the test chat page (§6). NO dashboard, analytics, billing, or settings pages. Anything beyond scope gets cut, not merged.
5. **Typed API contracts.** When an endpoint changes, the frontend types change in the same PR. No `any`-typed API responses.
6. **Never log or display secrets.** Green API tokens are entered in the wizard, sent to the API once, stored encrypted server-side, and never echoed back in full.

---

## 5. The API contract — how we avoid working for nothing

The backend owns the API shape; the frontend consumes it. Because `backend/app/api/` is not yet implemented, the merge process is:

1. **Inventory first.** List every API call the existing frontend code makes (or expects): method, path, request body, response shape.
2. **Compare against the planned surface below.** Where the frontend invented something different, the frontend adapts — not the backend — unless there's a concrete UX reason, which gets raised explicitly.
3. **Agree on the contract** (paths + Pydantic/TypeScript shapes) **before** either side writes more integration code.

Planned API surface (names indicative — the agreed contract supersedes this list):

- `POST /api/tenants` — create tenant for the authenticated user
- `GET /api/tenants/me` — current user's tenant + agent status
- `POST /api/business-info` — submit business info (hours, location, policy, FAQ)
- `POST /api/products/upload` — product photos + per-product name/price fields; optional CSV
- `POST /api/whatsapp/connect` — Green API instance id + token; returns connection check result
- `POST /api/builds` — trigger a build
- `GET /api/builds/{id}` — build status + report (poll for live progress; the report includes self-test results per question)
- `POST /api/chat` — test-chat endpoint: send a message to the tenant's conversation agent without WhatsApp, get the reply

Auth: Supabase JWT in the `Authorization` header on every call; the API resolves user → tenant server-side.

---

## 6. Frontend scope (exactly this, nothing more)

1. **Auth + tenant creation** — Supabase Auth flows, then create the tenant via the API.
2. **Onboarding wizard**, four steps:
   a. Business info form (hours, location, policies, FAQ)
   b. Product upload — drag-and-drop photos, per-product name/price fields, optional CSV price list
   c. WhatsApp connection — Green API instance id/token form + "test connection" action
   d. "Build my agent" — triggers the build, shows live progress, then renders the build report (including the 8-question self-test results — this is the trust moment, make it readable)
3. **Test chat page** — simple chat UI hitting `POST /api/chat`, so the owner can try their bot before going live. Same agent, no WhatsApp.

Notable product detail for the wizard: the build report includes an **assumptions list** (data the Builder invented because the owner's input was missing, e.g. auto-generated product names). Surface it prominently — "I named these products for you, please check" is a core trust feature, not a footnote.

---

## 7. Backend architecture facts the frontend agent should know (read-only knowledge)

- DB: Supabase Postgres + pgvector. Embeddings stored as `halfvec(3072)` with an HNSW index; hybrid retrieval = vector similarity + jsonb metadata filters, always tenant-scoped.
- Queue: Redis + arq. Builds and message processing run in a worker, not in the API request — which is why build progress is polled, not returned synchronously.
- WhatsApp: Green API, fully hidden behind a backend adapter. The frontend never sees Green API shapes beyond the instance-id/token form fields.
- Models: all model choices live in `backend/app/core/models.py` (conversation: Claude Sonnet; vision: gpt-4o-mini; embeddings: text-embedding-3-large). The frontend never references model names.
- Observability: every LLM call is traced in Langfuse, tagged by tenant. Message rows store trace ids.
- Build guarantees: builds are idempotent (re-running never duplicates data) and gated (agent goes `live` only after an 8-question self-test passes). The wizard's "build progress" reflects a real pass/fail gate, not a spinner.

---

## 8. Local development

- From `/infra`: `docker compose up redis`
- Backend: FastAPI API + arq worker, `INTAKE_MODE=polling` (no public URL needed locally)
- Frontend: `next dev` against the local API
- Env vars are listed in `/infra/.env.example` — when a frontend-relevant config value is added, it goes there too
- Backend env note: the repo is being moved to GitHub with a proper Python 3.12 venv; until that lands, coordinate before assuming a clean clone works

A demo dataset lives in `demo_assets/` (11 furniture products + CSV + business info). The full path — build via CLI → ask the bot — already works end-to-end; **breaking the demo path = breaking the build.**

---

## 9. How to raise conflicts

If anything the frontend needs conflicts with the rules above (e.g., "the wizard would be simpler if the client wrote to Supabase directly"), do not work around it silently. State the conflict, which rule it touches, and a proposed compliant alternative. Architecture changes require updating `SPEC.md` in the same change — the rules and the code never diverge.
