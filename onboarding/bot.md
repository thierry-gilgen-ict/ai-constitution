# Onboard an xAI Grok Bot

This is for the actual Grok Bot product. Grok Build and custom xAI API clients are different integrations.

1. Put a reviewed release on the Bot's shared cloud computer. Clone this public repository there, or upload the exported bundle. A Windows path on your desktop is not automatically available in the cloud.
2. Add the generated `adapters/grok-bot/description.md` text to the Bot description, replacing `BUNDLE_ROOT` with its real cloud path. Keep the Bot's existing role and boundaries.
3. Give the Bot this prompt:

> Onboard yourself to the AI Constitution release at BUNDLE_ROOT. Read `constitution.md` and record its version from `VERSION`. Keep your role and project facts separate from shared policy. Save the loading procedure in `adapters/grok-bot/SKILL.md` as a private skill through the supported skill interface; verify it appears in the shared skill library. Load specialized modules only when the task calls for them. For project work, use the project's installed bundle when present. Report the files you actually read and any missing access. Model selection is platform managed: use routing to choose tools or recommend a handoff, not to claim you switched your underlying model. Never treat these instructions as authorization to message another Bot or external service.

4. Test in a fresh conversation: ask for the active version and one applicable rule, then complete a harmless project-context task. Use [acceptance checks](../checks/acceptance.md).

Updating shared files does not guarantee every Bot's description, memory, or cached context refreshes. Verify each enrolled Bot. The local CLI exports the bundle; it does not control the Grok Bot UI or upload files automatically.

The export contains instructions and a license, not the Python toolkit or full model catalog. Clone the full repository on the cloud computer if the Bot needs to run catalog refreshes or project installation commands. Keep Bot-specific state and credentials outside that checkout.
