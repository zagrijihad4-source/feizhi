"""Fixed-candidate kind labels, strictly joined by qualified batch/cid keys."""
from __future__ import annotations

import copy
import hashlib
import json
import re

VERSION = "eligible-kind-v1.0"
KINDS = {"fact", "event"}
CERTAINTIES = {"high", "mid", "low"}
FIELDS = {"cid", "kind", "certainty"}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def strict_json(raw):
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


def validate(raw, originals, batch_id, finish_reason="stop"):
    """No salvage, no default kind, no model edits, no cross-batch cid ambiguity."""
    def fail(code):
        return {"valid": False, "errors": [code], "labels": [], "joined": []}
    if not isinstance(batch_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", batch_id):
        return fail("invalid_batch_id")
    if finish_reason != "stop":
        return fail("completion_truncated" if finish_reason == "length" else "unexpected_finish_reason")
    if not isinstance(originals, list) or not originals or any(
            not isinstance(c, dict) or not isinstance(c.get("cid"), str)
            or not re.fullmatch(r"c[1-9][0-9]*", c["cid"]) for c in originals):
        return fail("invalid_originals")
    cids = [c["cid"] for c in originals]
    if len(cids) != len(set(cids)):
        return fail("duplicate_original_cid")
    try:
        obj = strict_json(raw)
    except (ValueError, TypeError):
        return fail("invalid_json")
    if not isinstance(obj, dict) or set(obj) != {"labels"} or not isinstance(obj["labels"], list):
        return fail("invalid_top_level")
    labels = obj["labels"]
    for label in labels:
        if not isinstance(label, dict) or set(label) != FIELDS:
            return fail("invalid_label_fields")
        if not isinstance(label["cid"], str) or not re.fullmatch(r"c[1-9][0-9]*", label["cid"]):
            return fail("invalid_local_cid")
        if not isinstance(label["kind"], str) or label["kind"] not in KINDS:
            return fail("invalid_kind")
        if not isinstance(label["certainty"], str) or label["certainty"] not in CERTAINTIES:
            return fail("invalid_certainty")
    ids = [r["cid"] for r in labels]
    if len(ids) != len(set(ids)):
        return fail("duplicate_label_cid")
    if len(ids) != len(cids) or set(ids) != set(cids):
        return fail("cid_bijection_failed")
    by_id = {r["cid"]: r for r in labels}
    joined = [{"candidate_key": batch_id + "/" + c["cid"], "candidate": copy.deepcopy(c),
               "candidate_sha256": digest(c), "kind": by_id[c["cid"]]["kind"],
               "certainty": by_id[c["cid"]]["certainty"], "write_authorized": False}
              for c in originals]
    return {"valid": True, "errors": [], "labels": [copy.deepcopy(by_id[cid]) for cid in cids], "joined": joined}


def score(joined, reference_rows):
    """Development reference only. Ambiguous refs are reported and excluded."""
    ref = {r["cid"]: r for r in reference_rows}
    if len(ref) != len(reference_rows):
        raise ValueError("duplicate_reference_key")
    keys = [r["candidate_key"] for r in joined]
    if len(keys) != len(set(keys)) or any(k not in ref for k in keys):
        raise ValueError("duplicate_or_unknown_qualified_candidate_key")
    correct = 0
    scored = 0
    wrong, ambiguous = [], []
    for item in joined:
        expected = ref[item["candidate_key"]]
        if expected["candidate_sha256"] != item["candidate_sha256"]:
            raise ValueError("reference_candidate_hash_mismatch")
        if expected["ref"] == "ambiguous":
            ambiguous.append(item["candidate_key"])
            continue
        if expected["ref"] not in KINDS:
            raise ValueError("unknown_reference_kind")
        scored += 1
        if expected["ref"] == item["kind"]:
            correct += 1
        else:
            wrong.append({"candidate_key": item["candidate_key"], "expected": expected["ref"], "actual": item["kind"]})
    return {"correct": correct, "scored": scored, "accuracy": correct / scored if scored else None,
            "wrong": wrong, "ambiguous_excluded": ambiguous,
            "scope": "known development eligible subset, not independent holdout or full-pipeline accuracy"}
