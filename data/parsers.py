"""Parsers de datas e helpers de extração para os JSONs do PMM-e.

Os arquivos do PMM-e usam datas em formato brasileiro com timezone, ex.:
    "1/10/2025 20:00:57.335-03"   (data_matricula, created_at)
    "13/10/2025 16:00:00-03"      (data_hora_realizacao, data_hora_insert)

Também podem aparecer em ISO 8601 quando geradas pelo pipeline.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Iterable


_DATE_PATTERNS = (
    # Brasileiro com timezone: 1/10/2025 20:00:57.335-03  ou 13/10/2025 16:00:00-03
    re.compile(
        r"^(?P<d>\d{1,2})/(?P<m>\d{1,2})/(?P<y>\d{4})"
        r"(?:\s+(?P<H>\d{1,2}):(?P<M>\d{2})(?::(?P<S>\d{2})(?:\.(?P<f>\d+))?)?)?"
        r"(?P<tz>[+-]\d{2}(?::?\d{2})?)?$"
    ),
    # ISO 8601 simples ou com Z/offset
    re.compile(
        r"^(?P<y>\d{4})-(?P<m>\d{2})-(?P<d>\d{2})"
        r"(?:[T ](?P<H>\d{2}):(?P<M>\d{2})(?::(?P<S>\d{2})(?:\.(?P<f>\d+))?)?)?"
        r"(?P<tz>Z|[+-]\d{2}(?::?\d{2})?)?$"
    ),
)


def parse_date(value: str | None) -> datetime | None:
    """Aceita ISO 8601 ou formato brasileiro PMM-e. Retorna datetime tz-aware ou None."""
    if not value:
        return None
    s = str(value).strip()
    if not s:
        return None

    for pat in _DATE_PATTERNS:
        m = pat.match(s)
        if not m:
            continue
        try:
            y = int(m.group("y"))
            mo = int(m.group("m"))
            d = int(m.group("d"))
            H = int(m.group("H") or 0)
            M = int(m.group("M") or 0)
            S = int(m.group("S") or 0)
            f_raw = m.group("f") or ""
            micros = int(f_raw[:6].ljust(6, "0")) if f_raw else 0

            tz_str = m.group("tz")
            tz: timezone | None = None
            if tz_str:
                if tz_str.upper() == "Z":
                    tz = timezone.utc
                else:
                    sign = 1 if tz_str[0] == "+" else -1
                    cleaned = tz_str[1:].replace(":", "")
                    hh = int(cleaned[:2])
                    mm = int(cleaned[2:4]) if len(cleaned) >= 4 else 0
                    from datetime import timedelta

                    tz = timezone(sign * timedelta(hours=hh, minutes=mm))

            return datetime(y, mo, d, H, M, S, micros, tzinfo=tz)
        except (ValueError, TypeError):
            continue
    return None


def extract_year(value: str | None) -> int | None:
    """Extrai o ano de uma data PMM-e (BR ou ISO). None se inválido."""
    dt = parse_date(value)
    return dt.year if dt else None


def available_years(records: Iterable[dict], field: str) -> list[int]:
    """Lista de anos únicos (ordenados crescente) presentes em `records[*][field]`."""
    years = set()
    for r in records:
        y = extract_year(r.get(field))
        if y is not None:
            years.add(y)
    return sorted(years)


def infer_last_update(records: Iterable[dict], fields: tuple[str, ...]) -> datetime | None:
    """Maior data encontrada em `records[*][field]` percorrendo `fields` em ordem."""
    best: datetime | None = None
    for r in records:
        for f in fields:
            dt = parse_date(r.get(f))
            if dt is None:
                continue
            if best is None or dt > best:
                best = dt
            break
    return best


def format_br_date(dt: datetime | None) -> str | None:
    """Formata um datetime como dd/mm/aaaa (sem hora). None entra → None sai."""
    return dt.strftime("%d/%m/%Y") if dt else None
