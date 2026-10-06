import threading
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.core import db
from app.core.errors import NotFound
from app.models import Plant
from app.security import passwords
from app.services import numbering


def _plant(s):
    return s.execute(select(Plant)).scalars().first().id


def test_format_and_sequence(session):
    pid = _plant(session)
    d = datetime(2026, 3, 1, tzinfo=timezone.utc)
    assert numbering.next_number(session, pid, "PO", d) == "PO-2026-000001"
    assert numbering.next_number(session, pid, "PO", d) == "PO-2026-000002"
    assert numbering.next_number(session, pid, "GRN", d) == "GRN-2026-000001"


def test_yearly_reset(session):
    pid = _plant(session)
    numbering.next_number(session, pid, "PR", datetime(2026, 12, 31, tzinfo=timezone.utc))
    assert numbering.next_number(session, pid, "PR", datetime(2027, 1, 1, tzinfo=timezone.utc)) == "PR-2027-000001"


def test_unknown_doc_type(session):
    with pytest.raises(NotFound):
        numbering.next_number(session, _plant(session), "NOPE")


def test_no_duplicates_under_concurrency(engine):
    s0 = db.new_session()
    pid = _plant(s0)
    s0.close()
    out, errs = [], []

    def worker():
        s = db.new_session()
        try:
            for _ in range(5):
                n = numbering.next_number(s, pid, "SAMPLE", datetime(2026, 5, 1, tzinfo=timezone.utc))
                s.commit()
                out.append(n)
        except Exception as e:  # noqa: BLE001
            errs.append(e)
        finally:
            s.close()

    ts = [threading.Thread(target=worker) for _ in range(6)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert not errs, errs
    assert len(out) == 30 and len(set(out)) == 30


def test_rollback_does_not_burn_committed_numbers(session):
    pid = _plant(session)
    d = datetime(2026, 1, 1, tzinfo=timezone.utc)
    a = numbering.next_number(session, pid, "FG", d)
    session.commit()
    numbering.next_number(session, pid, "FG", d)
    session.rollback()
    assert numbering.next_number(session, pid, "FG", d) != a


def test_password_policy():
    assert passwords.policy_errors("Short1!")
    assert not passwords.policy_errors("Str0ng!Passw0rd#1", "bob")
    assert passwords.policy_errors("Bob!Str0ng!Pass#1", "bob")  # contains username


def test_hash_verify_roundtrip():
    h = passwords.hash_password("Str0ng!Passw0rd#1")
    assert h.startswith("$argon2id$") and passwords.verify_password(h, "Str0ng!Passw0rd#1")
    assert not passwords.verify_password(h, "nope") and not passwords.verify_password(None, "x")
