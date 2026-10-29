"""Isolated, journaled handoff prototype. No network and no production writes.

The journal and memory file are not one transaction. Readers MUST use guarded_read
and every writer must use this coordinator; direct memory.render bypasses it.
An explicit workspace and ledger copy keep this experiment away from production.
"""
from __future__ import annotations

import copy
import contextlib
import hashlib
import json
import os
import sqlite3
from pathlib import Path


AUTO_ARCHIVE_REASON = "超出上限，自动归档"


class HandoffError(ValueError):
    pass


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def file_digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else "absent"


class IsolatedCoordinator:
    """Durable intent -> atomic JSON replacement -> durable acknowledgment.

    Journal BEGIN IMMEDIATE serializes all coordinator processes. The review
    ledger's transaction holds a consistent current authorization snapshot for
    one operation; a decision can change after that operation returns. This is
    a local handoff prototype, not production write authorization.
    """

    def __init__(self, workspace, memory_path, journal_path, ledger, record_module,
                 *, capacity, fault_hook=None):
        self.workspace = Path(workspace).resolve()
        self.memory_path = Path(memory_path).resolve()
        self.journal_path = Path(journal_path).resolve()
        if not self.workspace.is_dir():
            raise HandoffError("workspace must already exist")
        ledger_path = Path(ledger._con.execute("PRAGMA database_list").fetchone()[2]).resolve()
        for path in (self.memory_path, self.journal_path, ledger_path):
            if not path.is_relative_to(self.workspace) or path == self.workspace:
                raise HandoffError("all mutable stores must be explicit workspace copies")
        if len({self.memory_path, self.journal_path, ledger_path}) != 3:
            raise HandoffError("memory, journal and ledger paths must be distinct")
        production = Path(r"<PROJECT_ROOT>\feizhi_pc\state").resolve()
        if self.workspace == production or self.workspace.is_relative_to(production):
            raise HandoffError("production state is forbidden")
        if (not isinstance(capacity, dict) or set(capacity) != {"facts", "events"}
                or any(type(n) is not int or n < 0 for n in capacity.values())):
            raise HandoffError("explicit nonnegative fact/event capacity is required")
        self.ledger, self.R = ledger, record_module
        self.capacity, self.fault_hook = dict(capacity), fault_hook
        self.db = sqlite3.connect(self.journal_path, timeout=5, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS intents(
                intent_id TEXT PRIMARY KEY,batch_key TEXT UNIQUE NOT NULL,
                request_json TEXT NOT NULL,request_sha256 TEXT NOT NULL,
                base_sha256 TEXT NOT NULL,target_sha256 TEXT NOT NULL,target_json TEXT NOT NULL,
                state TEXT NOT NULL CHECK(state IN ('prepared','committed')));
        """)
        row = self.db.execute("SELECT value FROM meta WHERE key='memory_path'").fetchone()
        if row and row[0] != str(self.memory_path):
            self.close()
            raise HandoffError("journal belongs to another memory path")
        self.db.execute("INSERT OR IGNORE INTO meta VALUES('memory_path',?)", (str(self.memory_path),))
        head = self.db.execute("SELECT value FROM meta WHERE key='head_sha256'").fetchone()
        if not head:
            if self.memory_path.exists():
                self.close()
                raise HandoffError("initial memory must be absent; no implicit adoption of an existing file")
            self.db.execute("INSERT INTO meta VALUES('head_sha256','absent')")

    def close(self):
        self.db.close()

    def _fault(self, phase):
        if self.fault_hook:
            self.fault_hook(phase)

    @contextlib.contextmanager
    def _operation_lock(self):
        # An OS lock survives neither exception nor process exit. It must span
        # BOTH journal transactions, avoiding a journal/ledger lock-order cycle
        # while the prepared intent is committed before the JSON replacement.
        lock_path = self.journal_path.with_suffix(self.journal_path.suffix + ".lock")
        with lock_path.open("a+b") as stream:
            stream.seek(0, os.SEEK_END)
            if stream.tell() == 0:
                stream.write(b"0")
                stream.flush()
            stream.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                stream.seek(0)
                if os.name == "nt":
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

    def _load_memory(self):
        if not self.memory_path.exists():
            return {"facts": [], "events": [], "last_mid": 0, "last_id": 0,
                    "last_extract_ts": 0.0, "_gate_map": {}}
        try:
            data = json.loads(self.memory_path.read_text(encoding="utf-8"))
        except (ValueError, OSError) as exc:
            raise HandoffError("memory unreadable; fail closed") from exc
        if not isinstance(data, dict) or not isinstance(data.get("_gate_map"), dict):
            raise HandoffError("unmanaged or malformed memory")
        return data

    def _replace(self, text):
        self.memory_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.memory_path.with_suffix(self.memory_path.suffix + ".handoff-tmp")
        with tmp.open("w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        self._fault("before_replace")
        os.replace(tmp, self.memory_path)
        self._fault("after_replace")

    def _check_head(self):
        expected = self.db.execute("SELECT value FROM meta WHERE key='head_sha256'").fetchone()[0]
        if file_digest(self.memory_path) != expected:
            raise HandoffError("memory differs from journal head; reconciliation required")

    def _finish(self, row):
        if hashlib.sha256(row["target_json"].encode("utf-8")).hexdigest() != row["target_sha256"]:
            raise HandoffError("journal target hash mismatch")
        if digest(json.loads(row["request_json"])) != row["request_sha256"]:
            raise HandoffError("journal request hash mismatch")
        if row["state"] == "committed":
            # An old completed batch may be replayed after newer batches. Never
            # roll the memory head back to that historical full-file snapshot.
            return
        actual = file_digest(self.memory_path)
        if actual == row["base_sha256"]:
            self._replace(row["target_json"])
        elif actual != row["target_sha256"]:
            raise HandoffError("unrecognized file at recovery; no overwrite")
        self.db.execute("UPDATE intents SET state='committed' WHERE intent_id=?", (row["intent_id"],))
        self.db.execute("UPDATE meta SET value=? WHERE key='head_sha256'", (row["target_sha256"],))

    def _recover_locked(self):
        rows = self.db.execute("SELECT * FROM intents WHERE state='prepared' ORDER BY rowid").fetchall()
        if len(rows) > 1:
            raise HandoffError("multiple incomplete intents")
        for row in rows:
            self._finish(row)
        self._check_head()

    def _new_intent_locked(self, batch_key, request, target):
        request_json, request_sha = canonical(request), digest(request)
        existing = self.db.execute("SELECT * FROM intents WHERE batch_key=?", (batch_key,)).fetchone()
        if existing:
            if existing["request_json"] != request_json or existing["request_sha256"] != request_sha:
                raise HandoffError("batch key already binds different full request")
            return existing, True
        intent_id = "handoff-" + digest({"batch_key": batch_key, "request": request})
        target["_gate_head_id"] = intent_id
        target_json = canonical(target)
        self.db.execute("INSERT INTO intents VALUES(?,?,?,?,?,?,?,'prepared')", (
            intent_id, batch_key, request_json, request_sha, file_digest(self.memory_path),
            hashlib.sha256(target_json.encode("utf-8")).hexdigest(), target_json))
        return self.db.execute("SELECT * FROM intents WHERE intent_id=?", (intent_id,)).fetchone(), False

    def _run_operation(self, prepare):
        """Two journal commits intentionally expose, and recover, the file window."""
        with self._operation_lock():
            return self._run_operation_locked(prepare)

    def _run_operation_locked(self, prepare):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            with self.ledger._transaction():
                self._recover_locked()
                row, replay = prepare()
                if row is None:
                    self.db.commit()
                    return {"intent_id": None, "idempotent": True}
                # Intent must survive even a hard process exit before replacement.
                self.db.commit()
                self._fault("after_intent")
                # OS operation lock spans both commits. All new operations
                # acquire operation, journal, then ledger; do not
                # call the coordinator from inside another ledger transaction.
                self.db.execute("BEGIN IMMEDIATE")
                self._finish(row)
                self.db.commit()
                return {"intent_id": row["intent_id"], "idempotent": replay}
        except BaseException:
            if self.db.in_transaction:
                self.db.rollback()
            raise

    def _snapshot(self, item, receipt_members, source_sha256):
        required = {"candidate_key", "candidate_sha256", "evaluation_sha256", "kind", "certainty"}
        if (not isinstance(item, dict) or set(item) != required or item["kind"] not in {"fact", "event"}
                or item["certainty"] not in {"high", "mid", "low"}):
            raise HandoffError("classified item schema mismatch")
        key = item["candidate_key"]
        row = self.ledger.get(key)
        if (key not in receipt_members or row["candidate_sha256"] != item["candidate_sha256"]
                or digest(row["candidate"]) != item["candidate_sha256"]
                or row["latest_evaluation_sha256"] != item["evaluation_sha256"]
                or row["latest_evaluation"].get("source_snapshot_sha256") != source_sha256
                or not row["eligible_for_kind_time"]):
            raise HandoffError("candidate/source stale, incomplete or not eligible")
        return row

    def commit(self, batch_key, classified, source_rows, *, ledger_batches):
        if not isinstance(batch_key, str) or not batch_key.strip() or not classified:
            raise HandoffError("explicit nonempty handoff batch required")
        if not isinstance(ledger_batches, list) or not ledger_batches:
            raise HandoffError("complete ledger batch receipts required")
        if (not isinstance(source_rows, list) or not source_rows
                or any(not isinstance(r, dict) or type(r.get("id")) is not int
                       or not isinstance(r.get("text"), str)
                       or not isinstance(r.get("role"), str) or not r["role"]
                       or "sent_at_ms" not in r
                       or (r["sent_at_ms"] is not None and type(r["sent_at_ms"]) is not int)
                       for r in source_rows)):
            raise HandoffError("source row schema mismatch")
        ids = [r["id"] for r in source_rows]
        if len(ids) != len(set(ids)):
            raise HandoffError("duplicate source message id")
        source_sha256 = digest(source_rows)
        keys = [r.get("candidate_key") for r in classified if isinstance(r, dict)]
        if len(keys) != len(classified) or len(keys) != len(set(keys)):
            raise HandoffError("duplicate or malformed classified keys")

        def prepare():
            receipts = [self.ledger.get_batch(b) for b in ledger_batches]
            members = {m["candidate_key"] for receipt in receipts for m in receipt["members"]}
            snapshots = [(item, self._snapshot(item, members, source_sha256)) for item in classified]
            request = {"classified": classified, "source_rows": source_rows, "capacity": self.capacity,
                       "ledger_receipts": receipts, "isolated_only": True}
            existing = self.db.execute("SELECT * FROM intents WHERE batch_key=?", (batch_key,)).fetchone()
            if existing:
                if existing["request_json"] != canonical(request):
                    raise HandoffError("handoff key conflict")
                return existing, True
            target = self._load_memory()
            all_records = target["facts"] + target["events"]
            by_id = {r["id"]: r for r in all_records}
            for item, snap in snapshots:
                key, candidate = item["candidate_key"], snap["candidate"]
                old = target["_gate_map"].get(key)
                if old:
                    if old["candidate_sha256"] != snap["candidate_sha256"]:
                        raise HandoffError("stable candidate key conflict")
                    rid = old["record_id"]
                    if rid not in by_id:
                        raise HandoffError("mapped record missing")
                    all_records = [r for r in all_records if r["id"] != rid]
                else:
                    rid = None
                rec = {**candidate, "kind": item["kind"], "certainty": item["certainty"]}
                if rid:
                    rec["id"] = rid
                recs, stored, _notes, mid = self.R.add_record(
                    all_records, rec, source_rows, target.get("last_mid", 0), gate_state="eligible")
                stored["gate_candidate_key"] = key
                stored["gate_candidate_sha256"] = snap["candidate_sha256"]
                stored["gate_evaluation_sha256"] = snap["latest_evaluation_sha256"]
                # Stable identity does not erase explicit prior manual forgetting.
                if old and by_id[rid].get("archived") and by_id[rid].get("archive_reason") != AUTO_ARCHIVE_REASON:
                    for name in ("archived", "archived_at", "archive_reason"):
                        stored[name] = by_id[rid].get(name)
                all_records = recs
                target["last_mid"] = mid
                target["_gate_map"][key] = {"record_id": stored["id"],
                    "candidate_sha256": snap["candidate_sha256"],
                    "evaluation_sha256": snap["latest_evaluation_sha256"],
                    "classified_item_sha256": digest(item)}
            # Explicit capacity, no trim bypass. Pending/rejected never use quota.
            for bucket, kind in (("facts", "fact"), ("events", "event")):
                records = [r for r in all_records if r["kind"] == kind]
                live = self.R.recallable(records)
                excess = max(0, len(live) - self.capacity[bucket])
                for r in live[:excess]:
                    r["archived"] = True
                    r["archive_reason"] = AUTO_ARCHIVE_REASON
                    r["archived_at"] = "isolated_capacity_policy"
                target[bucket] = records
            return self._new_intent_locked(batch_key, request, target)

        result = self._run_operation(prepare)
        return {**result, **self.guarded_read()}

    def guarded_read(self):
        """Recover then reconcile current ledger states, or return no content.

        Returns copied records only; callers can render them via memory.py using
        an in-memory object. A direct file reader bypasses this safety contract.
        """
        def prepare():
            target = self._load_memory()
            changes = []
            by_id = {r["id"]: r for r in target["facts"] + target["events"]}
            for key, mapped in target["_gate_map"].items():
                if mapped["record_id"] not in by_id:
                    raise HandoffError("mapped record missing")
                record = by_id[mapped["record_id"]]
                snap = self.ledger.get(key)
                valid = (snap["eligible_for_kind_time"]
                         and snap["candidate_sha256"] == mapped["candidate_sha256"]
                         and snap["latest_evaluation_sha256"] == mapped["evaluation_sha256"]
                         and record.get("gate_candidate_key") == key
                         and record.get("gate_candidate_sha256") == mapped["candidate_sha256"]
                         and record.get("gate_evaluation_sha256") == mapped["evaluation_sha256"])
                if not valid and record.get("gate_state") != "pending":
                    record["gate_state"] = "pending"
                    changes.append(key)
            request = {"safety_reconcile": sorted(changes),
                       "base_sha256": file_digest(self.memory_path), "isolated_only": True}
            if not changes:
                return None, True
            return self._new_intent_locked("reconcile/" + digest(request), request, target)

        self._run_operation(prepare)
        # Reacquire both locks so a coordinator writer cannot change the file
        # between its hash check and the returned copy. Ledger mutations may
        # happen after return; consumers must not cache it as continuing approval.
        with self._operation_lock():
            return self._read_locked()

    def _read_locked(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            with self.ledger._transaction():
                self._check_head()
                data = self._load_memory()
                visible = []
                for r in data["facts"] + data["events"]:
                    key = r.get("gate_candidate_key")
                    if not key:
                        continue
                    snap = self.ledger.get(key)
                    mapped = data["_gate_map"].get(key, {})
                    if (not snap["eligible_for_kind_time"]
                            or snap["latest_evaluation_sha256"] != mapped.get("evaluation_sha256")
                            or snap["candidate_sha256"] != mapped.get("candidate_sha256")):
                        continue
                    visible.append(r)
                recallable = self.R.recallable(visible)
                result = {"stored_count": len(data["facts"]) + len(data["events"]),
                          "recallable_count": len(recallable), "records": copy.deepcopy(recallable),
                          "pending_record_keys": [r.get("gate_candidate_key") for r in data["facts"] + data["events"]
                                                  if r.get("gate_state") == "pending"],
                          "memory_sha256": file_digest(self.memory_path),
                          "capacity": dict(self.capacity), "production_write_authorized": False}
                self.db.commit()
                return result
        except BaseException:
            self.db.rollback()
            raise
