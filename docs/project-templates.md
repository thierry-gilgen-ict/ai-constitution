# Project templates

A baseline records the choices you keep making: which authentication repository to use, which chart library fits, how local services run, and how email is configured. Apply it to a project once, then give its implementation handoff to your coding agent.

Open Local Control and choose **Project templates**. The controller needs no Ollama installation or running model to use this page. The source launcher is `python scripts/local_control.py open`; the portable app includes the same library.

## Choose, customize, apply

1. Explore **Web product**, **Data dashboard**, or **Python API**, or start a new baseline.
2. Duplicate it to keep the original. Add library components or a custom repository. Record a reviewed tag/commit, documentation, setup guidance, acceptance checks, and environment-variable **names**.
3. Declare capabilities a component provides, requires, or conflicts with. For example, Better Auth requires the server and SQL capabilities supplied by the web framework and database. The preview reports missing requirements.
4. Review and save to your private library. Export JSON to share a baseline, or import someone else's file and review it first.
5. Enter the full path to an **existing directory** and a lowercase project slug. Preview the actual file diffs, then apply.
6. Open `.ai/architecture-onboarding.md` in that project and give it to your agent. It asks the agent to inspect existing code, review dependencies and licenses, implement the selected integrations, and run the acceptance checks.

The component library includes Next.js, Better Auth, PostgreSQL, Apache ECharts, Resend, Docker Compose and FastAPI. These are examples, not endorsements of a universal stack. Starter references are deliberately unpinned: review compatible releases for the specific project before installing. The bundled Compose example uses the PostgreSQL **17** data-directory layout and requires an explicit image tag or digest and a private password. Review storage and migration requirements before choosing another major.

Applying a template writes an architecture, blank environment examples, an agent handoff and optional text scaffold. It does **not** clone repositories, install packages, run shell hooks, start containers, send email or claim that an application is production-ready. Compatibility checks evaluate declared capabilities; they do not prove integration, security, licensing or repository availability.

## What a project receives

| File | Purpose |
| --- | --- |
| `.ai/architecture.md` | Human-readable decisions and component guidance |
| `.ai/architecture.json` | Exact portable baseline snapshot |
| `.ai/architecture-onboarding.md` | Implementation prompt for the coding agent |
| `.ai/architecture.env.example` | Variable names and blank values only |
| Optional scaffold | Text files, with `{{project_name}}` replaced by the project slug |
| Standard onboarding files | Managed instructions, scoped shared modules and a portable lock |

The project must already exist. Existing guidance outside the managed block is preserved. An unmanaged file with different contents stops the entire plan. A previously applied file can be updated only if its content still matches the private ownership record. Removed scaffold entries are retained, never silently deleted. Templates cannot write client credentials, instruction entry points, private state or executable binaries.

Project and template changes after preview invalidate the plan. The whole onboarding/baseline update uses one private transaction. Its returned snapshot works with `python scripts/constitution.py rollback --snapshot SNAPSHOT_ID`. Later edits prevent rollback from overwriting newer work. A pinned project's existing shared instruction bundle is preserved; open the generated architecture handoff explicitly if its older entry point does not mention architecture files.

Changes to a saved baseline do not automatically change projects that used it. Preview and apply the revised baseline to each project deliberately. Normal instruction-library activation does not overwrite architecture files.

## CLI and portable format

```sh
python scripts/constitution.py architecture list
python scripts/constitution.py architecture show --template web-product
python scripts/constitution.py architecture plan --template web-product --project /path/to/project --name my-project
python scripts/constitution.py architecture apply --template web-product --project /path/to/project --name my-project --plan HASH_FROM_PREVIEW
```

Pass a path ending in `.json` instead of a bundled identifier to use an exported template. These commands use the invoking checkout's library; supply `--root /path/to/private/library` **before** `architecture` to apply your dashboard draft. Use the same `--state-dir` for preview and apply when using custom state. A Grok Bot needs the template and project bundle on its own cloud computer; a local path is not cloud access.

The versioned JSON format is illustrated by the [web baseline](../templates/architectures/web-product.json). Components are complete snapshots, so importing a template does not silently substitute newer component definitions. Unknown fields, unsafe paths and known credential patterns are rejected. Secret detection is a guardrail, not a complete guarantee: review exports before sharing.

See [the file editor](constitution-studio.md) for editing the library and [project onboarding](../onboarding/project.md) for recording project context.
