"""Anthropic tool schemas and dispatch for the Builder agent loop."""

from __future__ import annotations

from app.builder.context import BuildContext

# ── Anthropic tool definitions ──────────────────────────────────────────────

TOOL_SCHEMAS = [
    {
        "name": "list_uploaded_assets",
        "description": "Scan the assets directory. Returns a structured list of image files and CSV product data, including which images have CSV matches.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "caption_image",
        "description": "Caption a product image using vision AI. Returns JSON with name_he, name_en, category, colors, materials, style, description_he, description_en.",
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {"type": "string", "description": "Image filename (e.g. 'sofa-white-3seat.webp')"},
            },
            "required": ["filename"],
        },
    },
    {
        "name": "create_or_update_product",
        "description": "Upsert a product in the database and upload its image. Idempotent: re-running updates in place.",
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {"type": "string", "description": "Image filename for this product"},
                "stable_key": {"type": "string", "description": "SKU if available, else normalized image stem"},
                "name_he": {"type": "string", "description": "Hebrew product name"},
                "name_en": {"type": "string", "description": "English product name"},
                "caption_name_he": {"type": "string", "description": "Hebrew name from caption (fallback if name_he empty)"},
                "caption_name_en": {"type": "string", "description": "English name from caption (fallback if name_en empty)"},
                "description_he": {"type": "string"},
                "description_en": {"type": "string"},
                "category": {"type": "string"},
                "colors": {"type": "array", "items": {"type": "string"}},
                "materials": {"type": "array", "items": {"type": "string"}},
                "style": {"type": "string"},
                "price": {"type": "number"},
                "currency": {"type": "string"},
                "in_stock": {"type": "boolean"},
            },
            "required": ["filename", "stable_key"],
        },
    },
    {
        "name": "add_business_info",
        "description": "Add a business information record (hours, location, policy, faq, or other). Call once per record from business_info.txt.",
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "hours|location|policy|faq|other"},
                "content_he": {"type": "string", "description": "Hebrew content"},
                "content_en": {"type": "string", "description": "English content"},
            },
            "required": ["topic", "content_he", "content_en"],
        },
    },
    {
        "name": "generate_system_prompt",
        "description": "Generate and persist the tenant's conversation agent system prompt from catalog and business info.",
        "input_schema": {
            "type": "object",
            "properties": {
                "draft": {"type": "string", "description": "Brief outline of the business and catalog for the prompt"},
            },
            "required": ["draft"],
        },
    },
    {
        "name": "index_embeddings",
        "description": "Generate embeddings for all products and business_info, then atomically swap staging->active. Must be called after all products and business_info are created.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "run_self_test",
        "description": "Run the 8-question self-test gate (retrieval assertions + behavior checks). Must be called after index_embeddings.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "finalize_build",
        "description": "Finalize the build. Refused unless run_self_test passed this run. Sets agent status to live on success, failed on gate rejection.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
        "cache_control": {"type": "ephemeral"},  # marks end of stable tool-definition prefix
    },
]

# ── Tool dispatch ────────────────────────────────────────────────────────────


async def dispatch(ctx: BuildContext, name: str, inputs: dict) -> str:
    """Route a tool_use block to the correct implementation."""
    if name == "list_uploaded_assets":
        return await _list_uploaded_assets(ctx)
    elif name == "caption_image":
        from app.builder.tools.catalog import caption_image
        return await caption_image(ctx, inputs["filename"])
    elif name == "create_or_update_product":
        from app.builder.tools.catalog import create_or_update_product
        return await create_or_update_product(ctx, inputs)
    elif name == "add_business_info":
        from app.builder.tools.knowledge import add_business_info
        return await add_business_info(
            ctx,
            topic=inputs["topic"],
            content_he=inputs.get("content_he", ""),
            content_en=inputs.get("content_en", ""),
        )
    elif name == "generate_system_prompt":
        from app.builder.tools.knowledge import generate_system_prompt
        return await generate_system_prompt(ctx, inputs.get("draft", ""))
    elif name == "index_embeddings":
        from app.builder.tools.knowledge import index_embeddings
        return await index_embeddings(ctx)
    elif name == "run_self_test":
        from app.builder.validation import run_self_test
        return await run_self_test(ctx)
    elif name == "finalize_build":
        from app.builder.tools.finalize import finalize_build
        return await finalize_build(ctx)
    else:
        return f"Unknown tool: {name}"


async def _list_uploaded_assets(ctx: BuildContext) -> str:
    import json
    from app.builder.assets import load_assets

    assets, warnings = load_assets(ctx.assets_dir)
    ctx.assets = {a.stable_key: a for a in assets}
    return json.dumps({
        "assets": [
            {
                "filename": a.filename,
                "stable_key": a.stable_key,
                "name_en": a.name_en,
                "name_he": a.name_he,
                "price": a.price,
                "currency": a.currency,
                "category": a.category,
                "in_stock": a.in_stock,
                "colors": a.colors,
                "materials": a.materials,
                "style": a.style,
                "csv_matched": a.csv_matched,
            }
            for a in assets
        ],
        "warnings": warnings,
        "total": len(assets),
        "business_info_file": str(ctx.assets_dir / "business_info.txt")
        if (ctx.assets_dir / "business_info.txt").exists()
        else None,
    })
