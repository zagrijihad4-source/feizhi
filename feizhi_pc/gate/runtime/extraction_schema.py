"""Pure validation of a complete extraction response before any write.

Compatibility is explicit:
* Both facts/events are required lists, with at most 12 elements per bucket.
* A nonempty string item is the historical no-citation form. It remains a string
  so the existing ingestion layer can retain it in quarantine, not recall it.
* Object items require a nonempty string text. Missing source_msg_ids means [],
  preserving the existing missing-source quarantine path; a provided value must
  be a list and every provided element must be a valid ID.
* Missing/None certainty and time_raw become "". Empty certainty means unknown;
  a nonempty certainty must be high/mid/low (case/outer whitespace normalized).
  Missing/None time_anchor_msg_id becomes None. No date is invented here.
* Extra object-item fields are ignored, but only the five allowed fields are
  returned: no model-supplied gate, manual time, archive or review authorization.
  Top-level extra keys are rejected.

The input is never modified and the function returns only after every element
has passed. The caller-supplied parse_id must be pure and return a positive int
or None. It may support integer strings; bool/float/other raw types are rejected
before calling it. Parsing failures never silently drop a reference.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any


MAX_ITEMS_PER_BUCKET = 12
BUCKETS = ("facts", "events")
CERTAINTIES = frozenset({"high", "mid", "low"})


class InvalidExtractionShape(ValueError):
    """Safe schema error: code/path only, never echo private input values."""

    def __init__(self, code: str, path: str):
        self.code = code
        self.path = path
        super().__init__(f"{code} at {path}")


def _id(value: Any, *, parse_id: Callable[[Any], int | None], path: str) -> int:
    # Do not let a permissive injected parser alias True or 1.9 to a message ID.
    if not (type(value) is int or isinstance(value, str)):
        raise InvalidExtractionShape("invalid_message_id", path)
    try:
        parsed = parse_id(value)
    except (TypeError, ValueError, OverflowError):
        # A parser exception may echo the rejected private value. Suppress its
        # traceback display; expose only a fixed code and structural path.
        raise InvalidExtractionShape("invalid_message_id", path) from None
    if type(parsed) is not int or parsed <= 0:
        raise InvalidExtractionShape("invalid_message_id", path)
    return parsed


def _item(item: Any, *, parse_id: Callable[[Any], int | None], path: str) -> str | dict:
    if isinstance(item, str):
        text = item.strip()
        if not text:
            raise InvalidExtractionShape("empty_text", path)
        return text
    if not isinstance(item, dict):
        raise InvalidExtractionShape("invalid_item_type", path)

    text = item.get("text")
    if not isinstance(text, str):
        raise InvalidExtractionShape("invalid_text_type", path + ".text")
    text = text.strip()
    if not text:
        raise InvalidExtractionShape("empty_text", path + ".text")

    sources = item.get("source_msg_ids", [])
    if not isinstance(sources, list):
        raise InvalidExtractionShape("invalid_source_container", path + ".source_msg_ids")
    ids = [_id(value, parse_id=parse_id, path=f"{path}.source_msg_ids[{index}]")
           for index, value in enumerate(sources)]

    anchor = item.get("time_anchor_msg_id")
    if anchor is not None:
        anchor = _id(anchor, parse_id=parse_id, path=path + ".time_anchor_msg_id")

    certainty = item.get("certainty")
    if certainty is None:
        certainty = ""
    elif not isinstance(certainty, str):
        raise InvalidExtractionShape("invalid_certainty_type", path + ".certainty")
    else:
        certainty = certainty.strip().lower()
        if certainty and certainty not in CERTAINTIES:
            raise InvalidExtractionShape("invalid_certainty", path + ".certainty")

    time_raw = item.get("time_raw")
    if time_raw is None:
        time_raw = ""
    elif not isinstance(time_raw, str):
        raise InvalidExtractionShape("invalid_time_raw_type", path + ".time_raw")
    else:
        time_raw = time_raw.strip()

    return {"text": text, "certainty": certainty, "source_msg_ids": ids,
            "time_raw": time_raw, "time_anchor_msg_id": anchor}


def validate_extraction(obj: Any, *, parse_id: Callable[[Any], int | None]) -> dict[str, list]:
    """Validate and normalize a complete response, with no writes or partial result.

    Returns {"facts": [...], "events": [...]} or raises InvalidExtractionShape.
    Both empty arrays are a valid complete empty result. More than 12 items in
    either bucket is rejected instead of silently truncating unprocessed data.
    """
    if not isinstance(obj, dict) or set(obj) != set(BUCKETS):
        raise InvalidExtractionShape("invalid_top_level", "$")
    if not callable(parse_id):
        raise InvalidExtractionShape("invalid_id_parser", "$")
    for bucket in BUCKETS:
        if not isinstance(obj[bucket], list):
            raise InvalidExtractionShape("invalid_bucket_type", "$." + bucket)
        if len(obj[bucket]) > MAX_ITEMS_PER_BUCKET:
            raise InvalidExtractionShape("too_many_items", "$." + bucket)

    # Both buckets' structure is checked first; all item outputs remain local
    # until the complete response has validated, including the last element.
    normalized = {}
    for bucket in BUCKETS:
        normalized[bucket] = [_item(item, parse_id=parse_id, path=f"$.{bucket}[{index}]")
                              for index, item in enumerate(obj[bucket])]
    return normalized
