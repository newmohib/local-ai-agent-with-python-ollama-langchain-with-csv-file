import csv
import os
import re
import sqlite3
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .config import USER_DB_PATH

CSV_TO_DB_FIELDS: List[Tuple[str, str]] = [
    ("id", "id"),
    ("comcode", "comcode"),
    ("policynum", "policynum"),
    ("Agency", "agency"),
    ("ridernum", "ridernum"),
    ("plancode", "plancode"),
    ("comkey", "comkey"),
    ("lastName", "last_name"),
    ("firstName", "first_name"),
    ("fullname", "full_name"),
    ("dob", "dob"),
    ("gender", "gender"),
    ("poltype", "poltype"),
    ("crole", "crole"),
    ("age", "age"),
    ("IssueDate", "issue_date"),
    ("ADDR1", "addr1"),
    ("ADDR2", "addr2"),
    ("CITY", "city"),
    ("MOBILE", "mobile"),
    ("FATHERNAME", "father_name"),
    ("clttype", "clttype"),
    ("ben_seq_no", "ben_seq_no"),
    ("remarks", "remarks"),
    ("RRN", "rrn"),
    ("NID", "nid"),
    ("CLNTID", "clntid"),
]

DB_COLUMNS = [db for _, db in CSV_TO_DB_FIELDS]

DB_SCHEMA = (
    "create table if not exists users ("
    + ", ".join([f"{col} text" for col in DB_COLUMNS])
    + ", primary key (id)"
    + ");"
)


def _gender_values_from_text(text: str) -> List[str]:
    q = (text or "").lower()
    values: List[str] = []
    if re.search(r"\bmale\b", q) or re.search(r"\bm\b", q):
        values.append("m")
    if re.search(r"\bfemale\b", q) or re.search(r"\bf\b", q):
        values.append("f")
    return values


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(USER_DB_PATH) or ".", exist_ok=True)
    con = sqlite3.connect(USER_DB_PATH, timeout=3)
    con.row_factory = sqlite3.Row
    return con


def init_user_db() -> None:
    con = _connect()
    try:
        con.execute(DB_SCHEMA)
        con.commit()
    finally:
        con.close()


def _normalize_full_name(first_name: str, last_name: str) -> str:
    full = f"{first_name or ''} {last_name or ''}".strip()
    full = re.sub(r"\s+", " ", full)
    return full


def _row_from_csv(row: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for csv_key, db_key in CSV_TO_DB_FIELDS:
        out[db_key] = row.get(csv_key)
    if not out.get("full_name"):
        out["full_name"] = _normalize_full_name(
            out.get("first_name", "") or "",
            out.get("last_name", "") or "",
        )
    return out


def _row_to_db(row: Dict[str, Any]) -> Dict[str, Any]:
    out = {k: row.get(k) for k in DB_COLUMNS}
    if not out.get("full_name"):
        out["full_name"] = _normalize_full_name(
            out.get("first_name", "") or "",
            out.get("last_name", "") or "",
        )
    return out


def upsert_user(row: Dict[str, Any]) -> Dict[str, Any]:
    if not row.get("id"):
        raise ValueError("id is required")
    data = _row_to_db(row)
    placeholders = ", ".join(["?"] * len(DB_COLUMNS))
    columns = ", ".join(DB_COLUMNS)
    updates = ", ".join([f"{c}=excluded.{c}" for c in DB_COLUMNS if c != "id"])
    con = _connect()
    try:
        con.execute(
            f"insert into users ({columns}) values ({placeholders}) "
            f"on conflict(id) do update set {updates}",
            [data.get(c) for c in DB_COLUMNS],
        )
        con.commit()
    finally:
        con.close()
    return get_user(str(row["id"]))


def delete_user(user_id: str) -> bool:
    con = _connect()
    try:
        cur = con.execute("delete from users where id = ?", (user_id,))
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


def get_user(user_id: str) -> Optional[Dict[str, Any]]:
    con = _connect()
    try:
        row = con.execute("select * from users where id = ?", (user_id,)).fetchone()
    finally:
        con.close()
    if not row:
        return None
    return dict(row)


def list_users(
    limit: int = 50,
    offset: int = 0,
    filters: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    filters = filters or {}
    clauses = []
    params: List[Any] = []
    for key, value in filters.items():
        if key in DB_COLUMNS and value is not None and value != "":
            clauses.append(f"{key} like ?")
            params.append(f"%{value}%")
    where = f"where {' and '.join(clauses)}" if clauses else ""
    sql = (
        f"select * from users {where} "
        "order by id asc limit ? offset ?"
    )
    params.extend([limit, offset])
    con = _connect()
    try:
        rows = con.execute(sql, params).fetchall()
    finally:
        con.close()
    return [dict(r) for r in rows]


def search_users(
    query: str,
    limit: int = 50,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    q = (query or "").strip().lower()
    if not q:
        return list_users(limit=limit, offset=offset)

    tokens = re.findall(r"[a-z0-9]+", q)
    if not tokens:
        return list_users(limit=limit, offset=offset)

    field_map = {
        "city": "city",
        "mobile": "mobile",
        "phone": "mobile",
        "nid": "nid",
        "policy": "policynum",
        "policynum": "policynum",
        "id": "id",
        "dob": "dob",
        "date": "issue_date",
        "gender": "gender",
        "age": "age",
        "father": "father_name",
        "fathername": "father_name",
        "name": "full_name",
        "fullname": "full_name",
        "full": "full_name",
        "first": "first_name",
        "last": "last_name",
        "address": "addr1",
        "addr": "addr1",
    }

    field_hits = [field_map[t] for t in tokens if t in field_map]
    con = _connect()
    try:
        if field_hits:
            field = field_hits[0]
            stopwords = {
                "provide",
                "list",
                "data",
                "user",
                "users",
                "where",
                "is",
                "will",
                "be",
                "minimum",
                "maximum",
                "min",
                "max",
                "between",
                "the",
                "a",
                "an",
                "of",
                "in",
                "show",
                "get",
                "with",
                "for",
            }
            rest = [t for t in tokens if t not in field_map and t not in stopwords]
            term = " ".join(rest) if rest else q
            if field == "gender":
                gender_values = _gender_values_from_text(term or q)
                if gender_values:
                    placeholders = ", ".join(["?"] * len(gender_values))
                    rows = con.execute(
                        f"select * from users where lower(gender) in ({placeholders}) order by id asc limit ? offset ?",
                        (*gender_values, limit, offset),
                    ).fetchall()
                else:
                    like = f"%{term}%"
                    rows = con.execute(
                        f"select * from users where lower({field}) like ? order by id asc limit ? offset ?",
                        (like, limit, offset),
                    ).fetchall()
            else:
                like = f"%{term}%"
                rows = con.execute(
                    f"select * from users where lower({field}) like ? order by id asc limit ? offset ?",
                    (like, limit, offset),
                ).fetchall()
        else:
            gender_values = _gender_values_from_text(q)
            text_tokens = tokens[:]
            if gender_values:
                text_tokens = [
                    t for t in text_tokens if t not in {"male", "female", "m", "f", "gender"}
                ]
            clauses = [
                "(" + " or ".join([f"lower({col}) like ?" for col in DB_COLUMNS]) + ")"
                for _ in text_tokens
            ]
            params = []
            for t in text_tokens:
                like = f"%{t}%"
                params.extend([like for _ in DB_COLUMNS])
            where = " and ".join(clauses) if clauses else "1=1"
            if gender_values:
                placeholders = ", ".join(["?"] * len(gender_values))
                where = f"({where}) and lower(gender) in ({placeholders})"
                params.extend(gender_values)
            sql = f"select * from users where {where} order by id asc limit ? offset ?"
            params.extend([limit, offset])
            rows = con.execute(sql, params).fetchall()
    finally:
        con.close()
    return [dict(r) for r in rows]


def search_users_boolean(
    query: str,
    limit: int = 50,
    offset: int = 0,
) -> Optional[List[Dict[str, Any]]]:
    q = (query or "").strip().lower()
    if not q:
        return None

    if " and " not in q and " or " not in q:
        return None

    field_map = {
        "city": "city",
        "mobile": "mobile",
        "phone": "mobile",
        "nid": "nid",
        "policy": "policynum",
        "policynum": "policynum",
        "clntid": "clntid",
        "client": "clntid",
        "id": "id",
        "dob": "dob",
        "date": "issue_date",
        "issue": "issue_date",
        "gender": "gender",
        "age": "age",
        "father": "father_name",
        "fathername": "father_name",
        "name": "full_name",
        "fullname": "full_name",
        "first": "first_name",
        "last": "last_name",
        "address": "addr1",
        "addr": "addr1",
        "remarks": "remarks",
    }

    stopwords = {
        "provide",
        "list",
        "data",
        "user",
        "users",
        "where",
        "is",
        "will",
        "be",
        "minimum",
        "maximum",
        "min",
        "max",
        "between",
        "the",
        "a",
        "an",
        "of",
        "in",
        "show",
        "get",
        "with",
        "for",
        "and",
        "or",
        "under",
        "over",
        "below",
        "above",
        "less",
        "than",
        "at",
        "least",
        "ending",
        "ends",
        "last",
        "digit",
        "father",
        "name",
    }

    def _extract_field(clause: str) -> Optional[str]:
        tokens = re.findall(r"[a-z0-9]+", clause)
        for t in tokens:
            if t in field_map:
                return field_map[t]
        return None

    def _extract_term(clause: str) -> str:
        tokens = [t for t in re.findall(r"[a-z0-9]+", clause) if t not in stopwords]
        return " ".join(tokens).strip()

    def _parse_clause(clause: str) -> Optional[tuple[str, list[Any]]]:
        field = _extract_field(clause)
        if not field:
            return None

        numbers = re.findall(r"\d+", clause)

        if field == "age":
            min_match = re.search(r"(?:min|minimum|at least|over|above)\s*(\d+)", clause)
            max_match = re.search(
                r"(?:max|maximum|under|below|less than)\s*(\d+)", clause
            )
            exact_match = re.search(r"(?:^|\\b)age\\s*(?:is|=)?\\s*(\\d+)\\b", clause)
            min_age = int(min_match.group(1)) if min_match else None
            max_age = int(max_match.group(1)) if max_match else None
            if exact_match and min_age is None and max_age is None:
                exact_age = int(exact_match.group(1))
                return (
                    "cast(coalesce(nullif(age,''),'0') as integer) = ?",
                    [exact_age],
                )
            if min_age is None and max_age is None and numbers:
                if len(numbers) >= 2:
                    min_age = int(numbers[0])
                    max_age = int(numbers[1])
                else:
                    min_age = int(numbers[0])
                    max_age = int(numbers[0])
            clauses = []
            params: List[Any] = []
            if min_age is not None:
                clauses.append("cast(coalesce(nullif(age,''),'0') as integer) >= ?")
                params.append(min_age)
            if max_age is not None:
                clauses.append("cast(coalesce(nullif(age,''),'0') as integer) <= ?")
                params.append(max_age)
            if not clauses:
                return None
            return "(" + " and ".join(clauses) + ")", params

        if field == "gender":
            gender_values = _gender_values_from_text(clause)
            if gender_values:
                placeholders = ", ".join(["?"] * len(gender_values))
                return (f"lower(gender) in ({placeholders})", gender_values)

        if field in {"dob", "issue_date"}:
            dates = re.findall(r"\d{4}-\d{2}-\d{2}", clause)
            if dates:
                if len(dates) >= 2:
                    return (
                        f"({field} >= ? and {field} <= ?)",
                        [dates[0], dates[1]],
                    )
                return (f"{field} = ?", [dates[0]])

        if field == "mobile" and ("last" in clause and "digit" in clause) and numbers:
            suffix = numbers[-1]
            return ("mobile like ?", [f"%{suffix}"])

        term = _extract_term(clause)
        if term:
            return (f"lower({field}) like ?", [f"%{term}%"])
        return None

    or_groups = [part.strip() for part in re.split(r"\s+or\s+", q) if part.strip()]
    group_sqls: List[str] = []
    params: List[Any] = []

    for group in or_groups:
        and_parts = [p.strip() for p in re.split(r"\s+and\s+", group) if p.strip()]
        conds: List[str] = []
        group_params: List[Any] = []
        for clause in and_parts:
            parsed = _parse_clause(clause)
            if not parsed:
                conds = []
                group_params = []
                break
            sql, p = parsed
            conds.append(sql)
            group_params.extend(p)
        if conds:
            group_sqls.append("(" + " and ".join(conds) + ")")
            params.extend(group_params)

    if not group_sqls:
        return None

    where = " or ".join(group_sqls)
    sql = f"select * from users where {where} order by id asc limit ? offset ?"
    params.extend([limit, offset])
    con = _connect()
    try:
        rows = con.execute(sql, params).fetchall()
    finally:
        con.close()
    return [dict(r) for r in rows]


def search_by_mobile_suffix(
    suffix: str,
    limit: int = 50,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    cleaned = re.sub(r"\D", "", suffix or "")
    if not cleaned:
        return []
    like = f"%{cleaned}"
    con = _connect()
    try:
        rows = con.execute(
            "select * from users where mobile like ? order by id asc limit ? offset ?",
            (like, limit, offset),
        ).fetchall()
    finally:
        con.close()
    return [dict(r) for r in rows]


def search_by_mobile_suffixes(
    suffixes: Iterable[str],
    limit: int = 50,
) -> List[Dict[str, Any]]:
    clean = [re.sub(r"\D", "", s or "") for s in suffixes]
    clean = [s for s in clean if s]
    if not clean:
        return []
    con = _connect()
    try:
        rows = []
        for suf in clean:
            like = f"%{suf}"
            rows.extend(
                con.execute(
                    "select * from users where mobile like ? order by id asc",
                    (like,),
                ).fetchall()
            )
    finally:
        con.close()
    # de-dup by id, preserve order
    seen = set()
    out = []
    for r in rows:
        rid = r["id"]
        if rid in seen:
            continue
        seen.add(rid)
        out.append(dict(r))
        if len(out) >= limit:
            break
    return out


def search_by_age_range(
    min_age: Optional[int],
    max_age: Optional[int],
    limit: int = 50,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    if min_age is None and max_age is None:
        return []
    clauses = []
    params: List[Any] = []
    if min_age is not None:
        clauses.append("cast(coalesce(nullif(age,''),'0') as integer) >= ?")
        params.append(min_age)
    if max_age is not None:
        clauses.append("cast(coalesce(nullif(age,''),'0') as integer) <= ?")
        params.append(max_age)
    where = " and ".join(clauses)
    con = _connect()
    try:
        rows = con.execute(
            f"select * from users where {where} order by id asc limit ? offset ?",
            (*params, limit, offset),
        ).fetchall()
    finally:
        con.close()
    return [dict(r) for r in rows]


def search_by_field_and_age(
    field: str,
    term: str,
    min_age: Optional[int],
    max_age: Optional[int],
    limit: int = 50,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    if field not in DB_COLUMNS:
        return []
    clauses = [f"lower({field}) like ?"]
    params: List[Any] = [f"%{(term or '').lower()}%"]
    if min_age is not None:
        clauses.append("cast(coalesce(nullif(age,''),'0') as integer) >= ?")
        params.append(min_age)
    if max_age is not None:
        clauses.append("cast(coalesce(nullif(age,''),'0') as integer) <= ?")
        params.append(max_age)
    where = " and ".join(clauses)
    sql = f"select * from users where {where} order by id asc limit ? offset ?"
    params.extend([limit, offset])
    con = _connect()
    try:
        rows = con.execute(sql, params).fetchall()
    finally:
        con.close()
    return [dict(r) for r in rows]


def search_by_name_and_field(
    field: str,
    field_term: str,
    name_term: str,
    limit: int = 50,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    if field not in DB_COLUMNS:
        return []
    field_term = (field_term or "").strip().lower()
    name_term = (name_term or "").strip().lower()
    if not field_term or not name_term:
        return []

    if field == "gender":
        gender_values = _gender_values_from_text(field_term)
        if not gender_values:
            return []
        placeholders = ", ".join(["?"] * len(gender_values))
        sql = f"""
            select *
            from users
            where lower(gender) in ({placeholders})
              and (
                lower(coalesce(full_name, '')) like ?
                or lower(coalesce(first_name, '')) like ?
                or lower(coalesce(last_name, '')) like ?
              )
            order by id asc
            limit ? offset ?
        """
        params = [
            *gender_values,
            f"%{name_term}%",
            f"%{name_term}%",
            f"%{name_term}%",
            limit,
            offset,
        ]
        con = _connect()
        try:
            rows = con.execute(sql, params).fetchall()
        finally:
            con.close()
        return [dict(r) for r in rows]

    sql = f"""
        select *
        from users
        where lower({field}) like ?
          and (
            lower(coalesce(full_name, '')) like ?
            or lower(coalesce(first_name, '')) like ?
            or lower(coalesce(last_name, '')) like ?
          )
        order by id asc
        limit ? offset ?
    """
    params = [
        f"%{field_term}%",
        f"%{name_term}%",
        f"%{name_term}%",
        f"%{name_term}%",
        limit,
        offset,
    ]
    con = _connect()
    try:
        rows = con.execute(sql, params).fetchall()
    finally:
        con.close()
    return [dict(r) for r in rows]


def search_by_numeric_range(
    field: str,
    min_val: Optional[int],
    max_val: Optional[int],
    limit: int = 50,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    if min_val is None and max_val is None:
        return []
    if field not in DB_COLUMNS:
        return []
    clauses = []
    params: List[Any] = []
    if min_val is not None:
        clauses.append(f"cast({field} as integer) >= ?")
        params.append(min_val)
    if max_val is not None:
        clauses.append(f"cast({field} as integer) <= ?")
        params.append(max_val)
    where = " and ".join(clauses)
    con = _connect()
    try:
        rows = con.execute(
            f"select * from users where {where} order by id asc limit ? offset ?",
            (*params, limit, offset),
        ).fetchall()
    finally:
        con.close()
    return [dict(r) for r in rows]


def search_by_date_range(
    field: str,
    start_date: Optional[str],
    end_date: Optional[str],
    limit: int = 50,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    if field not in DB_COLUMNS:
        return []
    if start_date is None and end_date is None:
        return []
    clauses = []
    params: List[Any] = []
    if start_date:
        clauses.append(f"date({field}) >= date(?)")
        params.append(start_date)
    if end_date:
        clauses.append(f"date({field}) <= date(?)")
        params.append(end_date)
    where = " and ".join(clauses)
    con = _connect()
    try:
        rows = con.execute(
            f"select * from users where {where} order by id asc limit ? offset ?",
            (*params, limit, offset),
        ).fetchall()
    finally:
        con.close()
    return [dict(r) for r in rows]

def import_users_csv(
    csv_path: str,
    limit: Optional[int] = None,
    skip_existing: bool = True,
) -> Dict[str, Any]:
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"CSV file not found: {csv_path}")
    inserted = 0
    skipped = 0
    con = _connect()
    try:
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                data = _row_from_csv(row)
                if skip_existing and data.get("id"):
                    exists = con.execute(
                        "select 1 from users where id = ? limit 1", (data["id"],)
                    ).fetchone()
                    if exists:
                        skipped += 1
                        continue
                placeholders = ", ".join(["?"] * len(DB_COLUMNS))
                columns = ", ".join(DB_COLUMNS)
                updates = ", ".join(
                    [f"{c}=excluded.{c}" for c in DB_COLUMNS if c != "id"]
                )
                con.execute(
                    f"insert into users ({columns}) values ({placeholders}) "
                    f"on conflict(id) do update set {updates}",
                    [data.get(c) for c in DB_COLUMNS],
                )
                inserted += 1
                if limit and inserted >= limit:
                    break
        con.commit()
    finally:
        con.close()
    return {"inserted": inserted, "skipped": skipped, "path": csv_path}
