# Routing

Generated for v0.2.0. Edit `registry/models.json` and `registry/routes.json`, then run `build`.

These are provisional starting points, not measured rankings. Respect an explicit model choice. Confirm account access and required tools before selecting a model. Reasoning levels and model identifiers can differ between clients.

| Platform | Task | Preferred | Fallback |
| --- | --- | --- | --- |
| codex | small | GPT-6 Luna | GPT-6.1 Sol |
| cursor | small | Composer 2.5 | Grok 4.7 |
| grok-bot | small | Platform-managed selection | Platform managed |
| codex | implementation | GPT-6.1 Sol | GPT-6 Astra |
| cursor | implementation | Composer 2.5 | Grok 4.7 |
| grok-bot | implementation | Platform-managed selection | Platform managed |
| codex | deep | GPT-6 Astra | GPT-6.1 Sol |
| cursor | deep | Grok 4.7 | Composer 2.5 |
| grok-bot | deep | Platform-managed selection | Platform managed |
| codex | review | GPT-6 Astra | GPT-6.1 Sol |
| cursor | review | Grok 4.7 | Composer 2.5 |
| grok-bot | review | Platform-managed selection | Platform managed |
| codex | research | GPT-6.1 Sol | GPT-6 Astra |
| cursor | research | Composer 2.5 | Grok 4.7 |
| grok-bot | research | Platform-managed selection | Platform managed |

## Selection boundaries

- Codex: use supported settings or the model picker. This guide never rewrites your active model settings.
- Cursor: use the model picker or supported SDK. Native Auto remains managed by Cursor.
- Grok Bot: there is no model picker. Routing describes task/tool selection and authorized handoffs.
- Local servers: discover installed models explicitly with `local`. Tool calling, context, and reasoning support must be tested on that server; model names are insufficient.
- When a candidate is unavailable, use an available listed fallback. If none fits, state the limitation.
- Keep source verification dates separate from catalog download dates. Review stale recommendations before selecting them.

## Evidence

- **GPT-6 Luna** (codex): provisional; checked 2026-10-02. Official model description; no comparative project evaluation yet. [Source](https://developers.openai.com/api/docs/models/gpt-6-luna).
- **GPT-6.1 Sol** (codex): provisional; checked 2026-10-02. Official model description; no comparative project evaluation yet. [Source](https://developers.openai.com/api/docs/models/gpt-6.1-sol).
- **GPT-6 Astra** (codex): provisional; checked 2026-10-02. Official model description; no comparative project evaluation yet. [Source](https://developers.openai.com/api/docs/models/gpt-6-astra).
- **Composer 2.5** (cursor): provisional; checked 2026-10-02. Official Cursor catalog; no comparative project evaluation yet. [Source](https://cursor.com/docs/models-and-pricing).
- **Grok 4.7** (cursor): provisional; checked 2026-10-02. Official Cursor catalog; no comparative project evaluation yet. [Source](https://cursor.com/docs/models-and-pricing).
- **Platform-managed selection** (grok-bot): documented; checked 2026-10-02. Grok Bot settings documentation. [Source](https://docs.x.ai/grok-bot/settings-and-notifications).
