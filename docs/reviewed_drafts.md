# Reviewed file drafts

Normal file work preserves original files while the operator reviews a plan, works with copies and gives feedback. This extends the existing SQLite ledger, immutable change plans and exact-hash apply engine. It does not execute arbitrary commands, install tools or add another database.

## Actual flow

1. The initial model invocation receives the current request and screened conversation/memory context, with no original workspace contents. If it needs a file, it returns an exact relative `read_files` list and a short plan. There is no automatic directory discovery in this normal path.
2. `work_drafts.create()` stores the proposed paths, authenticated owner, registered workspace, conversation generation and a scope hash. No file bytes are copied yet. The operator uses `open-draft <draft-id> <scope-hash>` in the same channel/thread to approve that read scope.
3. `open_and_submit()` reads only those paths with existing no-follow, single-link, UTF-8, size and secret checks. It stores the screened contents/hashes in the same SQLite database and queues one continuation atomically. Duplicate approvals reuse that continuation. Read approval grants copying into this draft; it does not grant writes to originals.
4. Each model call materializes a fresh temporary working directory from the approved copies and current pending changes. It returns proposed file deltas as JSON. `merge()` carries unchanged proposed edits forward, revises previous draft outputs and removes draft-only creations when requested. Originals remain unchanged. The temporary directory is removed after invocation.
5. `reviewed_changes.propose()` stores a new immutable plan against the approved original preimages. The previous pending plan is revoked atomically; stale feedback cannot replace a newer revision. New files also wait for final approval and target a unique `nyanya-tasks/drafts/<draft-id>/` directory.
6. After feedback, the operator reviews `plan <plan-id>` or `plan-file <plan-id> <relative-path>` and sends `approve <plan-id> <plan-hash>`. The existing engine rechecks owner, workspace, current plan, expiry, original bytes, execution ownership and the apply journal before writing. Wrong/stale hashes, changed originals and uncertain effects remain held. Repeated approval reuses one apply task.

A single ready draft in the same conversation generation is reused for ordinary follow-up messages. Use an explicit draft ID when several are open. Other owners, channels/threads, workspaces and projects cannot supply its contents. Reset prevents automatic reuse and further feedback from the earlier generation; it does not revoke an already recorded file plan. An exact authenticated plan approval remains a separate decision. Explicit `draft-show` and `draft-close` can inspect/close an older generation in its original channel. Current-input-only requests do not automatically attach a saved draft; explicit inline-only requests still materialize no file contents.

## Commands

| Command | Effect |
|---|---|
| `open-draft <id> <scope-hash>` | Copy the exact approved input list and resume planning; no original writes |
| `draft-show <id>` | Show scope/status/revision and current plan |
| `draft-feedback <id> <request>` | Explicitly revise or discuss that ready draft |
| `draft-close <id>` | Close a settled draft and revoke its pending candidate; originals and evidence remain |
| `plan`, `plan-file`, `approve`, `revoke` | Existing immutable final-plan review, exact approval and revocation |

Discord and Telegram route these explicit file controls to the same operation authority. Telegram accepts the displayed bare command, `/command` and the normal `/command@bot` form. Its incoming chat/user checks run first; the existing owner, workspace, channel and hash checks remain authoritative. This wires file approvals and draft feedback, not complete Telegram natural-language/control parity or durable delivery.

Adding another input file requires a new approved scope. Close the current settled draft and request the expanded plan. A short assent, a remembered instruction or a model-produced command never substitutes for an authenticated control command. Controls use the connector's existing actor/channel checks and API token protections.

An expired final candidate can be closed to release its draft slot. Its original expiry state and evidence remain preserved. Approved, applying or uncertain plans stay held; expiration is not permission to discard active or unresolved effects.

Pending deletions retain their approved original text as explicitly marked undo context, without materializing that file in the temporary draft directory. Feedback can restore or revise that input using `modify`. Restoring the original text removes the proposed deletion; changing it creates a new reviewed candidate. Neither path reads a new original nor bypasses final approval or the whole-file input budget.

## Bounds and retention

The approved input list is limited to 80 files and 50,000 UTF-8 bytes in total. The working copy and final candidate use the existing 2,000,000-byte/40-change bounds, and each owner can have at most 20 pending/ready drafts. Whole files that do not fit the provider input budget are omitted; they cannot be edited by that result. Original files may only be modified/deleted when included completely in the current input.

Read-scope approval expires after one hour. A ready draft is available for 30 days from opening; final change-plan approval retains its existing one-hour expiry. Expired read scopes with no active/uncertain effects settle without copying anything. Worker maintenance clears explicitly closed/applied input-copy bodies after seven days, at most 100 per pass. The worker currently checks maintenance every 30 seconds. Immutable plans, original requests/results, journals and recovery evidence are retained under their existing policy; clearing working copies does not erase those records, SQLite free pages, backups or provider history. Ready or uncertain work is not discarded as temporary clutter.

## Native original-workspace guard

`provider_isolation.protect_original()` wraps normal worker model children on macOS with the installed `/usr/bin/sandbox-exec`. The profile denies direct filesystem reads/writes under the canonical original workspace and writes to its ancestors, including a verified APFS data-volume alias. Canonical paths are necessary for `/var` aliases. The temporary copy directory must be outside the original workspace. Missing native support or an unsafe directory blocks execution; there is no silent unrestricted fallback. Other platforms therefore cannot run this protected normal path until an equivalent guard is separately implemented and tested.

This adds a narrow original-workspace denial to the existing provider CLI planning/read-only options. It is not complete host, network, IPC, credential or provider-session isolation. Provider HOME/authentication and required runtime paths remain available; unknown external side effects are not certified safe. Keep registered roots narrow and review the exact CLI/runtime used. A copied input is still sent to the selected external model, so approve only information suitable for that provider. Word lists and prompts assist interpretation and screening; persisted scopes and exact final approval enforce normal file authority.

## Verification and operating rollout

`tests/test_draft_workflow.py` exercises no read before approval, repeated approvals, feedback/stale plans, create/modify/delete, changed originals, owner/channel/reset fences, private paths, sensitive inputs, closure/expiry/retention, uncertain effects and native direct-access/ancestor-rename denial using synthetic files. Existing conversation, apply admission, recovery, output limits and privacy tests remain separate. Fake models do not prove real CLI startup or Discord delivery. A selected operating install requires a consistent migration backup, old-row preservation, exact installed-file verification and live synthetic connector acceptance. Never restore an old whole database over newer work.
