"""Synthetic trusted-host boundary checks. No real pending candidate is approved."""
import copy
import json
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "ledger_code"))
from review_ledger import ReviewLedger
from review_boundary import (ReviewBoundary, TrustedDecision, AuthorizationDenied,
                             ReviewBoundaryError, NeedsReconciliation)


def envelope(key="synthetic-A/c1", policy="test-v1", route="review"):
    return {"candidate_key": key, "candidate": {"cid": key.rsplit("/",1)[-1],"text":"synthetic pending observation",
        "source_msg_ids":[1],"time_raw":"","time_anchor_msg_id":None},
        "route":route,"scope":{"decision":"keep"},
        "support":{"status":"needs_review" if route=="review" else "supported"},
        "evidence":[{"source_msg_id":1,"quote":"synthetic evidence","mode":"assertion"}],
        "policy_version":policy,"source_snapshot_sha256":"f"*64}


def authorize(packet, decision="approve"):
    return TrustedDecision(packet["request_id"],packet["candidate_key"],packet["candidate_sha256"],
        packet["evaluation_sha256"],packet["packet_sha256"],decision,"synthetic-test-operator",
        "synthetic fixture decision only","synthetic-test-not-human-authentication",True)


class BoundaryTests(unittest.TestCase):
    def setUp(self):
        base=HERE/"test_work";base.mkdir(exist_ok=True)
        self.ws=Path(tempfile.mkdtemp(dir=base))
        self.ledger=ReviewLedger(self.ws/"ledger.sqlite3")
        self.ledger.store_evaluation(envelope())
        self.boundaries=[]
    def tearDown(self):
        for boundary in self.boundaries:boundary.close()
        self.ledger.close()
    def boundary(self, authorizer=None, hook=None):
        b=ReviewBoundary(self.ws,self.ledger,self.ws/"requests.sqlite3",authorizer=authorizer,fault_hook=hook)
        self.boundaries.append(b);return b
    def test_prepare_is_undecided_and_preserves_ledger(self):
        b=self.boundary();before=self.ledger.events();packet=b.prepare("synthetic-A/c1")
        self.assertIsNone(packet["decision"])
        self.assertEqual(packet["candidate_sha256"],self.ledger.get("synthetic-A/c1")["candidate_sha256"])
        self.assertTrue(packet["evidence"]);self.assertTrue(packet["versions"]["policy_version"])
        self.assertEqual(self.ledger.events(),before)
        self.assertFalse(packet["production_write_authorized"])
    def test_default_authorizer_does_not_call_resolve(self):
        b=self.boundary();p=b.prepare("synthetic-A/c1")
        with patch.object(self.ledger,"resolve_review",wraps=self.ledger.resolve_review) as resolve:
            with self.assertRaises(AuthorizationDenied):b.apply(p["request_id"])
            self.assertEqual(resolve.call_count,0)
        self.assertEqual(self.ledger.get("synthetic-A/c1")["review_state"],"pending")
    def test_payload_self_report_cannot_authorize(self):
        b=self.boundary();p=b.prepare("synthetic-A/c1")
        with self.assertRaises(ReviewBoundaryError):b.apply({"request_id":p["request_id"],"is_human":True,"actor":"user","decision":"approve"})
        with self.assertRaises(TypeError):b.apply(p["request_id"],is_human=True)
        self.assertEqual(self.ledger.get("synthetic-A/c1")["review_state"],"pending")
    def test_authorizer_raw_dictionary_is_not_a_trusted_decision(self):
        b=self.boundary(lambda p:{"is_human":True,"actor":"user","decision":"approve"});p=b.prepare("synthetic-A/c1")
        with self.assertRaises(AuthorizationDenied):b.apply(p["request_id"])
    def test_trusted_approval_and_receipt_do_not_authorize_production_write(self):
        b=self.boundary(authorize);p=b.prepare("synthetic-A/c1");result=b.apply(p["request_id"])
        self.assertEqual(result["review_state"],"approved")
        self.assertFalse(result["production_write_authorized"])
        self.assertFalse(result["receipt"]["ledger_commit_proven_by_receipt"])
        self.assertTrue(b.inspect(p["request_id"])["current_ledger_effect_matches_receipt"])
        self.assertFalse(self.ledger.get("synthetic-A/c1")["write_authorized"])
    def test_trusted_rejection_is_explicit_and_nonexportable(self):
        b=self.boundary(lambda p:authorize(p,"reject"));p=b.prepare("synthetic-A/c1");b.apply(p["request_id"])
        self.assertEqual(self.ledger.get("synthetic-A/c1")["review_state"],"rejected")
        self.assertEqual(self.ledger.export_eligible(),[])
    def test_duplicate_apply_never_resolves_twice_even_after_reopen(self):
        b=self.boundary(authorize);p=b.prepare("synthetic-A/c1");b.apply(p["request_id"])
        b2=self.boundary(authorize)
        with patch.object(self.ledger,"resolve_review",wraps=self.ledger.resolve_review) as resolve:
            with self.assertRaises(NeedsReconciliation):b2.apply(p["request_id"])
            self.assertEqual(resolve.call_count,0)
    def test_stale_hash_fails_before_authorizer_or_resolve(self):
        calls=[];b=self.boundary(lambda p:calls.append(p) or authorize(p));p=b.prepare("synthetic-A/c1")
        self.ledger.store_evaluation(envelope(policy="test-v2"))
        with patch.object(self.ledger,"resolve_review",wraps=self.ledger.resolve_review) as resolve:
            with self.assertRaises(ReviewBoundaryError):b.apply(p["request_id"])
            self.assertEqual(resolve.call_count,0)
        self.assertEqual(calls,[])
    def test_decision_bound_to_other_subject_or_hash_is_denied(self):
        for field,value in (("candidate_key","synthetic-B/c2"),("candidate_sha256","0"*64),
            ("evaluation_sha256","0"*64),("packet_sha256","0"*64),("request_id","rvw_"+"0"*32)):
            b=self.boundary(lambda p,f=field,v=value:replace(authorize(p),**{f:v}));p=b.prepare("synthetic-A/c1")
            with self.subTest(field=field):
                with self.assertRaises(AuthorizationDenied):b.apply(p["request_id"])
        self.assertEqual(self.ledger.get("synthetic-A/c1")["review_state"],"pending")
    def test_missing_authorized_flag_and_unknown_decision_are_denied(self):
        for change in ({"authorized":False},{"decision":"continue"},{"reason":""},{"principal":""},{"authorization_ref":""}):
            b=self.boundary(lambda p,c=change:replace(authorize(p),**c));p=b.prepare("synthetic-A/c1")
            with self.assertRaises(AuthorizationDenied):b.apply(p["request_id"])
    def test_authorizer_time_does_not_allow_stale_snapshot(self):
        def changing(p):self.ledger.store_evaluation(envelope(policy="test-v2"));return authorize(p)
        b=self.boundary(changing);p=b.prepare("synthetic-A/c1")
        with patch.object(self.ledger,"resolve_review",wraps=self.ledger.resolve_review) as resolve:
            with self.assertRaises(ReviewBoundaryError):b.apply(p["request_id"])
            self.assertEqual(resolve.call_count,0)
    def test_nonpending_candidate_cannot_prepare_or_apply(self):
        b=self.boundary(authorize);p=b.prepare("synthetic-A/c1");b.apply(p["request_id"])
        with self.assertRaises(ReviewBoundaryError):b.prepare("synthetic-A/c1")
    def test_receipt_write_failure_rolls_back_ledger_resolution(self):
        b=self.boundary(authorize);p=b.prepare("synthetic-A/c1")
        with patch.object(b,"_record_receipt",side_effect=OSError("synthetic registry failure")):
            with self.assertRaises(OSError):b.apply(p["request_id"])
        self.assertEqual(self.ledger.get("synthetic-A/c1")["review_state"],"pending")
        self.assertFalse(any(e["event_type"]=="review_approved" for e in self.ledger.events()))
        with self.assertRaises(NeedsReconciliation):b.apply(p["request_id"])
    def test_receipt_before_ledger_commit_is_not_approval(self):
        def fail(phase):
            if phase=="after_receipt_before_ledger_commit":raise RuntimeError("synthetic precommit exit")
        b=self.boundary(authorize,fail);p=b.prepare("synthetic-A/c1")
        with self.assertRaises(RuntimeError):b.apply(p["request_id"])
        observed=b.inspect(p["request_id"])
        self.assertIsNotNone(observed["receipt"])
        self.assertFalse(observed["current_ledger_effect_matches_receipt"])
        self.assertTrue(observed["needs_reconciliation"])
        self.assertEqual(self.ledger.get("synthetic-A/c1")["review_state"],"pending")
        with self.assertRaises(NeedsReconciliation):b.prepare("synthetic-A/c1")
    def test_exported_packet_mutation_does_not_change_stored_request(self):
        b=self.boundary(authorize);p=b.prepare("synthetic-A/c1");original=copy.deepcopy(p)
        p["candidate"]["text"]="altered";p["decision"]="approve"
        self.assertEqual(b.get_packet(p["request_id"]),original)
    def test_corrupt_stored_packet_is_rejected_without_resolve(self):
        b=self.boundary(authorize);p=b.prepare("synthetic-A/c1")
        b._db.execute("UPDATE review_requests SET packet_json='{}' WHERE request_id=?",(p["request_id"],))
        with self.assertRaises(ReviewBoundaryError):b.apply(p["request_id"])
        self.assertEqual(self.ledger.get("synthetic-A/c1")["review_state"],"pending")
    def test_approve_invalidate_then_new_authorization_and_reclassification(self):
        b=self.boundary(authorize);p=b.prepare("synthetic-A/c1");b.apply(p["request_id"])
        first=self.ledger.get("synthetic-A/c1")
        self.assertTrue(first["eligible_for_kind_time"])
        synthetic_kind={"kind":"event","evaluation_sha256":first["latest_evaluation_sha256"]}
        self.ledger.store_evaluation(envelope(policy="test-v2"))
        changed=self.ledger.get("synthetic-A/c1")
        self.assertFalse(changed["eligible_for_kind_time"])
        self.assertNotEqual(changed["latest_evaluation_sha256"],synthetic_kind["evaluation_sha256"])
        new=b.prepare("synthetic-A/c1");b.apply(new["request_id"])
        reclassified={"kind":"event","evaluation_sha256":self.ledger.get("synthetic-A/c1")["latest_evaluation_sha256"]}
        self.assertNotEqual(reclassified["evaluation_sha256"],synthetic_kind["evaluation_sha256"])
    def test_paths_cannot_target_root_or_original_ledger(self):
        with self.assertRaises(ReviewBoundaryError):ReviewBoundary(ROOT,self.ledger,ROOT/"requests.sqlite3")
        with self.assertRaises(ReviewBoundaryError):ReviewBoundary(self.ws,self.ledger,self.ws)
        with self.assertRaises(ReviewBoundaryError):ReviewBoundary(self.ws,self.ledger,self.ws/"ledger.sqlite3")
        with self.assertRaises(ReviewBoundaryError):ReviewBoundary(self.ws,self.ledger,HERE/"outside.sqlite3")
    def test_frozen_code_and_fixture_directories_are_not_workspaces(self):
        for name in ("fixtures","runtime","ledger_code","coordinator","review"):
            path=ROOT/name
            if path.is_dir():
                with self.subTest(name=name):
                    with self.assertRaises(ReviewBoundaryError):ReviewBoundary(path,self.ledger,path/"requests.sqlite3")

if __name__=="__main__":unittest.main(verbosity=2)
