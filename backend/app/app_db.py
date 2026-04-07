import csv
import json
import os
import sqlite3
from typing import Any, Dict, Iterable, List, Optional

from .config import APP_DB_PATH

DB_SCHEMA = """
create table if not exists products (
  parent_asin text primary key,
  title text,
  description text,
  features text,
  main_category text,
  store text,
  average_rating real,
  rating_number integer,
  price real,
  date_first_available text,
  image text,
  updated_at text default (datetime('now'))
);
"""


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(APP_DB_PATH) or ".", exist_ok=True)
    con = sqlite3.connect(APP_DB_PATH, timeout=3)
    con.row_factory = sqlite3.Row
    return con


def init_db() -> None:
    con = _connect()
    try:
        con.executescript(DB_SCHEMA)
        con.commit()
    finally:
        con.close()


def _normalize_row(row: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(row)
    features = out.get("features")
    if isinstance(features, str) and features:
        try:
            out["features"] = json.loads(features)
        except json.JSONDecodeError:
            out["features"] = features
    return out


def _row_to_db(row: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(row)
    features = out.get("features")
    if isinstance(features, (list, dict)):
        out["features"] = json.dumps(features, ensure_ascii=False)
    return out


def upsert_product(row: Dict[str, Any]) -> Dict[str, Any]:
    if not row.get("parent_asin"):
        raise ValueError("parent_asin is required")

    data = _row_to_db(row)
    con = _connect()
    try:
        con.execute(
            """
            insert into products (
              parent_asin, title, description, features, main_category, store,
              average_rating, rating_number, price, date_first_available, image, updated_at
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            on conflict(parent_asin) do update set
              title=excluded.title,
              description=excluded.description,
              features=excluded.features,
              main_category=excluded.main_category,
              store=excluded.store,
              average_rating=excluded.average_rating,
              rating_number=excluded.rating_number,
              price=excluded.price,
              date_first_available=excluded.date_first_available,
              image=excluded.image,
              updated_at=datetime('now')
            """,
            (
                data.get("parent_asin"),
                data.get("title"),
                data.get("description"),
                data.get("features"),
                data.get("main_category"),
                data.get("store"),
                data.get("average_rating"),
                data.get("rating_number"),
                data.get("price"),
                data.get("date_first_available"),
                data.get("image"),
            ),
        )
        con.commit()
    finally:
        con.close()
    return get_product(str(row["parent_asin"]))


def product_exists(parent_asin: str) -> bool:
    con = _connect()
    try:
        row = con.execute(
            "select 1 from products where parent_asin = ? limit 1", (parent_asin,)
        ).fetchone()
    finally:
        con.close()
    return row is not None


def delete_product(parent_asin: str) -> bool:
    con = _connect()
    try:
        cur = con.execute("delete from products where parent_asin = ?", (parent_asin,))
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


def get_product(parent_asin: str) -> Optional[Dict[str, Any]]:
    con = _connect()
    try:
        row = con.execute(
            "select * from products where parent_asin = ?", (parent_asin,)
        ).fetchone()
    finally:
        con.close()
    if not row:
        return None
    return _normalize_row(dict(row))


def list_products(
    limit: int = 50,
    offset: int = 0,
    parent_asin: Optional[str] = None,
    title: Optional[str] = None,
    store: Optional[str] = None,
    main_category: Optional[str] = None,
) -> List[Dict[str, Any]]:
    clauses = []
    params: List[Any] = []

    if parent_asin:
        clauses.append("parent_asin = ?")
        params.append(parent_asin)
    if title:
        clauses.append("title like ?")
        params.append(f"%{title}%")
    if store:
        clauses.append("store like ?")
        params.append(f"%{store}%")
    if main_category:
        clauses.append("main_category like ?")
        params.append(f"%{main_category}%")

    where = f"where {' and '.join(clauses)}" if clauses else ""
    sql = (
        f"select * from products {where} "
        "order by updated_at desc limit ? offset ?"
    )
    params.extend([limit, offset])

    con = _connect()
    try:
        rows = con.execute(sql, params).fetchall()
    finally:
        con.close()
    return [_normalize_row(dict(r)) for r in rows]


def count_products() -> int:
    con = _connect()
    try:
        count = con.execute("select count(*) from products").fetchone()[0]
    finally:
        con.close()
    return int(count or 0)


def get_products_by_ids(ids: Iterable[str]) -> List[Dict[str, Any]]:
    id_list = [str(x) for x in ids if x]
    if not id_list:
        return []
    placeholders = ",".join(["?"] * len(id_list))
    con = _connect()
    try:
        rows = con.execute(
            f"select * from products where parent_asin in ({placeholders})",
            id_list,
        ).fetchall()
    finally:
        con.close()
    by_id = {r["parent_asin"]: _normalize_row(dict(r)) for r in rows}
    return [by_id.get(i) for i in id_list if by_id.get(i) is not None]


def iter_products(limit: Optional[int] = None, keyword: Optional[str] = None):
    con = _connect()
    try:
        cursor = con.execute("select * from products")
        count = 0
        for row in cursor:
            out = _normalize_row(dict(row))
            if keyword and not _matches_keyword(out, keyword):
                continue
            yield out
            count += 1
            if limit and count >= limit:
                break
    finally:
        con.close()


def import_csv(
    csv_path: str,
    limit: Optional[int] = None,
    keyword: Optional[str] = None,
    skip_existing: bool = True,
) -> int:
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"CSV file not found: {csv_path}")
    inserted = 0
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if keyword and not _matches_keyword(row, keyword):
                continue
            parent_asin = row.get("parent_asin")
            if skip_existing and parent_asin and product_exists(str(parent_asin)):
                continue
            upsert_product(_normalize_row(row))
            inserted += 1
            if limit and inserted >= limit:
                break
    return inserted


def _matches_keyword(row: Dict[str, Any], keyword: str) -> bool:
    if not keyword:
        return True
    haystack = " ".join(
        [
            str(row.get("title") or ""),
            str(row.get("description") or ""),
            " ".join(str(x) for x in (row.get("features") or []) if x is not None)
            if isinstance(row.get("features"), list)
            else str(row.get("features") or ""),
            str(row.get("main_category") or ""),
            str(row.get("store") or ""),
        ]
    ).lower()
    return keyword.lower() in haystack
