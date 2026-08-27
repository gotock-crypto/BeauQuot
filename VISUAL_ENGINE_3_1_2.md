# Visual Engine 3.1.2

3.1.2 keeps the 3.1 semantic visual pipeline and adds production-safe multi-token Hugging Face failover.

### HF credentials

- `HF_TOKEN`
- `HF_TOKEN_2`
- `HF_TOKEN_3`
- `HF_TOKEN_ORDER` (optional; default: `HF_TOKEN,HF_TOKEN_2,HF_TOKEN_3`)

### Failure handling

- 401: credential disabled for the current process and next token is used.
- 402: quota exhausted; credential disabled for the current process and next token is used.
- 5xx/provider error: provider-level failover remains available.
- No repeated provider calls are made for a token after a 401/402.

This is intentionally in-memory. Restarting the service resets the circuit breaker, which is useful after credits are replenished or credentials are changed.
