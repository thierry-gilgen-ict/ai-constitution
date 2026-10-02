# Model definitions and provenance

## Two different catalogs

`registry/catalog.json` is a complete snapshot of the **providers returned by the models.dev API with `type=all`**. It includes all upstream model types, retains provider-scoped identifiers, and preserves unknown fields for forward compatibility.

`registry/models.json` is a much smaller set of curated **client routing candidates**. A provider definition describes a model; a client candidate describes how a particular product lets you select it. These must not be conflated.

The initial snapshot was fetched October 2, 2026 and contains 225 providers and 8,371 provider-scoped definitions. OpenAI, Anthropic, xAI, Google, and many hosted/open-weight providers are included. An underlying model may appear under several serving providers or aliases. This is not a count of unique foundation models.

## Query offline

```sh
python scripts/constitution.py providers
python scripts/constitution.py models --provider anthropic --json --limit 100
python scripts/constitution.py models --provider openai --tools
python scripts/constitution.py models --provider xai --json
python scripts/constitution.py models --provider google --json
python scripts/constitution.py models --search llama --open-weights
```

`--json` returns full upstream model fields. The default view returns names, identifiers, context limits, and tool-support metadata. Use the provider IDs from `providers`; model identifiers are not normalized across vendors.

Depending on upstream coverage, definitions include `cost`, `limit`, `modalities`, `tool_call`, `reasoning`, `reasoning_options`, `structured_output`, `open_weights`, release dates, and canonical model identifiers. Prices retain upstream units and semantics; consult the source provider before financial decisions. Missing metadata is unknown.

## Freshness is visible

The snapshot records its source URL, SHA-256, retrieval time, license, and provider/model counts. A download timestamp does not mean every field was reverified. Model-level upstream dates are preserved. Curated route facts have their own verification dates and source links.

`route` reports `stale: true` when a selected candidate's verification exceeds 45 days. It is advisory and never applies a model setting. Pass repeated `--available` registry keys to constrain recommendations to models you have actually confirmed in your account.

```sh
python scripts/constitution.py route --platform codex --task deep --available codex:balanced
```

## Refresh every provider

```sh
python scripts/constitution.py update --dry-run
python scripts/constitution.py update
```

All providers and models returned by the source are included, including newly added providers. There is no hardcoded provider enumeration. A semantic diff records additions, changes, and removals in private state. Refreshes do not modify curated routing choices or client settings.

If the source removes records, the default preserves the installed catalog and exits with a review-required result. After inspecting the diff, use `update --allow-removals`. Removed upstream records are not automatically equivalent to provider deprecations.

## What “all” can honestly mean

No single public catalog proves coverage of every provider, private deployment, account restriction, preview, region, and newly announced model. This project supports the complete upstream catalog rather than claiming omniscience. Upstream availability can lag a provider release.

For a release that has not reached models.dev, verify the official model documentation and add a reviewed definition to `registry/overrides.json`; refresh preserves these overrides. The maintenance skill can do this and cite its evidence. Contributing the record upstream helps everyone. See [updates](updates.md).

The shape below is an **illustration, not a real model**. Replace each placeholder with an officially verified value. Include only capabilities or limits you can substantiate; omitted values remain unknown.

```json
{
  "schema_version": 1,
  "models": [
    {
      "provider": "provider-id",
      "provider_name": "Provider display name",
      "id": "model-id-from-official-docs",
      "definition": { "name": "Official model name" },
      "source": "https://example.com/official-model-documentation",
      "verified_at": "2026-10-02"
    }
  ]
}
```

Then run `check` and `models --provider provider-id --json`. For an existing provider/model pair, the override replaces that model's definition, so retain every verified field you need. The output includes `constitution_provenance` to distinguish the reviewed addition from imported data.

Provider metadata is untrusted data. It is displayed and searched, never executed as code or converted into authority for an agent. API keys are neither needed nor collected for public catalog refreshes.

Sources: [models.dev API and schema](https://github.com/anomalyco/models.dev), [official OpenAI models](https://developers.openai.com/api/docs/models), [Anthropic models](https://platform.claude.com/docs/en/about-claude/models/overview), [xAI models](https://docs.x.ai/developers/models), [Google models](https://ai.google.dev/gemini-api/docs/models).
