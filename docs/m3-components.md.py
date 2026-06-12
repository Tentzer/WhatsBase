# WhatsBase M3 — what we built and why (reference)

## Builder agent
**What it does:** Turns an owner's raw uploads (photos + CSV + free text) into a working, tested AI sales agent — products in the DB, a knowledge base, a generated system prompt, all gated behind a self-test.
**How it works:** A plain tool-calling loop over the Anthropic API. Claude gets 8 tools (list assets, caption, upsert product, business info, generate prompt, index embeddings, self-test, finalize) and decides its own plan. After our fix, it works one product per cycle: caption image → upsert that product → next image, so each turn stays small no matter the catalog size.
**Why we need it:** This IS the product — "upload your stuff, get a WhatsApp bot." Without an autonomous builder, every tenant onboarding would be manual data entry. The agent design (vs a hardcoded pipeline) lets it handle messy input: photos only, photos+CSV, missing fields.

## Assumptions log
**What it does:** Records every piece of data the Builder invented because the owner's input was missing it. Example: SHL-001 had blank names in the CSV, so the Builder named it "Modern White Shelf" from the photo caption — and wrote that fact into the report.
**How it works:** Detection at the merge point: when a CSV field is empty and the caption fills it, that's logged to the report's `assumed` list automatically — the agent doesn't have to remember to report it.
**Why we need it:** Trust. A real owner uploading 50 messy products needs to see "I named these 6 for you, check them" instead of silently shipping invented data to their customers. It's the difference between a tool owners trust and one that surprises them.

## Idempotent build (stable keys + stage→swap)
**What it does:** Running the same build twice produces the same result — no duplicate products, no doubled embeddings. A failed build leaves the previous good state untouched.
**How it works:** Two mechanisms. (1) Products upsert by a stable key (CSV SKU, else the image filename stem) — re-running updates the existing row instead of inserting a new one. (2) Embeddings are written with status=staging, then swapped to active in one transaction only on success; retrieval only ever reads active rows.
**Why we need it:** Builds fail mid-way (we proved it tonight: credits ran out at product 9, you ctrl-C'd a run). Without idempotency, every retry would duplicate data and every crash would leave a half-built live agent answering customers from a corrupted catalog.

## Validation gate (self-test)
**What it does:** Refuses to set the agent live unless it actually works. 8 deterministic questions (white sofa in EN+HE, out-of-stock honesty, exact price, category breadth, out-of-scope decline, price filter, compound filter), each checked two ways: does retrieval return the right products, AND does the LLM respond correctly given those results.
**How it works:** Code-enforced, not prompt-enforced: `finalize_build` checks a flag that only `run_self_test` can set, this run. Fail any question → agent status = failed, report explains which and why. Tonight it correctly rejected a build because retrieval was broken — that's it working.
**Why we need it:** It's the only thing standing between "build completed" and "a broken bot talking to real customers." Tonight's run is the proof: without the gate, an agent that finds zero products for every query would have gone live.

## Storage (Supabase bucket + public URLs)
**What it does:** Every product photo is uploaded to the public `product-images` bucket and its URL saved on the product_images row.
**How it works:** During upsert, the Builder uploads the local file to Storage under tenant/SKU/filename and stores the public URL. Bucket is public-read so the URL loads without auth.
**Why we need it:** M4's WhatsApp bot sends product photos by URL — Green API fetches the image from that link. No public URL = the bot can talk but never show a single product photo = the demo's money shot dies. (We verified: URLs load logged-out.)

## Retrieval (hybrid search)
**What it does:** Given a customer question ("white sofa?", "lamps under 1000"), returns the matching products — by meaning, not keywords, combined with hard filters.
**How it works:** The question is embedded into a vector; pgvector finds the closest product embeddings by cosine similarity (HNSW index on halfvec). Structured filters (category, colors, price range, in_stock) apply as SQL WHERE clauses on the metadata JSONB, in the same query. Always filtered by tenant_id.
**Why we need it:** It's how the bot finds the right products. Vector similarity handles natural language in two languages ("ספה לבנה" finds the white sofa); the SQL filters handle hard constraints (under ₪1000, in stock) that similarity alone can't guarantee. Currently has 2 known SQL bugs being fixed.

## Metadata contract
**What it does:** Every product embedding carries {category, colors, in_stock, price} in its metadata JSONB.
**How it works:** index_embeddings writes these four keys at index time; retrieval's filters read exactly these keys. Written and read sides locked to the same contract.
**Why we need it:** It's the bridge between the Builder (writer) and retrieval (reader) — the two sides never import each other, so a shared data contract is their only agreement. If the Builder writes different keys than retrieval reads, every filtered search silently returns nothing.

## Dry-run
**What it does:** Runs the whole Builder loop — real LLM calls, real decisions — but writes nothing to the DB or Storage.
**How it works:** Every persisting tool checks ctx.dry_run and logs "would write X" instead of writing. (We fixed a bug where it was secretly writing products anyway.)
**Why we need it:** Lets you watch the agent's plan and captions without polluting a tenant's data — a pre-flight before committing, and a debugging tool that separates "the agent reasoned wrong" from "the write failed." Limit to know: it can't test the gate (no embeddings exist to search), so its self-test "pass" is synthetic.

## Tenant scoping (invariant #2)
**What it does:** Every single query carries WHERE tenant_id = X.
**How it works:** tenant_id is a required argument everywhere; retrieval raises if it's missing. Important detail we confirmed: our backend connects as the Postgres owner role, which BYPASSES the RLS policies — so the in-code filter is the only wall between tenants, which is why it's tested defensively.
**Why we need it:** One missing filter = business A's bot recommending business B's products to B's customers. The single worst bug this product could have.

## Build report (build_runs)
**What it does:** Every build writes a permanent record: what was found, created, assumed, the per-question self-test results, errors, timestamps.
**How it works:** Accumulated in memory during the run, written to build_runs.report as JSON at the end, win or lose.
**Why we need it:** It's the audit trail and the debugging entry point. "Why is this tenant's bot bad?" starts with "what did its last build report say?" Tonight it told us exactly which 8 questions failed and pasted the SQL error — that's it doing its job.

## Observability (Langfuse)
**What it does:** Every LLM call and every build run is traced — what was sent, what came back, tokens, cost, per tenant.
**How it works:** Decorators on the loop and tools emit traces to Langfuse cloud, tagged with tenant_id.
**Why we need it:** When a bot misbehaves in production, the trace is how you see what the model actually saw. Also answers cost questions with real numbers (your $1/build) instead of guesses.

---
*Status as of this doc: all of the above verified working except retrieval, which has two known SQL bugs (bind params + uuid join cast) queued for fix. The gate correctly held the agent at failed until they're resolved.*