# Maintain the illustrated documentation

The [illustrated manual](manual/README.md) covers all 14 Local Control pages, important dialogs, onboarding, progress, empty states and recovery. The images show the real HTML/CSS/JavaScript UI with synthetic API responses. Every dashboard image carries a **DEMONSTRATION DATA** label. CLI images are rendered transcripts of commands executed against disposable installation targets.

## Refresh everything with one command

Use a development Git checkout with Python 3.11+ and Node.js, then prepare the optional browser tooling once:

```sh
npm ci --ignore-scripts
npx playwright install chromium
```

For subsequent refreshes:

```sh
npm run screenshots
```

This captures the complete set, writes its manifest, rebuilds the manual and runs the offline publication checks. It does not start Local Control, read its private state, install models, call providers or write your actual client configuration. The isolated server binds to loopback on a temporary port and serves only the six checked-in web assets. Browser requests to external origins are blocked. The CLI installer uses temporary homes and state directories.

Open `.local/screenshot-review/review.html` for visual inspection. Review readable text, unclipped controls, accurate captions and privacy before committing images. Automated checks cannot recognize a password in image pixels. The fictional accounts and paths are intentional; never substitute a real account export or browser session.

The package downloads used for browser-tool installation are separate from capture: the capture itself needs no network. The screenshots include a **fictional next release**, example models, driver versions and simulated performance. These images establish no hardware, account-access or release claims.

## Change a workflow or caption

- `scripts/documentation_scenarios.cjs`: page, interactions, viewport, capture region, title and caption for each image.
- `tests/fixtures/documentation.cjs`: fictional API data and failure scenarios. Use the real API’s response shape; unsupported endpoints fail the capture.
- `scripts/documentation_cli.py`: real check and dry-run transcripts with normalized demonstration paths.
- `scripts/documentation_manual.py`: generated chapter and index layout.
- `docs/assets/screenshots/manifest.json`: UI version, source digest, browser/OS, dimensions, checksums, coverage and pending external captures.

Edit source scenarios and captions, then refresh; do not hand-edit generated manual chapters or the manifest. If a source file’s content changes, the freshness check requires regeneration. Add a scenario for every new dashboard page and important new workflow. Copyable commands belong in the guides as text; an image does not replace them.

For a single draft image without replacing the complete manifest:

```sh
node scripts/screenshots.cjs --only update-blocked --output .local/screenshot-draft
```

For a comparison run that preserves committed screenshots and manual pages:

```sh
node scripts/screenshots.cjs --output .local/screenshot-comparison
```

Its `review.html` pairs the new captures with committed images. Save the checkout and `.local` output together when viewing a downloaded CI artifact so the relative baseline links resolve. Byte differences are informational; fonts and Chromium builds can differ across operating systems. Visual review remains required.

## Checks and CI

```sh
python scripts/check_screenshots.py
python scripts/check_docs.py
```

The screenshot checker verifies version and source freshness, every declared journey, dashboard navigation coverage, image checksums/dimensions, PNG integrity, missing/unlisted images, manual captions, README gallery coverage and external-guide links. It rejects embedded text/EXIF metadata. Budgets are **900 KiB per screenshot** and **16 MiB for the gallery**. It also checks the complete release payload against the updater’s **64 MiB / 1,000-entry** limits, including its manifest.

The **Documentation screenshots** workflow reruns all journeys on Chromium and publishes a side-by-side review artifact. The regular check matrix validates committed assets on Windows, macOS and Linux. Review CI captures when changing the UI; fixture success is distinct from [physical acceptance](compatibility-matrix.md).

Capture tooling is development-only and requires a Git checkout with the test fixtures and npm dependencies. Portable runtime packages still ship the manual and screenshots; they do not need Playwright to use them.

## External applications

Actual Cursor, Codex desktop, xAI Grok Bot, Ollama installer, Windows updater and macOS updater interfaces cannot be recreated by a Local Control fixture. Their slots are explicitly **pending** in the [external capture checklist](manual/toolkit.md#external-application-captures), with usable instructions linked beside them.

To complete a slot:

1. Use a disposable account/profile or repository in the actual application. Record application version, OS, date and exact interaction path.
2. Capture the real interface. Avoid credentials, personal login identifiers, project inventories, machine addresses and conversation contents. Prefer a new capture with demonstration data over obscuring a private session.
3. Review the pixels yourself and strip embedded metadata. Save a PNG within the image budgets; attach an explanatory caption and copyable commands where applicable.
4. Extend the manifest schema, checker and manual generator to register reviewed external images separately from generated dashboard captures. Preserve them across automatic refreshes. Submit the image and provenance together.

Do not mark those slots complete based on dashboard instructions, a transcript, a generated mockup or fixture tests. Until an actual capture is reviewed, the status stays pending.
