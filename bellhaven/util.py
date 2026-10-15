"""Normalization and deterministic keys. No external API calls."""
import hashlib
import json
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def words(s):
    s = str(s or "").lower().replace("&", " and ")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", s)).strip()


def street_norm(s):
    s = words(s)
    alias = {"street": "st", "avenue": "ave", "road": "rd", "drive": "dr", "boulevard": "blvd", "lane": "ln", "court": "ct", "circle": "cir", "north": "n", "south": "s", "east": "e", "west": "w", "highway": "hwy", "parkway": "pkwy", "suite": "ste"}
    return " ".join(alias.get(x, x) for x in s.split())


def money(v):
    if v is None or v == "":
        return Decimal(0)
    try:
        return Decimal(str(v).replace(",", "").replace("$", ""))
    except InvalidOperation:
        raise ValueError(f"Unexpected money value: {v!r}; fail closed")


def key_for(payload):
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:20]


def load_json(path, default=None):
    path = Path(path)
    if not path.exists():
        return {} if default is None else default
    with path.open(encoding="utf8") as f:
        return json.load(f)


def save_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf8") as f:
        json.dump(value, f, ensure_ascii=False, indent=2, sort_keys=True, default=str)
    tmp.replace(path)
