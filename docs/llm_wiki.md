# LLM Wiki: topic memory with cited work evidence

NyaNya's LLM Wiki organizes completed work into short topic summaries. It is an agent memory feature, separate from a GitHub documentation Wiki. Conversation recall still references the original task/result ledger; the Wiki adds topics, revisions, source citations and explicit review/forget controls.

## What the source implements

The existing result-model call can return an optional list named **wiki**, with up to three **topic** and **summary** pairs. This uses the same call that answers the request; it adds no background LLM refinement call. A missing field falls back to the screened work-record excerpts. An empty list intentionally records no topic. Malformed or sensitive optional notes are omitted without failing the otherwise valid answer. Questions, failed/cancelled/blocked work, pending file plans and storage opt-out requests do not create Wiki notes.

**work_memory.complete_conn** first verifies and writes a successful task/attempt record. **wiki_store.capture_conn** then writes its notes in that same fenced completion transaction. SQLite schema v9 adds only the topic/revision table; the source request, complete result, file plan and journal stay in their existing tables. A note cites its source task and execution. Reviewed file application is labelled as historical applied-plan evidence; ordinary replies remain model claims, including replies that sound certain.

Identical active topic/content pairs are deduplicated. Different content under a normalized topic creates another revision. The old version is preserved and conflicting active versions are marked. A candidate does not silently overwrite a selected version. Selecting a revision in the dashboard atomically marks its other active versions as superseded. This is memory curation, not file approval or confirmation that a statement remains true today.

## Recall boundaries

**wiki_store.worker_context** resolves the current task's owner, registered workspace, project and conversation session from the ledger. It retrieves matching topic summaries only after the last explicit reset. Bound conversation work-record retrieval uses the same channel boundary. Unbound requests retain their explicit owner/workspace/project work-record contract.

Topic matching uses words in the current request against saved topic/summary text. Matching occurs before the materialized row limit so older topics remain searchable. Up to five notes fit within 8 KiB; the complete provider prompt keeps its existing 100,000-byte limit. The current request and complete selected file snapshots take priority. Conversation history retains its independent 24 KiB budget. Duplicate Wiki source tasks are excluded from work-record excerpts.

Automatic notes can be reused as **unreviewed historical claims** without a manual approval for every task. The result prompt carries source citations, review states and conflict flags. The Flash assessment does not receive Wiki notes. Current-only/no-history/no-memory requests suppress this recall. Old history cannot expand file discovery, approve a plan, run commands, cancel work, change model settings or override the present request.

Every read/review rechecks current task/attempt, owner/workspace/project/session, retained source record and applied-plan/journal evidence. Source and note text are screened at storage and again at retrieval, including currently known credential values. A revoked, forgotten, stale or wrong-scope source becomes unavailable.

Wiki summaries have no automatic 90-day expiry; the older work-record excerpt search retains that expiry. This does not guarantee complete semantic recall or verify present-day facts. Unaddressed channel messages are not collected. Provider hidden conversation history is not reused. No graph, new database backend, external service, autonomous tool execution or self-modification is introduced.

## Dashboard controls

The existing Memory view includes **Topic memory and evidence** (UI label: `주제별 기억과 근거`). Choose its explicit user/workspace/project/channel scope and optionally search a topic. The list shows automatic notes, selected and previous revisions, conflicts and task/attempt citations. Read and control endpoints require dashboard authentication and the existing Host/Origin checks.

### Memory screen areas

| Area | Contents and controls | Effect on ordinary conversation |
|---|---|---|
| Topic memory and evidence (`주제별 기억과 근거`) | Automatic topic summaries with task/attempt citations. Search reads the selected scope; revision selection resolves conflicting versions, rejection excludes one summary, and source forgetting excludes its derived memory. | Eligible automatic summaries can be recalled before review, as historical claims. Review every note only if useful. |
| Manual candidate review (`수동 기억 후보 검토`) | Counts for the candidates displayed below. **Extract from request history** inspects up to 80 recent requests and derives eligible candidates using rules, without another model call. | Extraction is separate from automatic Wiki recall and does not start a development task. |
| Candidate list (`기억 목록`) | Up to 120 loaded legacy candidates. **Approve** and **Reject** change a candidate's review status while retaining its text and source history. | Legacy search/format functions are not part of normal operation-model context. Approving a candidate alone does not change an ordinary Discord reply. |
| Work memory (`작업 기억`) | Short request/result excerpts of successful attempts in the selected owner/workspace/project scope. **Exclude from memory** applies the source-forgetting boundary below. | Supplies scoped historical work evidence; neither successful execution nor memory review verifies present file state. |

The manual-review summary and candidate list are two parts of the same legacy feature. They do not form another required approval step for automatic Wiki memory. None of these controls grants file-change permission. Forgetting derived memory preserves the original request/result ledger and backups; it is not secure deletion.

| Control | Source behavior |
|---|---|
| Select memory revision (`기억 버전 선택`) | Selects the current revision and supersedes other active revisions of that topic; stale review versions are rejected. |
| Reject summary (`요약 거부`) | Excludes this derived summary from automatic Wiki recall; the original conversation/work evidence is retained. |
| Forget source memory (`이 근거 기억 제외`) | Clears every Wiki note derived from that source attempt, forgets its work excerpt, and excludes that source turn from conversation recall. Original tasks, results, approvals and effects remain in the ledger. |
| Conversation reset | Establishes a new recall boundary without cancelling or deleting work. Old or late results cannot populate the new Wiki scope. |

Forgetting a work record also clears all Wiki notes from that source attempt, including rejected and superseded revisions, while preserving the original ledger. The separate legacy candidate list respects source storage refusal and source forgetting too. Both forget controls clear only the same owned request's derived candidate text. Read, search, review and refinement reject disallowed sources; older linked candidates lacking screened current successful work evidence are hidden without deleting their rows. Unlinked/manual legacy records are preserved. An explicit request not to remember/store also excludes that turn from future recent/related conversation context and private conversation export. Its original workflow request/result is retained; current-only without storage refusal does not erase the future conversation turn.

The scoped APIs are **GET /v1/wiki/scopes**, **GET /v1/wiki** and **POST /v1/wiki/{entry_id}/review**. A review includes the selected scope, status and displayed review version. There is no anonymous or model-controlled review path. A single local operator token can inspect explicitly selected operator scopes; this is not multi-user dashboard authentication.

## Validation and installation

Regression tests cover real completion transactions with deterministic providers, cross-channel/project/owner isolation, reset and late results, topic conflicts, revision fencing, sensitive/oversized/malformed notes, source revocation, forgetting across all recall paths, historical apply journals, old-topic search and bounded provider inputs. Source tests are separate from an operating deployment and real Discord/model delivery. Apply the additive migration to a consistent DB copy and verify preserved workflow rows before upgrading an installed instance.

Previous code can read the additive schema, but that is not a safe operational rollback guarantee. Older extractors may regenerate forgotten or opted-out memory from retained ledger evidence. During selected-file rollback, keep newer work rows and current provenance, no-store, forget and conversation/export guards. Never restore an old whole DB over later operations or restart on earlier guards merely because schema reads succeed.
