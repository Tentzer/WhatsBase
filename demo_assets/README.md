# Demo assets

Seed dataset for the end-to-end demo path (build → WhatsApp Q&A). The Builder
CLI (`python -m app.builder.cli --tenant <id> --assets ./demo_assets`, M3)
consumes this folder.

## Contents
- `products.csv` — ~10 furniture products (he + en names, category, price, attributes, image filename).
- `business_info.txt` — hours, location, policies, FAQ in Hebrew + English.
- `generate_placeholders.py` — draws labeled solid-color JPEGs with PIL (no network).
- `images/` — generated placeholder images (created by the script).

## Generate placeholder images
From this folder:

```
python generate_placeholders.py
```

> ⚠️ **Reminder for Eyal:** these are **labeled solid-color placeholders**, not
> real furniture. **Replace `images/*.jpg` with real furniture photos before the
> Builder runs in M3** — the vision captioning step needs real images to produce
> useful captions and attributes. Keep the same filenames (the `image` column in
> `products.csv`) so nothing else has to change.
