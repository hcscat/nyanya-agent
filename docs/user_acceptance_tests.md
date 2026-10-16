# NyaNya Agent User Acceptance Tests

This checklist verifies core behavior without requiring a complete source review. Never put passwords, tokens, personal paths or account identifiers in test messages.

Updated 2026-10-12: conversation, Wiki, storage refusal, forgetting and duplicate approval supplement the existing service/file/recovery/concurrency scenarios. This is a reusable execution plan, not a record that every row passed. See the separate verification table in [development status](development_status.md) for recent direct acceptance, and use an isolated workspace registered to the real test account. Interrupt/restart services or modify test files only within an authorized operating test. Actual accounts, task IDs, paths, messages and evidence belong in private local records rather than this public checklist.

## Common verdicts

- `Pass`: every expected result appears without an error.
- `Partial pass`: the main result appears but progress or dashboard evidence is missing.
- `Fail`: no response, or a permission, authentication or file-transfer error occurs.

## TC-01 Local services and dashboard

Run in a terminal:

```bash
./scripts/nyanya_ctl.sh status-all
./scripts/nyanya_ctl.sh dashboard-health
```

Open `http://127.0.0.1:8765/#office` in a browser and unlock with the dashboard control token before checking data.

Expected results:

- Discord bridge, dashboard and memory worker report `running` or `active`.
- Dashboard health reports `status=ok`.
- Agent Office and its accessible status list appear.

## TC-02 Discord control commands

Send these in order in an allowed Discord channel:

```text
!nyanya status
!nyanya tasks
```

Expected results:

- `status` summarizes bridge/backend configuration.
- `tasks` shows the current owner's active/queued tasks. Check completed results separately with `result <task-id>` or dashboard Tasks/Executions.
- Other owners' tasks and secret settings are not exposed.

## TC-03 Basic LLM response

Send the following in an allowed Discord channel. Korean messages are retained as executable test fixtures:

```text
!nyanya 현재 NyaNya Agent가 제공하는 기능을 다섯 줄로 요약해줘.
```

Expected results:

- An acknowledgement appears first.
- A plan/progress update appears while a longer request runs.
- One final Korean answer appears.
- The same request appears in dashboard Tasks or Executions.

The implementation has acknowledgement/final-result watchers but does not guarantee their send order or intermediate progress heartbeats. Record a partial pass if the order/progress expectations are missing. Receiving one answer on a healthy connection does not establish exactly once delivery across reconnects or process failures.

## TC-04 Codex read-only work and progress queries

Send in an allowed Discord channel:

```text
!nyanya codex README.md와 README.KO.md만 읽고 문서 구조의 차이를 다섯 가지로 정리해줘.
```

While it runs, send:

```text
!nyanya tasks
```

Expected results:

- The Codex request starts with a read-only profile.
- `tasks` shows queued/running state.
- A final summary appears and repository files remain unchanged.

`codex` selects Luna/Codex after Flash assessment. Prepare a small test workspace so the requested files fit the bounded snapshot. Reading a subset does not count as reviewing the whole workspace. This is not a test of resuming an external Codex conversation.

## TC-05 Inspected document upload and exact privacy confirmation

This is a future operating-test plan, not a live result. Run it only after explicit authorization to use a dedicated real test bot/channel and an isolated workspace registered to the test actor. The current document-upload change has not exercised real Discord delivery, service restart or a model call. Use operator-prepared synthetic documents only; never use actual personal data, credentials or operating files. Invented pattern fixtures remain in the files and must not be pasted into public messages or evidence.

Prepare small strict UTF-8, BOM-marked UTF-16 and CP949 text fixtures, and text-only DOCX/XLSX/PPTX fixtures without images, media or external relationships. The destination must expose a valid SDK guild file-size limit. Each file must fit the smaller of that limit and 8 MiB (8,388,608 bytes).

```text
!nyanya upload docs/nyanya_uat_sample.txt
```

| Scenario | Expected result |
|---|---|
| Supported synthetic document with no detected pattern | The request is accepted and the healthy destination receives one attachment containing the inspected original bytes. The response does not claim complete safety. |
| Supported file larger than 2,000,000 bytes but within the effective limit | The former 2,000,000-byte limit does not block it; normal inspection and destination limits still apply. |
| Synthetic personal-information pattern | No attachment is sent before confirmation. The notice contains kinds/counts, approval ID, SHA-256, destination and expiry; no matched values or extracted document text appears. |
| Exact confirmation | The original actor sends `!nyanya upload-approve <id> <sha256>` in the original channel within 300 seconds. The unchanged file and destination permit one send attempt. |
| Reject or cancel while pending | `!nyanya upload-reject <id>` or `!nyanya upload-cancel <id>` closes the pending confirmation without sending. |
| Changed file/workspace/destination, wrong hash, another actor/channel, expired or reused confirmation | No wrong or additional attachment is sent. A new inspection/request is required where appropriate. Generic `approve` cannot substitute for upload confirmation. |
| Synthetic credential-bearing text or a blocked authentication/session/key path | Hold without an approval override and without showing the credential value. |
| PDF, image/scan, legacy Office, ordinary archive, encrypted/unsupported document, Office image/media/external/binary content, or incomplete extraction | Hold as uninspected/unsupported; never label it safe or permit it through personal-information confirmation. |
| Missing/invalid guild limit, DM without guild metadata, over-limit file, or unavailable configured destination | Hold; never redirect a failed configured upload to the ordinary request channel. |

The confirmation also binds file device/inode/size/mtime/ctime and the exact frozen hash. Test actor/channel/file/destination changes one at a time with fresh synthetic requests. At most 16 pending confirmations are allowed per owner. Reports and private approval metadata contain detection counts and scope, not matched values or document excerpts.

Do not introduce a live failure, disconnect or in-flight cancellation unless separately authorized. Once the SDK send starts, cancellation or an error may leave delivery uncertain; no automatic retry is allowed. This healthy-connection checklist and fake-client regressions do not prove durable outbox delivery, duplicate-free redelivery after failure, or real Discord permissions/rate limits/reconnect behavior.

## TC-06 New files and existing-file approval

Prepare nonsensitive UTF-8 regular test files in an isolated workspace. Request a new document and check the task/date folder. Request an existing-file edit, then inspect changes and hash with `plan <plan-id>` and, if needed, `plan-file <plan-id> <relative-path>`.

Expected results:

- New-file creation does not overwrite an existing path.
- Existing files remain unchanged before approval; changed paths, reasons and before/after content are visible.
- Only the correct `approve <plan-id> <plan-hash>` applies the reviewed change.
- Wrong hashes and plans revoked with `revoke <plan-id>` do not apply.
- If the source changes after review, the old approval cannot overwrite it.

Record successful and rejected paths as separate test requests.

## TC-07 Interruption holds, diagnosis, reminders and resume

Submit a test request without file effects. Interrupt/recover a worker or controller only in a separately authorized operating drill. Inspect `recovery` and `why <task-id>`, then complete an independent new request. Send explicit `resume <task-id>` to retry the earlier request.

Expected results:

- The interrupted request is not replayed automatically; its hold reason and original request are available.
- Completing new work reminds the owner about earlier unfinished work.
- Explicit resume creates a new attempt and does not redeliver an old result as its outcome.
- Interrupted file application uses separate `reconcile <plan-id>` observation and `resolve <plan-id> <observation-hash>` after reviewing that hash.
- Resolve neither replays nor rolls back files. Partial application requires a new plan.

File-application interruption drills require authorized scope and test-file backups. REV-01 already has source/regression checks; verify that the live drill separates current attempts from prior results. Never retry operating requests arbitrarily.

## TC-08 Independent concurrency and model routing

In an isolated environment with concurrency at least two, submit two independent read/analysis requests. Inspect overlapping execution times, assessment scores and selected profiles in Tasks/Executions/events.

Expected results:

- Two sufficiently long requests overlap within the configured limit.
- Each has its own Flash assessment and selected-model record; their results remain separate.

This verifies concurrent requests. The DAG that splits one request into multiple agents is not implemented and cannot pass from this result. Concurrent file application in the same workspace is also outside this read-only test.

## TC-09 Channel conversation and reset

State a synthetic preference, then ask about it using a pronoun in the same channel. In an authorized drill, test recall after bridge restart and exclusion in another channel/project. After `reset`, earlier history must not be reused automatically; a current-only request must exclude history for that request. Answer a necessary question and verify continuation; the question itself must complete successfully. Fail if past conversation expands file-read scope or approval authority.

## TC-10 LLM Wiki and revision selection

Process synthetic information as successful work and inspect topics/sources in an explicit owner/workspace/project/channel dashboard scope. Change the same topic to create a conflict; select a revision and check that other active versions become superseded. Automatic summaries must be presented as historical model claims. Fail if memory selection starts file application or task execution.

## TC-11 Storage refusal and source forgetting

Explicitly refuse memory/storage for a request with a unique synthetic marker. The answer must complete, but work/Wiki/legacy derived memory, subsequent relevant conversation and `save` exports must exclude the marker/source. Forget a separate ordinary source; inactive summaries must also clear, and repeated forgetting must be idempotent. Preserve other sources and original requests/results/approvals/journals. This does not establish full deletion from DBs, backups or provider conversations.

## TC-12 Repeated identical approval

Inspect an existing-file plan's ID/hash in an isolated workspace and repeat the same approval. Regardless of successful/failed/running state, there must be one apply child/journal and no repeated application from the same approval. Record changed preimages, wrong hashes and another owner as separate rejection cases.

## Result record

| Test | Verdict | Checked at | Notes |
|---|---|---|---|
| TC-01 | Pending | | |
| TC-02 | Pending | | |
| TC-03 | Pending | | |
| TC-04 | Pending | | |
| TC-05 | Pending | | |
| TC-06 | Pending | | |
| TC-07 | Pending | | |
| TC-08 | Pending | | |
| TC-09 | Pending | | |
| TC-10 | Pending | | |
| TC-11 | Pending | | |
| TC-12 | Pending | | |
