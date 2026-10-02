# Third-party notices

## models.dev

`registry/catalog.json` contains data from the community-maintained [models.dev](https://github.com/anomalyco/models.dev) project, retrieved from `https://models.dev/api.json?type=all`.

Copyright (c) 2025 models.dev. Licensed under MIT. The complete upstream notice is preserved in [docs/licenses/models-dev.txt](docs/licenses/models-dev.txt).

Model and provider names are descriptive identifiers belonging to their respective owners. Inclusion is not endorsement or an availability guarantee.

## Local Control integrations

Local Control invokes separately installed [Ollama](https://github.com/ollama/ollama) and [llmfit](https://github.com/AlexsJones/llmfit) tools. Their binaries and model weights are not distributed in this repository. The llmfit installer downloads official release archives after checksum verification. Both projects publish their own licenses and notices; model weights have publisher-specific licenses shown through model cards.

Optional worker certificates use the separately installed [cryptography](https://github.com/pyca/cryptography) package under its upstream license. The dashboard uses system fonts, original CSS artwork and no third-party frontend bundle.

Optional desktop builds use [pystray](https://github.com/moses-palmer/pystray) (LGPL-3.0), [Pillow](https://github.com/python-pillow/Pillow) (MIT-CMU), and [PyInstaller](https://github.com/pyinstaller/pyinstaller) (GPL with its distribution exception). These are optional build/desktop dependencies, not requirements for the core constitution. Packaged artifacts include a dependency inventory and available distribution license files in `licenses/`; retain those alongside the app when redistributing. Refer to the respective upstream sources for source code and complete license terms.

## Visual reference

The repository presentation is inspired by [Engawa](https://github.com/thierry-gilgen-ict/engawa). Its image and source code were not copied into this project. The banner is an original AI-generated asset; [provenance](docs/provenance.md) records the method and prompt.
