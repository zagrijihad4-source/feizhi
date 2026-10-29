"""Isolated persistent gate/review ledger. It never imports or writes memory.py.

The explicit database path must be outside the production state directory.
An eligible export is only input to later kind/time validation, not permission
to write a production memory. resolve_review is a trusted human-operation API;
the caller must authenticate/authorize that operation outside this module.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import re
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

PRODUCTION_STATE = Path(r"<PROJECT_ROOT>\feizhi_pc\state")
ROUTES = {"eligible", "review", "exclude_public"}
SUPPORT_STATES = {"supported", "attributed", "needs_review", "contradicted"}
SCOPE_DECISIONS = {"keep", "review", "exclude_public"}
HEX64 = re.compile(r"[0-9a-fA-F]{64}\Z")


class LedgerError(ValueError):
    pass


class IdentityConflict(LedgerError):
    pass


class ReviewStateError(LedgerError):
    pass


def canonical(value) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise LedgerError("value is not finite JSON data") from exc


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _nonempty(value, name):
    if not isinstance(value, str) or not value.strip():
        raise LedgerError(name + " must be a nonempty string")
    return value.strip()


def _prepare(envelope):
    required = {"candidate_key", "candidate", "route", "scope", "support", "evidence",
                "policy_version", "source_snapshot_sha256"}
    allowed = required | {"candidate_sha256", "metadata"}
    if not isinstance(envelope, dict) or not required <= set(envelope) or set(envelope) - allowed:
        raise LedgerError("invalid evaluation envelope fields")
    clean = json.loads(canonical(envelope))
    key = _nonempty(clean["candidate_key"], "candidate_key")
    if key != clean["candidate_key"]:
        raise LedgerError("candidate_key must not contain boundary whitespace")
    candidate = clean["candidate"]
    if not isinstance(candidate, dict) or not isinstance(candidate.get("cid"), str) or not candidate["cid"]:
        raise LedgerError("candidate must be the original object with a string cid")
    if not isinstance(clean["route"], str) or clean["route"] not in ROUTES:
        raise LedgerError("invalid route")
    if not isinstance(clean["scope"], dict) or not isinstance(clean["scope"].get("decision"), str) or clean["scope"]["decision"] not in SCOPE_DECISIONS:
        raise LedgerError("scope.decision is invalid")
    if not isinstance(clean["support"], dict) or not isinstance(clean["support"].get("status"), str) or clean["support"]["status"] not in SUPPORT_STATES:
        raise LedgerError("support.status is invalid")
    if not isinstance(clean["evidence"], list) or any(not isinstance(x, dict) for x in clean["evidence"]):
        raise LedgerError("evidence must be a list of objects")
    clean["policy_version"] = _nonempty(clean["policy_version"], "policy_version")
    src = clean["source_snapshot_sha256"]
    if not isinstance(src, str) or not HEX64.fullmatch(src):
        raise LedgerError("source_snapshot_sha256 must be a SHA256 hex digest")
    clean["source_snapshot_sha256"] = src.lower()
    scope, support = clean["scope"]["decision"], clean["support"]["status"]
    expected = "review" if scope == "review" or support in {"needs_review", "contradicted"} else (
        "exclude_public" if scope == "exclude_public" else "eligible")
    if clean["route"] != expected:
        raise LedgerError("route disagrees with scope/support axes")
    if expected != "review" and not clean["evidence"]:
        raise LedgerError("eligible/public decisions require evidence; validation remains upstream")
    if "metadata" in clean and not isinstance(clean["metadata"], dict):
        raise LedgerError("metadata must be an object")
    candidate_json = canonical(candidate)
    candidate_hash = sha256_text(candidate_json)
    if "candidate_sha256" in clean and clean["candidate_sha256"] != candidate_hash:
        raise IdentityConflict("claimed candidate hash does not match the full original object")
    clean["candidate_sha256"] = candidate_hash
    evaluation_json = canonical(clean)
    return clean, candidate_json, candidate_hash, evaluation_json, sha256_text(evaluation_json)


class ReviewLedger:
    def __init__(self, path):
        if str(path) == ":memory:":
            raise LedgerError("use an explicit persistent database path")
        self.path = Path(path).expanduser().resolve()
        production = PRODUCTION_STATE.resolve()
        if self.path == production or production in self.path.parents:
            raise LedgerError("production state paths are forbidden")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._savepoint_serial = 0
        self._con = sqlite3.connect(self.path, isolation_level=None, timeout=5, check_same_thread=False)
        self._con.row_factory = sqlite3.Row
        self._con.execute("PRAGMA foreign_keys=ON")
        self._con.execute("PRAGMA synchronous=FULL")
        try:
            existing = {r[0] for r in self._con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
            if existing and "review_ledger_meta" not in existing:
                raise LedgerError("refusing to initialize a non-ledger database")
            if existing:
                version = self._con.execute(
                    "SELECT value FROM review_ledger_meta WHERE key='schema_version'").fetchone()
                if version is None or version[0] != "1":
                    raise LedgerError("unsupported review ledger schema")
            self._con.executescript("""
                CREATE TABLE IF NOT EXISTS review_ledger_meta(
                    key TEXT PRIMARY KEY, value TEXT NOT NULL);
                INSERT OR IGNORE INTO review_ledger_meta(key,value) VALUES('schema_version','1');
                CREATE TABLE IF NOT EXISTS candidates(
                    candidate_key TEXT PRIMARY KEY, candidate_json TEXT NOT NULL,
                    candidate_sha256 TEXT NOT NULL, route TEXT NOT NULL,
                    review_state TEXT NOT NULL, sticky_review INTEGER NOT NULL,
                    latest_evaluation_sha256 TEXT NOT NULL,
                    approved_evaluation_sha256 TEXT, resolved_by TEXT, resolution_reason TEXT,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    CHECK(sticky_review IN (0,1)),
                    CHECK((review_state='not_required' AND route IN ('eligible','exclude_public') AND sticky_review=0)
                        OR (review_state='approved' AND route='eligible' AND sticky_review=1 AND approved_evaluation_sha256 IS NOT NULL)
                        OR (review_state IN ('pending','rejected') AND route='review' AND sticky_review=1)));
                CREATE TABLE IF NOT EXISTS evaluations(
                    evaluation_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    candidate_key TEXT NOT NULL REFERENCES candidates(candidate_key),
                    evaluation_sha256 TEXT NOT NULL, evaluation_json TEXT NOT NULL,
                    requested_route TEXT NOT NULL, created_at TEXT NOT NULL,
                    UNIQUE(candidate_key,evaluation_sha256));
                CREATE TABLE IF NOT EXISTS events(
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    candidate_key TEXT NOT NULL REFERENCES candidates(candidate_key),
                    event_type TEXT NOT NULL, actor TEXT NOT NULL, reason TEXT NOT NULL,
                    payload_json TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS batch_receipts(
                    batch_key TEXT PRIMARY KEY, batch_payload_json TEXT NOT NULL,
                    batch_payload_sha256 TEXT NOT NULL, receipt_json TEXT NOT NULL,
                    receipt_sha256 TEXT NOT NULL, committed_at TEXT NOT NULL);
            """)
        except BaseException:
            self._con.close()
            raise

    def close(self):
        with self._lock:
            self._con.close()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()

    @contextlib.contextmanager
    def _transaction(self):
        with self._lock:
            nested = self._con.in_transaction
            if nested:
                self._savepoint_serial += 1
                savepoint = "ledger_sp_%d" % self._savepoint_serial
                self._con.execute("SAVEPOINT " + savepoint)
            else:
                self._con.execute("BEGIN IMMEDIATE")
            try:
                yield
            except BaseException:
                if nested:
                    self._con.execute("ROLLBACK TO SAVEPOINT " + savepoint)
                    self._con.execute("RELEASE SAVEPOINT " + savepoint)
                else:
                    self._con.rollback()
                raise
            else:
                if nested:
                    self._con.execute("RELEASE SAVEPOINT " + savepoint)
                else:
                    try:
                        self._con.commit()
                    except BaseException:
                        self._con.rollback()
                        raise

    def _event(self, key, event_type, actor, reason, payload):
        self._con.execute("INSERT INTO events(candidate_key,event_type,actor,reason,payload_json,created_at) VALUES(?,?,?,?,?,?)",
                          (key, event_type, actor, reason, canonical(payload), timestamp()))

    def store_evaluation(self, envelope):
        """Persist a complete evaluated object; model reevaluation cannot approve holds."""
        clean, candidate_json, candidate_hash, evaluation_json, evaluation_hash = _prepare(envelope)
        key, proposed = clean["candidate_key"], clean["route"]
        idempotent = False
        with self._transaction():
            current = self._con.execute("SELECT * FROM candidates WHERE candidate_key=?", (key,)).fetchone()
            if current and (current["candidate_json"] != candidate_json or current["candidate_sha256"] != candidate_hash):
                raise IdentityConflict("candidate key is already bound to a different full object")
            old_eval = self._con.execute("SELECT evaluation_json FROM evaluations WHERE candidate_key=? AND evaluation_sha256=?",
                                         (key, evaluation_hash)).fetchone()
            if old_eval:
                if old_eval["evaluation_json"] != evaluation_json:
                    raise IdentityConflict("evaluation digest collision with unequal JSON")
                idempotent = True
            else:
                effective, state, sticky = proposed, "not_required", 0
                transition = "new_candidate"
                if current:
                    if current["review_state"] == "rejected":
                        effective, state, sticky, transition = "review", "rejected", 1, "rejection_remains_sticky"
                    elif current["sticky_review"]:
                        effective, state, sticky = "review", "pending", 1
                        transition = "new_evaluation_requires_reapproval" if current["review_state"] == "approved" else "pending_review_remains_sticky"
                    elif current["route"] == "exclude_public" and proposed == "eligible":
                        effective, state, sticky, transition = "review", "pending", 1, "public_to_eligible_requires_review"
                    else:
                        transition = "route_changed" if proposed != current["route"] else "evaluation_updated"
                if effective == "review" and state == "not_required":
                    state, sticky = "pending", 1
                t = timestamp()
                if current is None:
                    self._con.execute("""INSERT INTO candidates(candidate_key,candidate_json,candidate_sha256,route,
                        review_state,sticky_review,latest_evaluation_sha256,created_at,updated_at)
                        VALUES(?,?,?,?,?,?,?,?,?)""",
                        (key,candidate_json,candidate_hash,effective,state,sticky,evaluation_hash,t,t))
                else:
                    preserve_rejection = state == "rejected"
                    self._con.execute("""UPDATE candidates SET route=?,review_state=?,sticky_review=?,
                        latest_evaluation_sha256=?,approved_evaluation_sha256=NULL,resolved_by=?,resolution_reason=?,updated_at=?
                        WHERE candidate_key=?""",
                        (effective,state,sticky,evaluation_hash,
                         current["resolved_by"] if preserve_rejection else None,
                         current["resolution_reason"] if preserve_rejection else None,t,key))
                self._con.execute("""INSERT INTO evaluations(candidate_key,evaluation_sha256,evaluation_json,requested_route,created_at)
                    VALUES(?,?,?,?,?)""", (key,evaluation_hash,evaluation_json,proposed,t))
                self._event(key,"evaluation_stored","system:source_gate",transition,
                    {"requested_route":proposed,"effective_route":effective,"review_state":state,
                     "candidate_sha256":candidate_hash,"evaluation_sha256":evaluation_hash,
                     "previous_route":current["route"] if current else None,
                     "previous_review_state":current["review_state"] if current else None})
        out = self.get(key)
        out["idempotent"] = idempotent
        return out

    def store_batch(self, batch_key, envelopes, expected_candidate_keys):
        """Atomically commit an exactly complete batch and its immutable receipt.

        The caller supplies the expected *qualified* candidate keys from the
        frozen input, not from the model response. Local cids can repeat across
        distinct input batches, so completeness is checked by qualified key.
        Envelope order may vary; persistence follows expected key order.
        """
        batch_key = _nonempty(batch_key, "batch_key")
        if not isinstance(expected_candidate_keys, list) or not expected_candidate_keys:
            raise LedgerError("expected_candidate_keys must be a nonempty list")
        keys = expected_candidate_keys
        if any(not isinstance(k, str) or not k or k.strip() != k for k in keys) or len(keys) != len(set(keys)):
            raise LedgerError("expected candidate keys must be nonempty and unique")
        if not isinstance(envelopes, list) or not envelopes:
            raise LedgerError("envelopes must be a nonempty complete list")
        prepared = [_prepare(env) for env in envelopes]
        actual = [p[0]["candidate_key"] for p in prepared]
        if len(actual) != len(set(actual)):
            raise LedgerError("duplicate candidate key in batch")
        if set(actual) != set(keys) or len(actual) != len(keys):
            raise LedgerError("batch candidate keys do not match frozen expected keys")
        by_key = {p[0]["candidate_key"]: p for p in prepared}
        ordered = [by_key[k] for k in keys]
        payload_json = canonical({"expected_candidate_keys": keys, "evaluations": [p[0] for p in ordered]})
        payload_hash = sha256_text(payload_json)
        idempotent = False
        with self._transaction():
            existing = self._con.execute("SELECT batch_payload_json,batch_payload_sha256 FROM batch_receipts WHERE batch_key=?",
                                         (batch_key,)).fetchone()
            if existing is not None:
                # Full JSON comparison still applies when a digest collides.
                if existing["batch_payload_json"] != payload_json or existing["batch_payload_sha256"] != payload_hash:
                    raise IdentityConflict("batch key is already bound to a different complete evaluation set")
                self.get_batch(batch_key)  # Validate the durable receipt before acknowledging a replay.
                idempotent = True
            else:
                members = []
                for clean, _candidate_json, candidate_hash, _evaluation_json, evaluation_hash in ordered:
                    stored = self.store_evaluation(clean)  # Nested SAVEPOINT; outer failure rolls it all back.
                    members.append({"candidate_key": clean["candidate_key"], "candidate_sha256": candidate_hash,
                        "evaluation_sha256": evaluation_hash,
                        "effective_evaluation_sha256_at_commit": stored["latest_evaluation_sha256"],
                        "route_at_commit": stored["route"], "review_state_at_commit": stored["review_state"]})
                committed_at = timestamp()
                receipt = {"batch_key": batch_key, "complete": True, "expected_count": len(keys),
                    "committed_count": len(members), "expected_candidate_keys": list(keys),
                    "batch_payload_sha256": payload_hash, "members": members,
                    "committed_at": committed_at, "write_authorized": False,
                    "note": "Receipt proves atomic handoff; export still applies current sticky review state."}
                receipt_json = canonical(receipt)
                self._con.execute("""INSERT INTO batch_receipts(batch_key,batch_payload_json,batch_payload_sha256,
                    receipt_json,receipt_sha256,committed_at) VALUES(?,?,?,?,?,?)""",
                    (batch_key,payload_json,payload_hash,receipt_json,sha256_text(receipt_json),committed_at))
        out = self.get_batch(batch_key)
        out["idempotent"] = idempotent
        return out

    def get_batch(self, batch_key):
        """Read and verify a complete committed receipt; no receipt means no batch export."""
        batch_key = _nonempty(batch_key, "batch_key")
        with self._lock:
            row = self._con.execute("SELECT * FROM batch_receipts WHERE batch_key=?", (batch_key,)).fetchone()
            if row is None:
                raise LedgerError("unknown or uncommitted batch")
            if sha256_text(row["batch_payload_json"]) != row["batch_payload_sha256"] or sha256_text(row["receipt_json"]) != row["receipt_sha256"]:
                raise LedgerError("batch receipt integrity check failed")
            payload, receipt = json.loads(row["batch_payload_json"]), json.loads(row["receipt_json"])
            if canonical(payload) != row["batch_payload_json"] or canonical(receipt) != row["receipt_json"]:
                raise LedgerError("noncanonical batch receipt")
            keys = payload["expected_candidate_keys"]
            if (not keys or len(keys) != len(set(keys)) or receipt["batch_key"] != batch_key
                    or receipt["complete"] is not True or receipt["expected_candidate_keys"] != keys
                    or receipt["expected_count"] != len(keys) or receipt["committed_count"] != len(keys)
                    or [m["candidate_key"] for m in receipt["members"]] != keys
                    or receipt["batch_payload_sha256"] != row["batch_payload_sha256"]):
                raise LedgerError("incomplete or inconsistent batch receipt")
            evaluations = payload["evaluations"]
            if not isinstance(evaluations, list) or len(evaluations) != len(keys):
                raise LedgerError("incomplete batch evaluation payload")
            for envelope, member, key in zip(evaluations, receipt["members"], keys):
                clean, _cj, candidate_hash, _ej, evaluation_hash = _prepare(envelope)
                if (clean["candidate_key"] != key or member["candidate_sha256"] != candidate_hash
                        or member["evaluation_sha256"] != evaluation_hash):
                    raise LedgerError("batch receipt does not match submitted full objects/evaluations")
            out = dict(receipt)
            out["receipt_sha256"] = row["receipt_sha256"]
            return out

    def get(self, key):
        with self._lock:
            row = self._con.execute("SELECT * FROM candidates WHERE candidate_key=?", (key,)).fetchone()
            if row is None:
                raise LedgerError("unknown candidate key")
            evaluation = self._con.execute("SELECT evaluation_json FROM evaluations WHERE candidate_key=? AND evaluation_sha256=?",
                                           (key,row["latest_evaluation_sha256"])).fetchone()
            if evaluation is None:
                raise LedgerError("ledger consistency error: missing evaluation")
            out = dict(row)
            out["candidate"] = json.loads(out.pop("candidate_json"))
            out["latest_evaluation"] = json.loads(evaluation["evaluation_json"])
            out["eligible_for_kind_time"] = self._is_exportable(row)
            out["write_authorized"] = False
            return out

    @staticmethod
    def _is_exportable(row):
        return row["route"] == "eligible" and (
            row["review_state"] == "not_required" or
            (row["review_state"] == "approved" and row["approved_evaluation_sha256"] == row["latest_evaluation_sha256"]))

    def export_eligible(self, batch_key=None):
        """Return originals excluding pending/rejected/public, using current state.

        Batch consumers MUST pass batch_key and await its complete receipt.
        The no-argument form remains for the explicit single-object interface.
        """
        with self._lock:
            if batch_key is None:
                rows = self._con.execute("SELECT * FROM candidates ORDER BY candidate_key").fetchall()
            else:
                receipt = self.get_batch(batch_key)
                rows = []
                for member in receipt["members"]:
                    row = self._con.execute("SELECT * FROM candidates WHERE candidate_key=?", (member["candidate_key"],)).fetchone()
                    evaluation = self._con.execute("SELECT evaluation_json FROM evaluations WHERE candidate_key=? AND evaluation_sha256=?",
                        (member["candidate_key"],member["evaluation_sha256"])).fetchone()
                    if (row is None or evaluation is None or row["candidate_sha256"] != member["candidate_sha256"]
                            or sha256_text(row["candidate_json"]) != member["candidate_sha256"]
                            or sha256_text(evaluation["evaluation_json"]) != member["evaluation_sha256"]):
                        raise LedgerError("batch member integrity check failed")
                    rows.append(row)
            return [json.loads(r["candidate_json"]) for r in rows if self._is_exportable(r)]

    def pending_reviews(self):
        with self._lock:
            keys = [r[0] for r in self._con.execute(
                "SELECT candidate_key FROM candidates WHERE review_state='pending' ORDER BY candidate_key")]
            return [self.get(key) for key in keys]

    def events(self, key=None):
        with self._lock:
            rows = self._con.execute("SELECT * FROM events" + (" WHERE candidate_key=?" if key is not None else "") + " ORDER BY event_id",
                                     (key,) if key is not None else ()).fetchall()
            return [{**dict(r), "payload": json.loads(r["payload_json"])} for r in rows]

    def resolve_review(self, key, decision, *, reviewer, reason,
                       expected_candidate_sha256, expected_evaluation_sha256):
        """Trusted explicit operation; callers must enforce human authorization.

        Expected hashes reject approval from an outdated review screen. No test or
        production caller should use this to auto-approve a model verdict.
        """
        reviewer = _nonempty(reviewer, "reviewer")
        reason = _nonempty(reason, "reason")
        if not isinstance(decision, str) or decision not in {"approve", "reject"}:
            raise LedgerError("decision must be approve or reject")
        with self._transaction():
            row = self._con.execute("SELECT * FROM candidates WHERE candidate_key=?", (key,)).fetchone()
            if row is None:
                raise LedgerError("unknown candidate key")
            if row["review_state"] != "pending":
                raise ReviewStateError("only a pending review can be resolved")
            if row["candidate_sha256"] != expected_candidate_sha256 or row["latest_evaluation_sha256"] != expected_evaluation_sha256:
                raise ReviewStateError("stale candidate/evaluation; refresh before resolving")
            approve = decision == "approve"
            self._con.execute("""UPDATE candidates SET route=?,review_state=?,approved_evaluation_sha256=?,
                resolved_by=?,resolution_reason=?,updated_at=? WHERE candidate_key=?""",
                ("eligible" if approve else "review", "approved" if approve else "rejected",
                 row["latest_evaluation_sha256"] if approve else None,reviewer,reason,timestamp(),key))
            self._event(key,"review_approved" if approve else "review_rejected",reviewer,reason,
                {"candidate_sha256":row["candidate_sha256"],"evaluation_sha256":row["latest_evaluation_sha256"],
                 "decision":decision,"write_authorized":False})
        return self.get(key)
