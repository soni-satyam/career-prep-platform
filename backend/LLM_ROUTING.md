# LLM routing

Every LLM call in the app goes through `app/core/llm_router.py`. It walks an ordered
chain of `provider:model` entries (`LLM_CHAIN` in `.env`) and returns the first usable answer.

Default chain:

| # | Entry | Why here |
|---|---|---|
| 1 | `groq:openai/gpt-oss-20b` | Fast, 30 req/min. Free plan is only **8K tokens/min**, so big requests skip it. |
| 2 | `openrouter:google/gemma-4-31b-it:free` | Free; account-wide rate limit shared with #3. |
| 3 | `openrouter:google/gemma-4-26b-a4b-it:free` | Second OpenRouter model. |
| 4 | `gemini:gemini-3.5-flash-lite` | Verified free-tier Flash-Lite (~500 requests/day). Kept late to save Gemini. |
| 5 | `huggingface:openai/gpt-oss-20b` | Independent quota pool, but only ~$0.10/month of credits: last resort. |
| - | nothing left | Clear message to the user (HTTP 429 "try in ~Ns" or 503 "temporarily unavailable"). |

```mermaid
flowchart TD
    A[AI request] --> B[Next entry in LLM_CHAIN]
    B --> C{Usable?<br/>has key, not cooling down,<br/>under its RPM and token budget,<br/>request fits its token cap}
    C -- No, skip without calling --> B
    C -- Yes --> D[Call provider<br/>no hidden SDK retries]
    D --> E{Result}
    E -- Success --> F{Output valid?<br/>JSON / quiz shape}
    F -- Yes --> G[Return response]
    F -- No --> H[Skip this entry for this request]
    E -- 429 rate limit --> I[Cooldown: Retry-After, else 60s<br/>daily quota: 1h+]
    E -- 401/403 bad key --> J[Disable provider 10min, then 1h, then 6h<br/>log error]
    E -- 402 no credits --> K[Disable provider 1h, then 4h, then 24h]
    E -- 400/422 invalid request --> L[Do NOT retry same entry<br/>3 in a row: park 10min]
    E -- 413 too large --> M[Skip for this request, no penalty]
    E -- 404 model missing --> N[Park entry 15min]
    E -- timeout / 5xx --> O[Short cooldown 5s, 15s, 45s... max 2min]
    H --> P
    I --> P
    J --> P
    K --> P
    L --> P
    M --> P
    N --> P
    O --> P
    P{Attempts < LLM_MAX_ATTEMPTS<br/>and chain not exhausted?}
    P -- Yes --> B
    P -- No, a slot frees within 25s --> Q[Wait, then try again]
    Q --> B
    P -- No --> R[Clear error: busy, retry in Ns<br/>or temporarily unavailable]
```

## Checking it

Admin only: `GET /api/v1/admin/llm-status` shows the active chain, entries skipped for
missing keys, requests/tokens used in the last minute, cooldowns, disabled providers
(bad key / no credits) and the last error per entry.

## Notes

- Counters are in memory (single uvicorn process). With several workers, lower the `*_RPM` values.
- Free tiers can use prompts to improve their products (Google says so for the unpaid Gemini API),
  and free OpenRouter models are run by third parties. Avoid sending sensitive resumes if that matters to you.
- Model names change often. If a log line says "model not found", edit `LLM_CHAIN`.
