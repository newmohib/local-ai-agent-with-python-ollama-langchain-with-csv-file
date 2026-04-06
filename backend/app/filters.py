from __future__ import annotations

from datetime import date
from typing import Any, Dict, Optional

from dateutil import parser as date_parser


def coerce_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.strip().replace(",", "").replace("$", "")
        if not cleaned:
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def coerce_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        cleaned = value.strip().replace(",", "")
        if not cleaned:
            return None
        try:
            return int(float(cleaned))
        except ValueError:
            return None
    return None


def coerce_date_iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return None
        try:
            dt = date_parser.parse(cleaned, fuzzy=True)
            return dt.date().isoformat()
        except (ValueError, OverflowError):
            return None
    return None


def build_chroma_filter(filter_obj: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not filter_obj:
        return None

    out: Dict[str, Any] = {}

    if filter_obj.get("main_category"):
        out["main_category"] = filter_obj["main_category"]
    if filter_obj.get("store"):
        out["store"] = filter_obj["store"]

    def _add_range(field: str, min_key: str, max_key: str, coerce_fn):
        range_obj = filter_obj.get(field)
        if not isinstance(range_obj, dict):
            return
        min_val = coerce_fn(range_obj.get(min_key))
        max_val = coerce_fn(range_obj.get(max_key))
        if min_val is None and max_val is None:
            return
        clause: Dict[str, Any] = {}
        if min_val is not None:
            clause["$gte"] = min_val
        if max_val is not None:
            clause["$lte"] = max_val
        out[field] = clause

    _add_range("price", "min", "max", coerce_float)
    _add_range("average_rating", "min", "max", coerce_float)
    _add_range("rating_number", "min", "max", coerce_int)
    _add_range("date_first_available", "from", "to", coerce_date_iso)

    return out or None


def build_qdrant_filter(filter_obj: Optional[Dict[str, Any]]):
    if not filter_obj:
        return None

    from qdrant_client.http import models as qmodels

    must = []

    if filter_obj.get("main_category"):
        must.append(
            qmodels.FieldCondition(
                key="main_category",
                match=qmodels.MatchValue(value=filter_obj["main_category"]),
            )
        )
    if filter_obj.get("store"):
        must.append(
            qmodels.FieldCondition(
                key="store", match=qmodels.MatchValue(value=filter_obj["store"])
            )
        )

    def _add_range(field: str, min_key: str, max_key: str, coerce_fn):
        range_obj = filter_obj.get(field)
        if not isinstance(range_obj, dict):
            return
        min_val = coerce_fn(range_obj.get(min_key))
        max_val = coerce_fn(range_obj.get(max_key))
        if min_val is None and max_val is None:
            return
        must.append(
            qmodels.FieldCondition(
                key=field,
                range=qmodels.Range(gte=min_val, lte=max_val),
            )
        )

    _add_range("price", "min", "max", coerce_float)
    _add_range("average_rating", "min", "max", coerce_float)
    _add_range("rating_number", "min", "max", coerce_int)
    _add_range("date_first_available", "from", "to", coerce_date_iso)

    if not must:
        return None
    return qmodels.Filter(must=must)


def build_vector_filter(vector_db: str, filter_obj: Optional[Dict[str, Any]]):
    if vector_db == "qdrant":
        return build_qdrant_filter(filter_obj)
    return build_chroma_filter(filter_obj)
