# Try the workspace without touching your setup

The repository includes a synthetic dashboard and a repeatable browser demonstration. It uses temporary project/configuration folders, `demo@example.com`, a simulated model and a clearly labelled fake release. It does not access real subscriptions or send inference.

```sh
npm ci --ignore-scripts
npx playwright install chromium
npm run test:browser
```

The six journeys exercise the update notification, project discovery/enrollment, backup and restore previews, worker installation steps, architecture capture and a synthetic local-session launch, plus keyboard/contrast checks. Videos and an HTML report are written under ignored `.local/browser-results` and `.local/browser-report`. Open the report with:

```sh
npx playwright show-report .local/browser-report
```

To record just the short architecture-to-session story, run `npm run demo`. It captures a supported project baseline, applies a pinned revision to a second disposable project, and launches a simulated local session. Dependency installation and a physical inference request are deliberately outside the synthetic demonstration. Use the [acceptance procedure](compatibility-matrix.md) to establish those separately.

Browser reports can contain temporary filesystem paths. Keep them private or review/redact them before sharing. CI uploads only synthetic-fixture artifacts with short retention. Node and Playwright are development dependencies; running Local Control does not need them.
