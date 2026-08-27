# Visual Engine 3.1.3

3.1.3 keeps the production-safe multi-token Hugging Face pipeline from 3.1.2 and raises the visual-semantic bar.

## Main goal

The image should not merely match the mood of a quote. It should show a **visual mechanism** that makes the quote's claim believable.

Examples:

- choice -> show the choice or its consequence, not just an open landscape;
- letting go -> show a concrete release/separation, not just a doorway;
- reciprocity -> show the reciprocal act;
- growth -> show a meaningful transition or transformation, not automatically a seedling;
- gratitude -> show what is being recognized, preserved, returned, or carried forward rather than automatically using flowers or a heart;
- past/present/future -> use visible temporal or spatial structure instead of a generic sunset.

## Pipeline

1. Semantic analyst extracts the quote's claim, tension, human change, idea structure, visual mechanism and specificity anchor.
2. Three visual concepts are generated with different visual strategies: direct action, object/architecture/nature-led metaphor, and hybrid/temporal contrast.
3. A strict concept judge scores semantic fit and quote inference and penalizes cliché/generic concepts.
4. The image prompt explicitly carries the semantic anchor, causal visual logic and specificity test.
5. After generation, the existing OCR + vision-caption semantic gate additionally checks whether the actual image shows the mechanism and rejects generic mood-only results.
6. Existing visual-history diversity checks remain active.

## Compatibility

- No new mandatory Python dependencies.
- Existing `.env` remains compatible.
- Existing `HF_TOKEN`, `HF_TOKEN_2`, `HF_TOKEN_3`, and `HF_TOKEN_ORDER` are unchanged.
- Existing database is compatible; no migration is required.
