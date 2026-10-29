"""Isolated guarded memory facade. No model calls, approval or production path.

Every public consumer reads the coordinator afresh. The legacy memory class is
used only through __new__ with guarded in-memory records; never __init__/_load.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import re
import sqlite3
import sys
import threading
from pathlib import Path


VERSION = "isolated-gate-memory-v1.0"
SAVED_KIND_VERSION = "eligible-kind-v1.0"
DEPENDENCIES = {
    "runtime/memory.py": "abf2b9c3eb294d831b91bf0f2dd0bab469b151e0560787de193b12263a690069",
    "runtime/memrec.py": "00cac261284268b4de7a3646316e2904ab95664c932a7ffd4e3e07a861cb5baf",
    "runtime/extraction_schema.py": "0c87817dfdf8a58a8d4aef35657b7ea8f7dbbea5dd47db8f2d66056d81171bcc",
    "ledger_code/review_ledger.py": "2339a35015cb52d59e726bfffdbdf9746b12a20c3aaecfec29d9e82c1c1fd377",
    "coordinator/recovery_adapter.py": "baaa2bd3c6e3d77793fca6dd83b7b65202e0ad1d826a6bc4069f24c0c7c4a61a",
    "classification/kind_core.py": "10c9f82557cd20777a8a3dd65d847cf563ded7d2b0399ee15a763d2883256118",
}
_IMPORT_LOCK = threading.RLock()
_BUNDLES = {}


class GateUnavailable(RuntimeError):
    """A guarded read failed; callers must not substitute legacy memory."""


class InvalidSavedKind(ValueError):
    """The frozen classification receipt cannot authorize this isolated handoff."""


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _strict(raw):
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise ValueError("duplicate_json_key")
            out[key] = value
        return out
    def constant(_value):
        raise ValueError("non_finite_json")
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _bundle(root):
    root = Path(root).resolve()
    with _IMPORT_LOCK:
        # Always check bytes, even if this exact bundle was imported before.
        for relative, expected in DEPENDENCIES.items():
            if _sha(root / relative) != expected:
                raise GateUnavailable("guarded dependency verification failed")
        if root in _BUNDLES:
            return _BUNDLES[root]
        suffix = hashlib.sha256(str(root).encode()).hexdigest()[:12]
        records = _load_module("_gate_records_" + suffix, root / "runtime/memrec.py")
        schema = _load_module("_gate_schema_" + suffix, root / "runtime/extraction_schema.py")
        previous = {name: sys.modules.get(name) for name in ("memrec", "extraction_schema")}
        try:
            # memory.py's globals retain these exact module objects after restore.
            sys.modules["memrec"], sys.modules["extraction_schema"] = records, schema
            renderer = _load_module("_gate_renderer_" + suffix, root / "runtime/memory.py")
        finally:
            for name, prior in previous.items():
                if prior is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = prior
        ledger = _load_module("_gate_ledger_" + suffix, root / "ledger_code/review_ledger.py")
        coordinator = _load_module("_gate_coordinator_" + suffix, root / "coordinator/recovery_adapter.py")
        kind = _load_module("_gate_kind_" + suffix, root / "classification/kind_core.py")

        class CompleteBatchCoordinator(coordinator.IsolatedCoordinator):
            """New facade policy; the base coordinator intentionally permits subsets."""
            _complete_binding = None

            def _snapshot(self, item, receipt_members, source_sha256):
                bound = self._complete_binding
                if bound is None:
                    raise InvalidSavedKind("complete saved-kind binding is required")
                receipt = self.ledger.get_batch(bound["receipt_key"])
                if receipt["receipt_sha256"] != bound["receipt_sha256"]:
                    raise InvalidSavedKind("frozen source receipt changed")
                eligible = set()
                for member in receipt["members"]:
                    row = self.ledger.get(member["candidate_key"])
                    if row["eligible_for_kind_time"]:
                        eligible.add(member["candidate_key"])
                        # Conservative v1 facade contract: old full receipts are
                        # not reused for a newer single-object evaluation.
                        if member["evaluation_sha256"] != row["latest_evaluation_sha256"]:
                            raise InvalidSavedKind("receipt/current evaluation mismatch")
                if eligible != bound["expected_keys"]:
                    raise InvalidSavedKind("saved-kind/current eligible bijection failed")
                return super()._snapshot(item, receipt_members, source_sha256)

        result = {"R": records, "M": renderer, "L": ledger, "C": CompleteBatchCoordinator, "K": kind}
        _BUNDLES[root] = result
        return result


class GateMemory:
    """A facade over workspace copies, not a drop-in production memory object.

    Public consumers: render, render_existing, query, stats. Each invokes one
    fresh guarded_read and never returns previously cached content on failure.
    """

    def __init__(self, workspace, *, ledger_path, journal_path, memory_path,
                 capacity=None, dependency_root=None):
        self._lock = threading.RLock()
        self._closed = False
        self._workspace = Path(workspace).resolve()
        self._ledger_path = Path(ledger_path).resolve()
        self._journal_path = Path(journal_path).resolve()
        self._memory_path = Path(memory_path).resolve()
        production = Path(r"<PROJECT_ROOT>\feizhi_pc\state").resolve()
        if (not self._workspace.is_dir() or self._workspace == production
                or self._workspace.is_relative_to(production)):
            raise GateUnavailable("explicit isolated workspace is required")
        paths = (self._ledger_path, self._journal_path, self._memory_path)
        if (len(set(paths)) != 3 or any(not p.is_relative_to(self._workspace)
                                      or p == self._workspace for p in paths)):
            raise GateUnavailable("all active stores must be distinct workspace copies")
        if not self._ledger_path.is_file():
            raise GateUnavailable("existing review ledger copy is required")
        for path in paths:
            if path.exists() and path.stat().st_nlink != 1:
                raise GateUnavailable("active stores must be independent copies")
        check = None
        try:
            check = sqlite3.connect(self._ledger_path.as_uri() + "?mode=ro", uri=True)
            version = check.execute("SELECT value FROM review_ledger_meta WHERE key='schema_version'").fetchone()
            tables = {r[0] for r in check.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if version != ("1",) or not {"candidates", "evaluations", "events", "batch_receipts"} <= tables:
                raise ValueError("not an initialized ledger copy")
        except Exception:
            raise GateUnavailable("existing initialized review ledger copy is required") from None
        finally:
            if check is not None:
                check.close()
        self._dependency_root = Path(dependency_root or Path(__file__).resolve().parent.parent).resolve()
        self._modules = _bundle(self._dependency_root)
        self._ledger = None
        self._coordinator = None
        try:
            self._ledger = self._modules["L"].ReviewLedger(self._ledger_path)
            self._coordinator = self._modules["C"](
                self._workspace, self._memory_path, self._journal_path, self._ledger, self._modules["R"],
                capacity=capacity if capacity is not None else {"facts": 60, "events": 40})
            self._store_identities = {p: (p.stat().st_dev, p.stat().st_ino)
                                      for p in (self._ledger_path, self._journal_path)}
        except Exception:
            if self._ledger is not None:
                self._ledger.close()
            raise GateUnavailable("guarded initialization failed") from None

    def close(self):
        with self._lock:
            if not self._closed:
                self._closed = True
                try:
                    self._coordinator.close()
                finally:
                    self._ledger.close()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()

    def _read(self):
        if self._closed:
            raise GateUnavailable("guarded memory is closed")
        try:
            # A live SQLite handle could still read a deleted path on some OSes.
            # Missing stores must fail closed instead of silently using that handle.
            self._require_stores()
            snapshot = self._coordinator.guarded_read()
            records = snapshot["records"]
            if (not isinstance(records, list) or len(records) != snapshot["recallable_count"]
                    or any(not isinstance(r, dict) or r.get("gate_state") != "eligible"
                           or not isinstance(r.get("gate_candidate_key"), str) for r in records)):
                raise GateUnavailable("guarded snapshot malformed")
            return copy.deepcopy(snapshot)
        except Exception:
            raise GateUnavailable("guarded memory unavailable") from None

    def _require_stores(self):
        for path, identity in self._store_identities.items():
            if (not path.is_file() or (path.stat().st_dev, path.stat().st_ino) != identity
                    or path.stat().st_nlink != 1):
                raise GateUnavailable("active guarded store unavailable or replaced")

    def _renderer(self, snapshot):
        klass = self._modules["M"].FeizhiMemory
        renderer = klass.__new__(klass)
        renderer._lock = threading.RLock()
        renderer._load_error = ""
        renderer.path = None  # No constructor, load, path or save participates.
        renderer.data = {"facts": [copy.deepcopy(r) for r in snapshot["records"] if r["kind"] == "fact"],
                         "events": [copy.deepcopy(r) for r in snapshot["records"] if r["kind"] == "event"],
                         "last_id": 0, "last_mid": 0, "last_extract_ts": 0.0}
        return renderer

    def render(self):
        with self._lock:
            return self._renderer(self._read()).render()

    def render_existing(self):
        with self._lock:
            return self._renderer(self._read()).render_existing()

    def query(self, text="", *, kind=None, limit=None):
        if not isinstance(text, str) or kind not in (None, "fact", "event"):
            raise ValueError("invalid guarded query")
        if limit is not None and (type(limit) is not int or limit < 0):
            raise ValueError("invalid guarded query limit")
        with self._lock:
            snapshot = self._read()
            records = [r for r in snapshot["records"] if (kind is None or r["kind"] == kind)
                       and text.casefold() in str(r.get("text", "")).casefold()]
            return copy.deepcopy(records if limit is None else records[:limit])

    def stats(self):
        with self._lock:
            snapshot = self._read()
            return {"version": VERSION, "stored_count": snapshot["stored_count"],
                    "recallable_count": snapshot["recallable_count"],
                    "recallable_facts": sum(r["kind"] == "fact" for r in snapshot["records"]),
                    "recallable_events": sum(r["kind"] == "event" for r in snapshot["records"]),
                    "pending_record_count": len(snapshot["pending_record_keys"]),
                    "capacity": copy.deepcopy(snapshot["capacity"]),
                    "memory_sha256": snapshot["memory_sha256"], "guarded": True,
                    "production_write_authorized": False}

    def commit_saved_kind(self, *, plan_path, result_path, kind_ledger_snapshot_path,
                          expected_plan_sha256, expected_result_sha256, batch, ledger_batch_key,
                          handoff_batch_key=None):
        """Validate saved v1 classification against its ORIGINAL ledger snapshot.

        No current evaluation is attached to an old label. Any mismatch, subset,
        new eligible member or older receipt fails before a memory handoff.
        """
        with self._lock:
            if self._closed:
                raise GateUnavailable("guarded memory is closed")
            try:
                self._require_stores()
                return self._commit_saved_kind(
                    Path(plan_path), Path(result_path), Path(kind_ledger_snapshot_path),
                    expected_plan_sha256, expected_result_sha256, batch, ledger_batch_key,
                    handoff_batch_key)
            except GateUnavailable:
                raise
            except Exception:
                raise InvalidSavedKind("saved kind binding rejected") from None

    def _commit_saved_kind(self, plan_path, result_path, frozen_ledger_path,
                           expected_plan_hash, expected_result_hash, batch, receipt_key, handoff_key):
        if (not all(isinstance(v, str) and re.fullmatch(r"[0-9a-f]{64}", v)
                    for v in (expected_plan_hash, expected_result_hash))
                or _sha(plan_path) != expected_plan_hash or _sha(result_path) != expected_result_hash):
            raise InvalidSavedKind("artifact hash mismatch")
        plan, result = _strict(plan_path.read_text(encoding="utf-8")), _strict(result_path.read_text(encoding="utf-8"))
        if (plan["version"] != SAVED_KIND_VERSION or result["_meta"]["version"] != SAVED_KIND_VERSION
                or result["_meta"]["plan_sha256"] != expected_plan_hash
                or plan["reference_labels_sent"] is not False
                or result["_meta"]["reference_labels_sent"] is not False
                or not isinstance(batch, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", batch)
                or _sha(frozen_ledger_path) != plan["ledger_snapshot_sha256"]):
            raise InvalidSavedKind("saved contract mismatch")
        jobs = [j for j in plan["jobs"] if j["batch"] == batch]
        outputs = [j for j in result["jobs"] if j["batch"] == batch]
        if len(jobs) != 1 or len(outputs) != 1:
            raise InvalidSavedKind("ambiguous saved batch")
        job, output = jobs[0], outputs[0]
        originals, sources = plan["original_candidates"][batch], plan["source_inputs"][batch]
        validation = self._modules["K"].validate(output["raw"], originals, batch, output["finish_reason"])
        if validation["valid"] is not True:
            raise InvalidSavedKind("saved raw validation failed")
        payload = job["request_payload"]
        data = _strict(payload["messages"][1]["content"].split("\n", 1)[1])
        if (set(data) != {"participants", "candidates", "source_messages"}
                or data["candidates"] != originals or data["source_messages"] != sources
                or data["participants"] != plan["participants"]
                or digest(payload) != job["request_payload_sha256"]
                or output["request_payload_sha256"] != job["request_payload_sha256"]
                or output["job_key"] != job["key"] or job["candidate_count"] != len(originals)
                or output["status"] != "valid_output" or output["finish_reason"] != "stop"):
            raise InvalidSavedKind("saved request/output mismatch")
        expected_joined = validation["joined"]
        if output["validation"]["valid"] is not True or output["validation"]["joined"] != expected_joined:
            raise InvalidSavedKind("saved joined objects mismatch")
        receipt = self._ledger.get_batch(receipt_key)
        if receipt["receipt_sha256"] != job["batch_receipt_sha256"]:
            raise InvalidSavedKind("saved receipt mismatch")
        members = {m["candidate_key"]: m for m in receipt["members"]}
        frozen = sqlite3.connect(frozen_ledger_path.resolve().as_uri() + "?mode=ro", uri=True)
        frozen.row_factory = sqlite3.Row
        classified = []
        try:
            for joined in expected_joined:
                key = joined["candidate_key"]
                old = frozen.execute("SELECT * FROM candidates WHERE candidate_key=?", (key,)).fetchone()
                if old is None or key not in members:
                    raise InvalidSavedKind("classification-time candidate missing")
                candidate = _strict(old["candidate_json"])
                evaluation = frozen.execute("SELECT evaluation_json FROM evaluations WHERE candidate_key=? AND evaluation_sha256=?",
                                            (key, old["latest_evaluation_sha256"])).fetchone()
                if evaluation is None:
                    raise InvalidSavedKind("classification-time evaluation missing")
                ev = _strict(evaluation[0])
                current = self._ledger.get(key)
                old_exportable = old["route"] == "eligible" and (old["review_state"] == "not_required" or
                    (old["review_state"] == "approved" and old["approved_evaluation_sha256"] == old["latest_evaluation_sha256"]))
                if (not old_exportable or candidate != joined["candidate"]
                        or digest(candidate) != old["candidate_sha256"] or old["candidate_sha256"] != joined["candidate_sha256"]
                        or digest(ev) != old["latest_evaluation_sha256"]
                        or ev["source_snapshot_sha256"] != digest(sources)
                        or current["candidate"] != candidate or current["candidate_sha256"] != old["candidate_sha256"]
                        or current["latest_evaluation_sha256"] != old["latest_evaluation_sha256"]
                        or not current["eligible_for_kind_time"]
                        or members[key]["evaluation_sha256"] != old["latest_evaluation_sha256"]):
                    raise InvalidSavedKind("classification-time/current binding mismatch")
                classified.append({"candidate_key": key, "candidate_sha256": old["candidate_sha256"],
                                   "evaluation_sha256": old["latest_evaluation_sha256"],
                                   "kind": joined["kind"], "certainty": joined["certainty"]})
        finally:
            frozen.close()
        self._coordinator._complete_binding = {"receipt_key": receipt_key, "receipt_sha256": receipt["receipt_sha256"],
                                               "expected_keys": {r["candidate_key"] for r in classified}}
        try:
            response = self._coordinator.commit(
                handoff_key or (VERSION + "/" + expected_result_hash + "/" + batch),
                classified, sources, ledger_batches=[receipt_key])
        finally:
            self._coordinator._complete_binding = None
        return {"version": VERSION, "batch": batch, "classified_count": len(classified),
                "stored_count": response["stored_count"], "recallable_count": response["recallable_count"],
                "intent_id": response["intent_id"], "idempotent": response["idempotent"],
                "kind_plan_sha256": expected_plan_hash, "kind_result_sha256": expected_result_hash,
                "classification_ledger_sha256": plan["ledger_snapshot_sha256"],
                "production_write_authorized": False}
