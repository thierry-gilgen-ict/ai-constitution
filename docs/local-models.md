# Local and self-hosted models

For hardware-aware onboarding, downloads, GPU controls and project launchers, use the optional **[Local Control companion](local-control.md)**. The core CLI below remains a read-only metadata discovery tool, without downloading weights or invoking a model.

| Server | Example | Metadata endpoint |
| --- | --- | --- |
| Ollama | `local --kind ollama` | `/api/tags` |
| LM Studio | `local --kind openai-compatible --url http://127.0.0.1:1234/v1` | `/v1/models` |
| vLLM or llama.cpp with a compatible server | `local --kind openai-compatible --url http://127.0.0.1:8000/v1` | `/v1/models` |

Prefix commands with `python scripts/constitution.py`. The compatible adapter works when the selected server implements the standard `data[].id` model-list response; it is not a certification of every server version.

```sh
python scripts/constitution.py local --kind ollama
python scripts/constitution.py local --kind openai-compatible --url http://127.0.0.1:1234/v1
```

Inventories are saved under `~/.config/ai-constitution/state/`. Different endpoints have separate inventory files. Local model names and private server addresses are not written to the public catalog.

For a server on another host, select it explicitly with `--allow-remote` and HTTPS. If authentication is required, use `--api-key-env VARIABLE_NAME`; the value is read from the environment, sent only to the selected endpoint, and never persisted. Redirects are refused. The tool does not scan your network or probe endpoints automatically.

## Before choosing a local model

The list endpoint does not prove context size, tool calling, structured output, reasoning settings, or performance. These depend on the weights, quantization, server, template, and hardware. Use a harmless test workload to confirm the capabilities needed for your task and record the result locally.

Use the client's supported provider configuration or your own API runner to actually run the model. This toolkit does not impersonate a hosted model, bypass a product's provider restrictions, or silently substitute a local endpoint into Codex, Cursor, or Grok Bot. Grok Bot's own model remains platform managed.

Sources: [Ollama list models](https://docs.ollama.com/api/tags), [LM Studio list models](https://lmstudio.ai/docs/developer/openai-compat/models).

<!-- screenshots:fit:begin -->

**In the dashboard · Find models for your hardware.** Choose Find models for my hardware. Estimated fit is shown separately from measured results.

![Find models for your hardware — demonstration data, UI 0.4.0](assets/screenshots/model-fit.png)

[Illustrated walkthrough](manual/models.md) · Fictional data; UI 0.4.0.

<!-- screenshots:fit:end -->
