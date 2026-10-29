"""Deny-by-default review request boundary for an explicit isolated ledger copy.

The host injects a trusted authorizer at construction, never from a request.
That callback is a trust boundary, NOT human authentication. It must verify an
actual human decision outside this module. Continue/run instructions are not
review approval. This module performs no network, UI, or production operation.

prepare() creates an undecided, hash-bound packet. apply() accepts ONLY its ID;
actor/is_human/decision fields in untrusted payloads cannot authorize anything.
The authorizer must return an exact TrustedDecision bound to the stored packet.

Request and ledger SQLite files are not one transaction. Apply durably consumes
the request, obtains authorization outside locks, then resolves in a ledger
transaction. A request receipt is committed BEFORE the ledger transaction. If
receipt writing fails, the ledger rolls back. A crash after receipt but before
ledger commit leaves a consumed request requiring reconciliation; receipt
existence alone never proves approval. There is no automatic reapproval/retry.
"""
from __future__ import annotations

import copy
import hashlib
import json
import secrets
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

VERSION = "trusted-review-boundary-v1"
PRODUCTION_STATE = Path(r"<PROJECT_ROOT>\feizhi_pc\state")
EXPERIMENT_ROOT = Path(__file__).resolve().parents[1]


class ReviewBoundaryError(ValueError):
    pass


class AuthorizationDenied(ReviewBoundaryError):
    pass


class NeedsReconciliation(ReviewBoundaryError):
    pass


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class TrustedDecision:
    """Only a trusted host authorizer may construct this from verified evidence.

    A model/request claiming it is human is not verification. authorization_ref
    is a nonsecret host audit reference, not a cryptographic proof by itself.
    """
    request_id: str
    candidate_key: str
    candidate_sha256: str
    evaluation_sha256: str
    packet_sha256: str
    decision: str
    principal: str
    reason: str
    authorization_ref: str
    authorized: bool = False


class DenyAll:
    def __call__(self, packet):
        return None


class ReviewBoundary:
    def __init__(self, workspace, ledger, request_db, *, authorizer: Callable | None = None, fault_hook=None):
        self.workspace = Path(workspace).resolve()
        self.path = Path(request_db).resolve()
        self.ledger = ledger
        if not self.workspace.is_dir():
            raise ReviewBoundaryError("explicit workspace must exist")
        if (self.workspace == EXPERIMENT_ROOT or not self.workspace.is_relative_to(EXPERIMENT_ROOT)
                or self.workspace == Path(self.workspace.anchor)):
            raise ReviewBoundaryError("dedicated workspace beneath this isolated experiment required")
        reserved = ("fixtures", "runtime", "ledger_code", "coordinator")
        if any(self.workspace.is_relative_to(EXPERIMENT_ROOT / name) for name in reserved):
            raise ReviewBoundaryError("frozen input/code directory is not a mutation workspace")
        review_root = EXPERIMENT_ROOT / "review"
        if self.workspace.is_relative_to(review_root) and not self.workspace.is_relative_to(review_root / "test_work"):
            raise ReviewBoundaryError("review code directory is immutable; only dedicated test_work children may mutate")
        ledger_path = Path(ledger._con.execute("PRAGMA database_list").fetchone()[2]).resolve()
        production = PRODUCTION_STATE.resolve()
        if self.workspace == production or self.workspace.is_relative_to(production):
            raise ReviewBoundaryError("production state workspace forbidden")
        for path in (self.path, ledger_path):
            if path == self.workspace or not path.is_relative_to(self.workspace):
                raise ReviewBoundaryError("ledger and request store must be explicit workspace copies")
            if path == production or path.is_relative_to(production):
                raise ReviewBoundaryError("production state forbidden")
            if path.is_relative_to(EXPERIMENT_ROOT / "fixtures"):
                raise ReviewBoundaryError("immutable fixtures are forbidden mutation stores")
        if self.path == ledger_path:
            raise ReviewBoundaryError("request store and ledger must differ")
        if authorizer is not None and not callable(authorizer):
            raise ReviewBoundaryError("authorizer must be a trusted host callback")
        self._authorizer = DenyAll() if authorizer is None else authorizer
        self._fault_hook = fault_hook
        self._lock = threading.RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self.path, timeout=5, isolation_level=None, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA synchronous=FULL")
        self._db.execute("PRAGMA foreign_keys=ON")
        try:
            tables = {r[0] for r in self._db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
            if tables and "review_request_meta" not in tables:
                raise ReviewBoundaryError("not a review request database")
            self._db.executescript("""
                CREATE TABLE IF NOT EXISTS review_request_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS review_requests(
                    request_id TEXT PRIMARY KEY,candidate_key TEXT NOT NULL,candidate_sha256 TEXT NOT NULL,
                    evaluation_sha256 TEXT NOT NULL,packet_json TEXT NOT NULL,packet_sha256 TEXT NOT NULL,
                    state TEXT NOT NULL,created_at TEXT NOT NULL,authorization_json TEXT,receipt_json TEXT);
                CREATE TABLE IF NOT EXISTS review_request_events(
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,request_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,detail TEXT NOT NULL,created_at TEXT NOT NULL);
            """)
            with self._transaction():
                for key, value in (("version", VERSION), ("ledger_path", str(ledger_path))):
                    existing = self._db.execute("SELECT value FROM review_request_meta WHERE key=?", (key,)).fetchone()
                    if existing and existing[0] != value:
                        raise ReviewBoundaryError("review request database binding mismatch")
                    self._db.execute("INSERT OR IGNORE INTO review_request_meta VALUES(?,?)", (key, value))
        except BaseException:
            self._db.close()
            raise

    def close(self):
        with self._lock:
            self._db.close()

    @contextmanager
    def _transaction(self):
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                yield
            except BaseException:
                self._db.rollback()
                raise
            else:
                self._db.commit()

    def _event(self, request_id, event_type, detail):
        self._db.execute("INSERT INTO review_request_events(request_id,event_type,detail,created_at) VALUES(?,?,?,?)",
                         (request_id, event_type, detail, now()))

    @staticmethod
    def _valid_request_id(request_id):
        if (not isinstance(request_id, str) or len(request_id) != 36 or not request_id.startswith("rvw_")
                or any(c not in "0123456789abcdef" for c in request_id[4:])):
            raise ReviewBoundaryError("invalid request ID; request payload is not authorization")

    def _row(self, request_id):
        self._valid_request_id(request_id)
        row = self._db.execute("SELECT * FROM review_requests WHERE request_id=?", (request_id,)).fetchone()
        if row is None:
            raise ReviewBoundaryError("unknown request")
        return row

    def get_packet(self, request_id):
        with self._lock:
            row = self._row(request_id)
            packet = json.loads(row["packet_json"])
            if digest(packet) != row["packet_sha256"]:
                raise ReviewBoundaryError("stored packet integrity mismatch")
            if (digest(packet["candidate"]) != packet["candidate_sha256"]
                    or digest(packet["evaluation"]) != packet["evaluation_sha256"]):
                raise ReviewBoundaryError("packet subject integrity mismatch")
            if (packet["request_id"] != row["request_id"] or packet["candidate_key"] != row["candidate_key"]
                    or packet["candidate_sha256"] != row["candidate_sha256"]
                    or packet["evaluation_sha256"] != row["evaluation_sha256"] or packet["decision"] is not None):
                raise ReviewBoundaryError("packet binding mismatch")
            return {**packet, "packet_sha256": row["packet_sha256"]}

    def _pending(self, packet):
        row = self.ledger.get(packet["candidate_key"])
        if row["review_state"] != "pending" or row["route"] != "review":
            raise ReviewBoundaryError("candidate is not currently pending")
        if (row["candidate_sha256"] != packet["candidate_sha256"]
                or row["latest_evaluation_sha256"] != packet["evaluation_sha256"]
                or digest(row["candidate"]) != packet["candidate_sha256"]
                or digest(row["latest_evaluation"]) != packet["evaluation_sha256"]):
            raise ReviewBoundaryError("stale or corrupt candidate/evaluation")
        return row

    def prepare(self, candidate_key):
        """Persist an undecided packet; never call resolve_review or authorizer."""
        if not isinstance(candidate_key, str) or not candidate_key.strip():
            raise ReviewBoundaryError("explicit candidate key required")
        with self.ledger._transaction():
            current = self.ledger.get(candidate_key)
            if current["review_state"] != "pending" or current["route"] != "review":
                raise ReviewBoundaryError("only a pending candidate can be prepared")
            evaluation = current["latest_evaluation"]
            packet = {"version": VERSION, "request_id": "rvw_" + secrets.token_hex(16),
                "created_at": now(), "candidate_key": candidate_key, "candidate": copy.deepcopy(current["candidate"]),
                "candidate_sha256": current["candidate_sha256"],
                "evaluation_sha256": current["latest_evaluation_sha256"],
                "evaluation": copy.deepcopy(evaluation), "evidence": copy.deepcopy(evaluation["evidence"]),
                "context_evidence": copy.deepcopy(evaluation.get("metadata", {}).get("context_evidence", [])),
                "versions": {"policy_version": evaluation["policy_version"],
                             "source_snapshot_sha256": evaluation["source_snapshot_sha256"]},
                "decision": None, "production_write_authorized": False,
                "authorization_note": "No human decision recorded; callback verification is required before apply."}
            self._pending(packet)
        with self._transaction():
            blocked = self._db.execute("""SELECT request_id FROM review_requests WHERE candidate_key=?
                AND candidate_sha256=? AND evaluation_sha256=? AND state IN ('attempting','uncertain','receipt_recorded')""",
                (candidate_key, packet["candidate_sha256"], packet["evaluation_sha256"])).fetchone()
            if blocked:
                raise NeedsReconciliation("a consumed request for this snapshot requires reconciliation")
            self._db.execute("INSERT INTO review_requests VALUES(?,?,?,?,?,?,?,?,NULL,NULL)", (
                packet["request_id"], candidate_key, packet["candidate_sha256"], packet["evaluation_sha256"],
                canonical(packet), digest(packet), "prepared", packet["created_at"]))
            self._event(packet["request_id"], "prepared", "undecided")
        return self.get_packet(packet["request_id"])

    def _mark(self, request_id, state, detail):
        with self._transaction():
            self._db.execute("UPDATE review_requests SET state=? WHERE request_id=?", (state, request_id))
            self._event(request_id, state, detail)

    @staticmethod
    def _authorization(packet, result):
        if type(result) is not TrustedDecision or result.authorized is not True:
            raise AuthorizationDenied("trusted authorizer did not provide an explicit decision")
        expected = (packet["request_id"], packet["candidate_key"], packet["candidate_sha256"],
                    packet["evaluation_sha256"], packet["packet_sha256"])
        actual = (result.request_id, result.candidate_key, result.candidate_sha256,
                  result.evaluation_sha256, result.packet_sha256)
        if expected != actual:
            raise AuthorizationDenied("authorizer decision does not bind this request snapshot")
        if result.decision not in ("approve", "reject"):
            raise AuthorizationDenied("no explicit approve/reject decision")
        for value in (result.principal, result.reason, result.authorization_ref):
            if not isinstance(value, str) or not value.strip():
                raise AuthorizationDenied("authorizer principal, reason and audit reference required")
        return result

    def _record_receipt(self, packet, authorization, ledger_reason):
        receipt = {"version": VERSION, "request_id": packet["request_id"], "packet_sha256": packet["packet_sha256"],
            "candidate_key": packet["candidate_key"], "candidate_sha256": packet["candidate_sha256"],
            "evaluation_sha256": packet["evaluation_sha256"], "authorization": asdict(authorization),
            "ledger_resolution_reason": ledger_reason, "recorded_at": now(),
            "ledger_commit_proven_by_receipt": False, "production_write_authorized": False,
            "note": "Recorded before ledger commit. Inspect current ledger; this receipt alone is not approval."}
        with self._transaction():
            row = self._row(packet["request_id"])
            if row["state"] != "attempting":
                raise ReviewBoundaryError("request was already consumed")
            self._db.execute("UPDATE review_requests SET state='receipt_recorded',authorization_json=?,receipt_json=? WHERE request_id=?",
                (canonical(asdict(authorization)), canonical(receipt), packet["request_id"]))
            self._event(packet["request_id"], "receipt_recorded", "ledger commit not yet assumed")
        return receipt

    def apply(self, request_id):
        """Consume once. The request cannot provide decision, actor or is_human."""
        packet = self.get_packet(request_id)
        with self._transaction():
            if self._row(request_id)["state"] != "prepared":
                raise NeedsReconciliation("request consumed; never automatically retry review resolution")
            self._db.execute("UPDATE review_requests SET state='attempting' WHERE request_id=?", (request_id,))
            self._event(request_id, "attempting", "durable request attempt")
        try:
            self._pending(packet)
        except Exception:
            self._mark(request_id, "stale", "not current pending snapshot")
            raise ReviewBoundaryError("request is stale or not pending") from None
        try:
            # Callback gets a detached copy, outside ledger/registry transactions.
            authorization = self._authorization(packet, self._authorizer(copy.deepcopy(packet)))
        except BaseException:
            self._mark(request_id, "denied", "no valid trusted authorization")
            raise
        try:
            with self.ledger._transaction():
                self._pending(packet)  # Authorizer may have taken time; check again atomically.
                reason = authorization.reason.strip() + "\n[trusted-review-request:" + request_id + "]"
                resolved = self.ledger.resolve_review(packet["candidate_key"], authorization.decision,
                    reviewer=authorization.principal.strip(), reason=reason,
                    expected_candidate_sha256=packet["candidate_sha256"],
                    expected_evaluation_sha256=packet["evaluation_sha256"])
                if self._fault_hook:
                    self._fault_hook("before_receipt")
                receipt = self._record_receipt(packet, authorization, reason)
                if self._fault_hook:
                    self._fault_hook("after_receipt_before_ledger_commit")
            # No required request-store write follows the actual ledger commit.
        except BaseException:
            try:
                self._mark(request_id, "uncertain", "apply failed; inspect both stores before any new request")
            except Exception:
                pass  # The durable attempting/receipt state still blocks request replay.
            raise
        return {"request_id": request_id, "ledger_effect_observed": True,
                "decision": authorization.decision, "review_state": resolved["review_state"],
                "receipt": receipt, "production_write_authorized": False}

    def inspect(self, request_id):
        """Read-only reconciliation evidence. Never promotes or retries a request."""
        packet = self.get_packet(request_id)
        with self._lock:
            stored = dict(self._row(request_id))
        receipt = json.loads(stored["receipt_json"]) if stored["receipt_json"] else None
        current = self.ledger.get(packet["candidate_key"])
        effect = False
        if receipt:
            auth = receipt["authorization"]
            expected_state = "approved" if auth["decision"] == "approve" else "rejected"
            effect = (current["review_state"] == expected_state
                and current["route"] == ("eligible" if auth["decision"] == "approve" else "review")
                and current["candidate_sha256"] == packet["candidate_sha256"]
                and current["latest_evaluation_sha256"] == packet["evaluation_sha256"]
                and current["resolved_by"] == auth["principal"].strip()
                and current["resolution_reason"] == receipt["ledger_resolution_reason"])
            if auth["decision"] == "approve":
                effect = effect and current["eligible_for_kind_time"] and current["approved_evaluation_sha256"] == packet["evaluation_sha256"]
        return {"request_id": request_id, "request_state": stored["state"], "receipt": receipt,
                "current_review_state": current["review_state"], "current_ledger_effect_matches_receipt": effect,
                "needs_reconciliation": stored["state"] in ("attempting", "uncertain", "receipt_recorded") and not effect,
                "production_write_authorized": False}
