# Visual Engine 3.1.1

## Acceptance hierarchy

1. Semantic truth
2. Correct relationship/action
3. No cliché contradiction
4. Visual originality
5. Adult editorial aesthetics
6. Beauty

## LLM routing

The semantic pipeline uses Hugging Face's official OpenAI-compatible router. Default model is `Qwen/Qwen3-8B` with provider failover `nscale` then `featherless-ai`. The router model syntax is provider-specific (`Qwen/Qwen3-8B:nscale`) so the service does not depend on a provider-specific URL.

## Semantic pipeline

`quote -> semantic analyst -> 3 visual concepts -> concept judge -> image generation -> image caption -> final semantic judge -> accept/retry`

The concept judge performs a quote-blind inference test: it asks what a viewer would infer from the scene without seeing the source quote. A beautiful but semantically wrong concept is rejected.

## Safety behavior

The concept and final semantic judges fail closed. If the judge cannot run, the candidate is not accepted. If the semantic analyst itself is unavailable, the bot records `VISUAL_ENGINE_DEGRADED` and can use the deterministic local fallback for availability.
