# Copyright and Origin Review

Date: 2026-06-07

## Scope

This note records a prior source-origin check for NyaNya Agent before publishing `hcscat/nyanya-agent`.

## Evidence Checked

Local source:

- `src/nyanya_agent/core.py`
- `src/nyanya_agent/bridge_common.py`
- `src/nyanya_agent/bridge_constants.py`
- `src/nyanya_agent/bridge_policy.py`
- `src/nyanya_agent/bridge_runtime.py`
- `src/nyanya_agent/bridge_store.py`
- `src/nyanya_agent/discord_bridge.py`
- `src/nyanya_agent/telegram_bridge.py`

## Findings

No direct source copy was found in the checked files.

Checks performed:

- Local core file hashes did not exactly match any checked official repository file.
- Project-specific local strings such as the messenger helper docstring, workspace policy text, Codex delegation environment variable names, `run_subprocess_cancellable`, and `Discord attachment context` were not found in the checked external repository.
- A narrowed text-similarity check against representative official Python files produced very low ratios, around `0.009` to `0.020`.
- The local project structure is materially different from the checked external agent runtime: a small Python CLI/bridge package plus shell scripts versus a multi-package runtime with CLI, TUI, Desktop, web dashboard, provider registry, tools, skills, gateway, memory, scheduler, and many pinned dependencies.

## License Context

The checked external repository is MIT licensed. MIT permits reuse, modification, publication, and sublicensing when the copyright and license notice are preserved in copies or substantial portions.

That said, NyaNya Agent should not imply affiliation with any unrelated upstream project and should use its own product identity.

## Practical Conclusion

Based on current evidence, NyaNya Agent is best treated as an independent lightweight Python bridge/wrapper, not a fork of the checked external project.

Risk-reduction actions taken:

- Runtime/package name changed to `nyanya-agent`.
- Environment variable prefix changed from legacy naming to `NYANYA_`.
- LaunchAgent labels changed to `com.hcs.nyanya.*`.
- Public repo excludes local `.env`, sessions, logs, downloads, and user workspace mappings.
- README states that this project is independent.

## Remaining Caveat

This is an engineering review, not legal advice. A formal legal review would compare full histories, authorship records, and any non-public generated prompts or session artifacts.
