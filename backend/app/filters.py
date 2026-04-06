from __future__ import annotations

from datetime import date
import re
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

    clauses = []

    if filter_obj.get("main_category"):
        clauses.append({"main_category": filter_obj["main_category"]})
    if filter_obj.get("store"):
        clauses.append({"store": filter_obj["store"]})

    def _add_range(field: str, min_key: str, max_key: str, coerce_fn):
        range_obj = filter_obj.get(field)
        if not isinstance(range_obj, dict):
            return
        min_val = coerce_fn(range_obj.get(min_key))
        max_val = coerce_fn(range_obj.get(max_key))
        if min_val is None and max_val is None:
            return
        if min_val is not None:
            clauses.append({field: {"$gte": min_val}})
        if max_val is not None:
            clauses.append({field: {"$lte": max_val}})

    _add_range("price", "min", "max", coerce_float)
    _add_range("average_rating", "min", "max", coerce_float)
    _add_range("rating_number", "min", "max", coerce_int)
    _add_range("date_first_available", "from", "to", coerce_date_iso)

    if not clauses:
        return None
    if len(clauses) == 1:
        return clauses[0]
    return {"$and": clauses}


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


def _first_float(patterns, text: str) -> Optional[float]:
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return float(match.group(1))
    return None


def infer_filter_from_query(query: str) -> Dict[str, Any]:
    text = (query or "").lower()
    inferred: Dict[str, Any] = {}

    price: Dict[str, float] = {}
    price_max = _first_float(
        [
            r"(?:under|below|less than)\s*\$\s*(\d+(?:\.\d+)?)",
            r"(?:maximum|max)\s*price\s*(?:is|of|will be)?\s*\$?\s*(\d+(?:\.\d+)?)",
            r"price\s*(?:under|below|less than|max|maximum)\s*\$?\s*(\d+(?:\.\d+)?)",
        ],
        text,
    )
    if price_max is not None:
        price["max"] = price_max

    price_min = _first_float(
        [
            r"(?:minimum|min)\s*price\s*(?:is|of|will be)?\s*\$?\s*(\d+(?:\.\d+)?)",
            r"price\s*(?:minimum|min|at least|more than|over|above)\s*\$?\s*(\d+(?:\.\d+)?)",
            r"(?:at least|more than|over|above)\s*\$\s*(\d+(?:\.\d+)?)",
        ],
        text,
    )
    if price_min is not None:
        price["min"] = price_min

    if price:
        inferred["price"] = price

    rating: Dict[str, float] = {}
    rating_min = _first_float(
        [
            r"(?:minimum|min)\s*(?:average\s*)?rating\s*(?:is|of|will be)?\s*(\d(?:\.\d+)?)",
            r"(?:average\s*)?rating\s*(?:at least|minimum|min|more than|over|above)\s*(\d(?:\.\d+)?)",
            r"(?:good|high)?\s*ratings?\s*(?:minimum|min|at least|more than|over|above)\s*(\d(?:\.\d+)?)",
            r"(\d(?:\.\d+)?)\s*\+?\s*(?:star|stars|rating)\s*(?:and up|or up|and above|or above|minimum|min|plus)?",
        ],
        text,
    )
    if rating_min is not None:
        rating["min"] = min(rating_min, 5.0)

    rating_max = _first_float(
        [
            r"(?:maximum|max)\s*(?:average\s*)?rating\s*(?:is|of|will be)?\s*(\d(?:\.\d+)?)",
            r"(?:average\s*)?rating\s*(?:under|below|less than|max|maximum)\s*(\d(?:\.\d+)?)",
        ],
        text,
    )
    if rating_max is not None:
        rating["max"] = min(rating_max, 5.0)

    if "good rating" in text or "good ratings" in text or "high rating" in text:
        rating.setdefault("min", 4.0)

    if rating:
        inferred["average_rating"] = rating

    rating_count: Dict[str, int] = {}
    rating_count_min = _first_float(
        [
            r"(?:minimum|min|at least|more than|over|above)\s*(\d+(?:\.\d+)?)\s*(?:reviews|review|ratings|rating count)",
            r"(?:reviews|review|rating count)\s*(?:minimum|min|at least|more than|over|above)\s*(\d+(?:\.\d+)?)",
        ],
        text,
    )
    if rating_count_min is not None:
        rating_count["min"] = int(rating_count_min)

    if rating_count:
        inferred["rating_number"] = rating_count

    return inferred


def merge_filter_objects(
    explicit_filter: Optional[Dict[str, Any]],
    inferred_filter: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    merged: Dict[str, Any] = {}
    if inferred_filter:
        merged.update(inferred_filter)
    if explicit_filter:
        for key, value in explicit_filter.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key].update(value)
            else:
                merged[key] = value
    return merged or None
