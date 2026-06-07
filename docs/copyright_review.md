# Copyright and Origin Review

Date: 2026-06-07

## Scope

This note compares the local NyaNya Agent codebase against the public Nous Research Hermes Agent repository for obvious source-copying risk before publishing `hcscat/nyanya-agent`.

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

Public reference:

- `https://github.com/NousResearch/hermes-agent`
- shallow clone commit checked locally during review: `fd4c8b404bd0a8bc9938a4f4c259830cbf8a4433`

## Findings

No direct source copy was found in the checked files.

Checks performed:

- Local core file hashes did not exactly match any checked official repository file.
- Project-specific local strings such as the messenger helper docstring, workspace policy text, Codex delegation environment variable names, `run_subprocess_cancellable`, and `Discord attachment context` were not found in the official repository.
- A narrowed text-similarity check against representative official Python files produced very low ratios, around `0.009` to `0.020`.
- The local project structure is materially different: a small Python CLI/bridge package plus shell scripts versus the official multi-package agent runtime with CLI, TUI, Desktop, web dashboard, provider registry, tools, skills, gateway, memory, scheduler, and many pinned dependencies.

## License Context

The official Nous Research Hermes Agent repository is MIT licensed. MIT permits reuse, modification, publication, and sublicensing when the copyright and license notice are preserved in copies or substantial portions.

That said, NyaNya Agent should not imply affiliation with Nous Research and should not use the official product name as its own name.

## Practical Conclusion

Based on current evidence, NyaNya Agent is best treated as an independent lightweight Python bridge/wrapper, not a fork of Nous Research Hermes Agent.

Risk-reduction actions taken:

- Runtime/package name changed to `NyaNya Agent`.
- Environment variable prefix changed from legacy naming to `NYANYA_`.
- LaunchAgent labels changed to `com.hcs.nyanya.*`.
- Public repo excludes local `.env`, sessions, logs, downloads, and user workspace mappings.
- README states that this project is independent and not the official Nous Research Hermes Agent.

## Remaining Caveat

This is an engineering review, not legal advice. A formal legal review would compare full histories, authorship records, and any non-public generated prompts or session artifacts.
