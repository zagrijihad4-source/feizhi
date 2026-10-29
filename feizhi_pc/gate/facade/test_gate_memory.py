"""Synthetic-only facade checks. No real messages, model requests or approvals."""
import copy
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import gate_memory as G

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
SOURCES = [{"id": 1, "role": "user", "text": "synthetic-source", "sent_at_ms": 1793070000000}]


def env(cid, *, route="eligible", policy="synthetic-v1"):
    return {"candidate_key": "A/" + cid,
            "candidate": {"cid": cid, "text": "synthetic-" + cid, "source_msg_ids": [1],
                          "time_raw": "", "time_anchor_msg_id": None},
            "route": route, "scope": {"decision": "keep"},
            "support": {"status": "needs_review" if route == "review" else "supported"},
            "evidence": [{"source_msg_id": 1, "quote": "synthetic-source"}],
            "policy_version": policy, "source_snapshot_sha256": G.digest(SOURCES)}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class GateMemoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = G._bundle(BASE)

    def setUp(self):
        cases = HERE / "test_work"
        cases.mkdir(exist_ok=True)
        self.ws = Path(tempfile.mkdtemp(prefix="case-", dir=cases)).resolve()
        self.ledger_path = self.ws / "ledger.sqlite3"
        self.snapshot = self.ws / "classification_ledger.sqlite3"
        self.memory_path = self.ws / "memory.json"
        self.journal_path = self.ws / "handoff.sqlite3"
        with self.bundle["L"].ReviewLedger(self.ledger_path) as ledger:
            rows = [env("c1"), env("c2"), env("c3", route="review")]
            self.receipt = ledger.store_batch("source-A", rows, [r["candidate_key"] for r in rows])
        shutil.copy2(self.ledger_path, self.snapshot)
        self.originals = [env("c1")["candidate"], env("c2")["candidate"]]
        self.plan = {"version": G.SAVED_KIND_VERSION, "reference_labels_sent": False,
                     "participants": {"user": "synthetic-user", "assistant": "synthetic-assistant"},
                     "ledger_snapshot_sha256": sha(self.snapshot),
                     "original_candidates": {"A": self.originals}, "source_inputs": {"A": SOURCES}}
        data = {"participants": self.plan["participants"], "candidates": self.originals, "source_messages": SOURCES}
        payload = {"messages": [{"role": "system", "content": "synthetic-kind-contract"},
                                {"role": "user", "content": "fixed\n" + G.canonical(data)}]}
        self.plan["jobs"] = [{"key": "kind_A", "batch": "A", "candidate_count": 2,
                              "request_payload": payload, "request_payload_sha256": G.digest(payload),
                              "batch_receipt_sha256": self.receipt["receipt_sha256"]}]
        labels = [{"cid": c["cid"], "kind": "event", "certainty": "high"} for c in self.originals]
        joined = [{"candidate_key": "A/" + c["cid"], "candidate": c, "candidate_sha256": G.digest(c),
                   "kind": "event", "certainty": "high", "write_authorized": False} for c in self.originals]
        self.result = {"_meta": {"version": G.SAVED_KIND_VERSION, "reference_labels_sent": False},
                       "jobs": [{"job_key": "kind_A", "batch": "A", "status": "valid_output",
                                 "finish_reason": "stop", "request_payload_sha256": G.digest(payload),
                                 "raw": G.canonical({"labels": labels}),
                                 "validation": {"valid": True, "joined": joined}}]}
        self.plan_path, self.result_path = self.ws / "kind_plan.json", self.ws / "kind_results.json"
        self.write_artifacts()
        self.facade = self.open()

    def write_artifacts(self):
        self.plan_path.write_text(G.canonical(self.plan), encoding="utf-8")
        self.result["_meta"]["plan_sha256"] = sha(self.plan_path)
        self.result_path.write_text(G.canonical(self.result), encoding="utf-8")

    def open(self, **kwargs):
        return G.GateMemory(self.ws, ledger_path=self.ledger_path, journal_path=self.journal_path,
                            memory_path=self.memory_path, **kwargs)

    def commit(self, **overrides):
        args = {"plan_path": self.plan_path, "result_path": self.result_path,
                "kind_ledger_snapshot_path": self.snapshot,
                "expected_plan_sha256": sha(self.plan_path), "expected_result_sha256": sha(self.result_path),
                "batch": "A", "ledger_batch_key": "source-A"}
        args.update(overrides)
        return self.facade.commit_saved_kind(**args)

    def tearDown(self):
        self.facade.close()

    def test_commit_render_query_and_replay(self):
        first = self.commit()
        self.assertEqual((first["classified_count"], first["stored_count"], first["recallable_count"]), (2, 2, 2))
        self.assertIn("synthetic-c1", self.facade.render())
        self.assertIn("synthetic-c2", self.facade.render_existing())
        self.assertEqual(len(self.facade.query()), 2)
        self.assertEqual(len(self.facade.query("C1", kind="event")), 1)
        self.assertEqual(self.facade.query(limit=0), [])
        self.assertTrue(self.commit()["idempotent"])
        self.assertFalse(self.facade.stats()["production_write_authorized"])

    def test_each_consumer_guarded_read_is_fresh(self):
        self.commit()
        with patch.object(self.facade._coordinator, "guarded_read", wraps=self.facade._coordinator.guarded_read) as read:
            self.facade.render()
            self.facade.render_existing()
            self.facade.query()
            self.facade.stats()
            self.assertEqual(read.call_count, 4)

    def test_renderer_never_constructs_loads_or_saves_memory(self):
        self.commit()
        klass = self.facade._modules["M"].FeizhiMemory
        with patch.object(klass, "__init__", side_effect=AssertionError("constructor forbidden")), \
             patch.object(klass, "_load", side_effect=AssertionError("load forbidden")), \
             patch.object(klass, "save", side_effect=AssertionError("save forbidden")):
            self.assertIn("synthetic-c1", self.facade.render())
            self.assertIn("synthetic-c2", self.facade.render_existing())

    def test_query_and_stats_return_detached_data(self):
        self.commit()
        returned = self.facade.query()
        returned[0]["text"] = "mutated"
        returned[0]["source_msg_ids"].append(999)
        stats = self.facade.stats()
        stats["capacity"]["events"] = 0
        self.assertNotIn("mutated", self.facade.render())
        self.assertNotIn(999, self.facade.query()[0]["source_msg_ids"])
        self.assertEqual(self.facade.stats()["capacity"]["events"], 40)

    def test_new_evaluation_removes_old_content_from_all_consumers(self):
        self.commit()
        self.facade._ledger.store_evaluation(env("c1", route="review", policy="synthetic-v2"))
        self.assertNotIn("synthetic-c1", self.facade.render())
        self.assertNotIn("synthetic-c1", self.facade.render_existing())
        self.assertEqual([r["gate_candidate_key"] for r in self.facade.query()], ["A/c2"])
        self.assertEqual(self.facade.stats()["recallable_count"], 1)
        self.assertEqual(self.facade.stats()["pending_record_count"], 1)

    def test_unavailable_ledger_never_returns_cached_legacy(self):
        self.commit()
        for consumer in (self.facade.render, self.facade.render_existing, self.facade.query, self.facade.stats):
            with patch.object(self.facade._ledger, "get", side_effect=RuntimeError("synthetic unavailable")):
                with self.assertRaises(G.GateUnavailable):
                    consumer()

    def test_removed_ledger_file_blocks_live_handle(self):
        self.commit()
        self.facade._ledger.close()
        self.ledger_path.unlink()
        with self.assertRaises(G.GateUnavailable):
            self.facade.render()
        # Reopen only to make the normal teardown close safe.
        shutil.copy2(self.snapshot, self.ledger_path)
        self.facade._ledger = self.bundle["L"].ReviewLedger(self.ledger_path)
        self.facade._coordinator.ledger = self.facade._ledger

    def test_stale_saved_kind_cannot_bind_new_current_evaluation(self):
        self.facade._ledger.store_evaluation(env("c1", policy="synthetic-v2"))
        with self.assertRaises(G.InvalidSavedKind):
            self.commit()
        self.assertFalse(self.memory_path.exists())

    def test_synthetic_reapproval_does_not_refresh_old_classification(self):
        self.commit()
        self.facade._ledger.store_evaluation(env("c1", route="review", policy="synthetic-v2"))
        current = self.facade._ledger.get("A/c1")
        self.facade._ledger.resolve_review("A/c1", "approve", reviewer="test_operator", reason="synthetic test only",
            expected_candidate_sha256=current["candidate_sha256"],
            expected_evaluation_sha256=current["latest_evaluation_sha256"])
        self.assertTrue(self.facade._ledger.get("A/c1")["eligible_for_kind_time"])
        with self.assertRaises(G.InvalidSavedKind):
            self.commit()
        self.assertNotIn("synthetic-c1", self.facade.render())
        self.assertEqual(self.facade.stats()["recallable_count"], 1)

    def test_complete_current_eligible_set_required(self):
        # All artifacts are self-consistent but intentionally omit eligible c2.
        self.plan["original_candidates"]["A"] = self.originals[:1]
        payload = self.plan["jobs"][0]["request_payload"]
        data = G._strict(payload["messages"][1]["content"].split("\n", 1)[1])
        data["candidates"] = self.originals[:1]
        payload["messages"][1]["content"] = "fixed\n" + G.canonical(data)
        self.plan["jobs"][0]["candidate_count"] = 1
        self.plan["jobs"][0]["request_payload_sha256"] = G.digest(payload)
        output = self.result["jobs"][0]
        output["request_payload_sha256"] = G.digest(payload)
        labels = G._strict(output["raw"])["labels"][:1]
        output["raw"] = G.canonical({"labels": labels})
        output["validation"]["joined"] = output["validation"]["joined"][:1]
        self.write_artifacts()
        with self.assertRaises(G.InvalidSavedKind):
            self.commit()
        self.assertFalse(self.memory_path.exists())

    def test_raw_label_bijection_is_rechecked_not_trusted_joined(self):
        output = self.result["jobs"][0]
        output["raw"] = '{"labels":[{"cid":"c1","kind":"event","certainty":"high"}]}'
        self.write_artifacts()
        with self.assertRaises(G.InvalidSavedKind):
            self.commit()
        self.assertFalse(self.memory_path.exists())

    def test_artifact_and_snapshot_hashes_are_required(self):
        for override in ({"expected_plan_sha256": "0" * 64}, {"expected_result_sha256": "0" * 64}):
            with self.assertRaises(G.InvalidSavedKind):
                self.commit(**override)
        bad = self.ws / "not-snapshot.sqlite3"
        bad.write_bytes(b"not a ledger")
        with self.assertRaises(G.InvalidSavedKind):
            self.commit(kind_ledger_snapshot_path=bad)
        self.assertFalse(self.memory_path.exists())

    def test_changed_sources_cannot_reanchor_saved_candidate(self):
        self.plan["source_inputs"]["A"] = [{**SOURCES[0], "sent_at_ms": SOURCES[0]["sent_at_ms"] + 86400000}]
        payload = self.plan["jobs"][0]["request_payload"]
        data = G._strict(payload["messages"][1]["content"].split("\n", 1)[1])
        data["source_messages"] = self.plan["source_inputs"]["A"]
        payload["messages"][1]["content"] = "fixed\n" + G.canonical(data)
        self.plan["jobs"][0]["request_payload_sha256"] = G.digest(payload)
        self.result["jobs"][0]["request_payload_sha256"] = G.digest(payload)
        self.write_artifacts()
        with self.assertRaises(G.InvalidSavedKind):
            self.commit()
        self.assertFalse(self.memory_path.exists())

    def test_capacity_stored_and_recallable_are_distinct(self):
        self.facade.close()
        self.facade = self.open(capacity={"facts": 60, "events": 1})
        self.commit()
        stats = self.facade.stats()
        self.assertEqual((stats["stored_count"], stats["recallable_count"]), (2, 1))
        self.assertEqual(len(self.facade.query()), 1)

    def test_closed_facade_blocks_all_public_consumers(self):
        self.facade.close()
        for consumer in (self.facade.render, self.facade.render_existing, self.facade.query, self.facade.stats):
            with self.assertRaises(G.GateUnavailable):
                consumer()

    def test_parent_ledger_path_and_empty_database_are_rejected(self):
        outside = self.ws.parent / (self.ws.name + "-outside.sqlite3")
        shutil.copy2(self.ledger_path, outside)
        with self.assertRaises(G.GateUnavailable):
            G.GateMemory(self.ws, ledger_path=outside, journal_path=self.ws / "x.sqlite3", memory_path=self.ws / "x.json")
        empty = self.ws / "empty.sqlite3"
        empty.touch()
        with self.assertRaises(G.GateUnavailable):
            G.GateMemory(self.ws, ledger_path=empty, journal_path=self.ws / "y.sqlite3", memory_path=self.ws / "y.json")
        self.assertEqual(empty.stat().st_size, 0)

    def test_host_module_cache_does_not_select_old_renderer_dependencies(self):
        prior = {name: sys.modules.get(name) for name in ("memrec", "extraction_schema")}
        fake_records, fake_schema = types.ModuleType("fake_old_memrec"), types.ModuleType("fake_old_schema")
        G._BUNDLES.pop(BASE.resolve(), None)
        try:
            sys.modules["memrec"], sys.modules["extraction_schema"] = fake_records, fake_schema
            loaded = G._bundle(BASE)
            self.assertIs(loaded["M"].R, loaded["R"])
            self.assertTrue(loaded["M"].validate_extraction.__module__.startswith("_gate_schema_"))
            self.assertIs(sys.modules["memrec"], fake_records)
            self.assertIs(sys.modules["extraction_schema"], fake_schema)
        finally:
            for name, value in prior.items():
                if value is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = value

    def test_public_surface_has_no_raw_mutation_extract_or_approval_entry(self):
        self.assertFalse(hasattr(self.facade, "maybe_extract"))
        self.assertFalse(hasattr(self.facade, "add_record"))
        self.assertFalse(hasattr(self.facade, "resolve_review"))
        self.assertFalse(hasattr(self.facade, "data"))


if __name__ == "__main__":
    protected = [BASE / name for name in G.DEPENDENCIES]
    before = {str(p): {"sha256": sha(p), "mtime_ns": p.stat().st_mtime_ns} for p in protected}
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(GateMemoryTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    after = {str(p): {"sha256": sha(p), "mtime_ns": p.stat().st_mtime_ns} for p in protected}
    receipt = {"version": G.VERSION, "tests_run": result.testsRun, "failures": len(result.failures),
               "errors": len(result.errors), "new_api_calls": 0, "real_human_approvals": 0,
               "synthetic_human_approvals": 1, "dependency_before": before, "dependency_after": after,
               "dependencies_unchanged": before == after, "production_state_accessed": False,
               "actual_message_content_used": False}
    (HERE / "TEST_RECEIPT.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    raise SystemExit(0 if result.wasSuccessful() and before == after else 1)
