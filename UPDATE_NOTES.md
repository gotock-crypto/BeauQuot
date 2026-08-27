# BeauQuot 3.1.3 — Semantic Visual Director

## What changed

- Kept the 3.1.2 multi-token HF failover unchanged.
- Upgraded semantic analysis with `idea_structure`, `visual_mechanism`, and `specificity_anchor`.
- Upgraded concept generation with `semantic_anchor`, `causal_logic`, and `specificity`.
- Added a stronger concept-quality gate that penalizes generic/cliché imagery even when it is aesthetically attractive.
- Added explicit instructions to show the mechanism of the quote: action, choice, consequence, reciprocity, release, transformation, contrast, etc.
- Increased candidate diversity pressure: direct action, object/architecture/nature-led metaphor, and hybrid/temporal contrast.
- Strengthened the final image semantic judge with a `mechanism_visible` check and genericity penalty.
- Kept adult editorial / realistic aesthetic and the existing no-text/OCR protections.
- No new mandatory Python dependencies.
- Existing `.env` contract remains valid.
- Existing database is compatible; no migration is required.

## Recommended production `.env`

```env
HF_TOKEN=<existing token>
HF_TOKEN_2=<new account token 1>
HF_TOKEN_3=<new account token 2>
HF_TOKEN_ORDER=HF_TOKEN_2,HF_TOKEN_3,HF_TOKEN
```

Do not put real tokens in the release archive.

## Expected result

The bot should produce fewer generic images such as `woman + flowers`, `woman + sunset`, `couple`, or `pretty landscape` when those elements do not express the quote's actual logic. It should more often use concrete objects, architecture, still life, nature, spatial relationships, visible actions, contrasts and transformations when those are the stronger visual translation.
