"""Conservative source-linked cover-page share candidates from Bronze HTML.

This is a candidate extractor, not a ticker mapper or PIT propagation rule.
Rows retain the exact source table/row text for inspection and can be
reconstructed from the referenced Bronze document hash.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime

from bs4 import BeautifulSoup


PARSER_VERSION = "cover_page_tables_v1"
MONTH = (r"(?:January|February|March|April|May|June|July|August|"
         r"September|October|November|December)")
DATE_RE = re.compile(rf"\b({MONTH}\s+\d{{1,2}},?\s+\d{{4}})\b", re.I)
COUNT_RE = re.compile(r"^\d{1,3}(?:,\d{3})+\s*$|^\d{4,}\s*$")
CLASS_RE = re.compile(r"\bClass\s+([A-Z])\b", re.I)
SHARE_WORDS = re.compile(r"\b(?:common|ordinary)\s+(?:stock|shares)\b", re.I)
CLASS_STOCK = re.compile(r"\bClass\s+[A-Z]\s+Stock\b", re.I)


@dataclass(frozen=True)
class CoverShare:
    as_of_date: date
    series_label: str | None
    class_label: str
    shares_outstanding: int
    table_index: int
    row_index: int
    source_row_text: str


def _text(value) -> str:
    return " ".join(value.get_text(" ", strip=True).split())


def _date(value: str) -> date | None:
    match = DATE_RE.search(value)
    if not match:
        return None
    normalized = re.sub(r"\s+", " ", match.group(1).replace(",", "")).strip()
    try:
        return datetime.strptime(normalized, "%B %d %Y").date()
    except ValueError:
        return None


def _count(cell: str) -> int | None:
    return int(cell.replace(",", "")) if COUNT_RE.fullmatch(cell) else None


def _cover_context(table) -> str:
    # The nearest text before a cover-page table often supplies the as-of
    # date; limit context so unrelated dates elsewhere in the filing do not
    # enter the candidate.
    previous = list(table.find_all_previous(string=True, limit=24))
    return " ".join(str(x).strip() for x in reversed(previous))[-1200:]


def extract_cover_shares(html: bytes) -> list[CoverShare]:
    soup = BeautifulSoup(html.decode("utf-8", errors="ignore"), "html.parser")
    found: list[CoverShare] = []
    for table_index, table in enumerate(soup.find_all("table")[:20]):
        rows = [
            [_text(cell) for cell in row.find_all(["td", "th"], recursive=False)]
            for row in table.find_all("tr")
        ]
        rows = [[cell for cell in cells if cell] for cells in rows]
        flat = " ".join(" ".join(cells) for cells in rows)
        context = _cover_context(table)
        if "outstanding" not in (flat + " " + context).lower():
            continue

        # Matrix layout: two share series can each have Class A/B/C. Keep
        # their series names, rather than merging equal class letters.
        header = next((cells for cells in rows[:5]
                       if sum(bool(CLASS_RE.fullmatch(c)) for c in cells) >= 2), None)
        matrix_date = _date(context) or _date(flat[:500])
        if header and matrix_date:
            classes = [c for c in header if CLASS_RE.fullmatch(c)]
            for row_index, cells in enumerate(rows):
                if not cells or not SHARE_WORDS.search(cells[0]):
                    continue
                series = cells[0]
                values = [_count(c) for c in cells[1:]]
                values = [v for v in values if v is not None]
                if len(values) != len(classes):
                    continue
                for label, value in zip(classes, values):
                    found.append(CoverShare(matrix_date, series, label,
                                            value, table_index, row_index,
                                            " | ".join(cells)))
            if any(x.table_index == table_index for x in found):
                continue

        # Two-column cover tables: class description and explicit count.
        table_date = _date(flat[:500]) or _date(context)
        for row_index, cells in enumerate(rows):
            if len(cells) < 2:
                continue
            label = cells[0]
            if not (SHARE_WORDS.search(label) or CLASS_STOCK.search(label)) \
                    or "weighted" in label.lower():
                continue
            counts = [_count(c) for c in cells[1:]]
            counts = [v for v in counts if v is not None]
            if len(counts) != 1:
                continue
            as_of = _date(label) or table_date
            if as_of is None:
                continue
            class_match = CLASS_RE.search(label)
            class_label = f"Class {class_match.group(1).upper()}" if class_match else "Common"
            found.append(CoverShare(as_of, None, label, counts[0],
                                    table_index, row_index, " | ".join(cells)))

    # Repeated HTML layouts may echo the same cover table. Preserve the first
    # source location while avoiding duplicate candidate values per filing.
    unique: dict[tuple, CoverShare] = {}
    for row in found:
        key = (row.as_of_date, row.series_label, row.class_label,
               row.shares_outstanding)
        unique.setdefault(key, row)
    return list(unique.values())
