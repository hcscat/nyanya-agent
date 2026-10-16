"""Current ledger notices with durable receipts, separate from saved model results."""

from dataclasses import dataclass
import hashlib
import json

from nyanya_agent import database as db, execution_store as ledger, operation_store as store


@dataclass(frozen=True)
class Notice:
    text: str
    owner: str
    revision: str
    task_id: str


def owner_digest(owner):
    return hashlib.sha256(owner.encode()).hexdigest()


def prepare(path, owner, exclude=None):
    """Read current actionable state; an unchanged delivered notice stays quiet."""
    # Candidate lifecycle, ownership and notice fields come from the same read.
    rows = store.recovery_inventory(path, owner, exclude)
    issues = [row for row in rows if row.get('delivery_status') in {'sending', 'uncertain'}]
    if not rows:
        return None
    revision = hashlib.sha256(json.dumps(
        [(r['id'], r['status'], r.get('attempts'), r.get('hold_reason'), r.get('diagnosis'),
          r.get('delivery_status')) for r in rows],
        ensure_ascii=False, sort_keys=True,
    ).encode()).hexdigest()
    recipient = owner_digest(owner)
    with db.connect(path) as conn:
        previous = conn.execute(
            "SELECT metadata_json FROM execution_events WHERE event_type='workflow.notice_delivered' "
            "AND json_extract(metadata_json,'$.recipient')=? ORDER BY seq DESC LIMIT 1", (recipient,),
        ).fetchone()
    if previous and json.loads(previous['metadata_json']).get('revision') == revision:
        return None
    # Explicit lists remain complete; background notices are bounded and say what they mean.
    text = (f"\n\n확인이 필요한 작업이 {len(rows)}개 있습니다. 자동 재실행하지 않았습니다.\n"
            + "\n".join(f"- {r['id']}: {r['title'][:60]} ({r['status']}"
                        f"{', 결과 전달 확인 필요' if r.get('delivery_status') in {'sending', 'uncertain'} else ''})"
                        for r in rows[:5])
            + "\n작업목록으로 현재 상태를, why 작업ID로 이력을 확인하세요. "
              "재진행하지 않을 실패는 dismiss 작업ID, 실행 취소는 cancel 작업ID를 사용하세요."
            + (" 전달 여부가 불확실한 결과의 알림만 종료하려면 ack-delivery 작업ID를 사용하세요. "
               "결과 재전송이나 실행 취소는 하지 않습니다." if issues else ""))
    return Notice(text, owner, revision, rows[0]['id'])


def delivered(path, notice):
    """Record only after successful send; an ambiguous send may still repeat."""
    with db.connect(path) as conn:
        conn.execute('BEGIN IMMEDIATE')
        metadata = {'recipient': owner_digest(notice.owner), 'revision': notice.revision}
        last = conn.execute(
            "SELECT metadata_json FROM execution_events WHERE event_type='workflow.notice_delivered' "
            "AND json_extract(metadata_json,'$.recipient')=? ORDER BY seq DESC LIMIT 1",
            (metadata['recipient'],),
        ).fetchone()
        if last and json.loads(last['metadata_json']).get('revision') == notice.revision:
            return
        ledger.append_event_conn(conn, task_id=notice.task_id, event_type='workflow.notice_delivered',
                                 message='Current task notice delivered', metadata=metadata)
