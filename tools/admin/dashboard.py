"""The dashboard's numbers: the whole library at a glance.

Every number that counts lines is Catalog.count_lines of a Filters built from
the same query string its link opens, so clicking a number lists exactly the
lines it counts. A line is a distinct line: a $G line's male and female rows,
and its other-sex, other-speaker and alternate-narrator recordings, are one line.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from tools.admin.catalog import Catalog, Filters, filters_from_query, query_of
from tools.admin.lines import is_variant, voiced

KINDS = ("accept", "progress", "complete", "gossip", "book")
BRACKETS = [(low, low + 9) for low in range(1, 70, 10)]


@dataclass
class Count:
    label: str
    value: int
    query: str  # the /lines query string that lists exactly these lines
    href: str = ""  # where the number links when it is not a Lines view

    @property
    def link(self) -> str:
        if self.href:
            return self.href
        return f"/lines?{self.query}" if self.query else "/lines"


@dataclass
class Summary:
    totals: list[Count]
    by_kind: list[list[Count]]
    by_level: list[list[Count]]
    by_zone: list[list[Count]]
    has_classic: bool = False
    notes: list[str] = field(default_factory=list)


def counted(catalog: Catalog, label: str, f: Filters) -> Count:
    query = query_of(f)
    return Count(label, catalog.count_lines(filters_from_query(query)), query)


def columns(
    catalog: Catalog, label: str, f: Filters, *, text_only: bool = False
) -> list[Count]:
    """One breakdown row: known, voiced, [text only,] yours, for the lines `f` selects."""
    known = counted(catalog, label, f)
    row = [
        known,
        counted(catalog, "voiced", replace(f, status="voiced")),
    ]
    if text_only:
        row.append(counted(catalog, "text only", replace(f, status="text_only")))
    row.append(counted(catalog, "yours", replace(f, status="yours")))
    return row


def summary(catalog: Catalog, npc_count: int, voice_count: int) -> Summary:
    lines = catalog.lines
    quests = {
        line.quest_id
        for line in lines
        if line.quest_id is not None and not is_variant(line)
    }
    variants = sum(1 for line in lines if is_variant(line) and voiced(line))
    totals = [
        Count("Quests known", len(quests), "kind=accept"),
        counted(catalog, "Lines known", Filters()),
        counted(catalog, "Voiced", Filters(status="voiced")),
        counted(catalog, "Text only", Filters(status="text_only")),
        counted(catalog, "Audio only", Filters(status="audio_only")),
        counted(catalog, "Yours", Filters(status="yours")),
        Count("NPCs speaking", npc_count, ""),
        Count("Voices in use", voice_count, "", href="/voices"),
        Count("Variant recordings", variants, "variants=1&status=voiced"),
    ]
    by_kind = [
        columns(catalog, kind, Filters(kind=kind), text_only=True) for kind in KINDS
    ]
    by_level = [
        columns(catalog, f"{low}-{high}", Filters(level_min=low, level_max=high))
        for low, high in BRACKETS
    ]
    by_level.append(columns(catalog, "unknown", Filters(level_unknown=True)))
    zones = sorted(
        {line.zone for line in lines if line.zone},
        key=lambda zone: (-catalog.count_lines(Filters(zone=zone)), zone),
    )
    by_zone = [columns(catalog, zone, Filters(zone=zone)) for zone in zones]
    if any(not line.zone for line in lines):
        by_zone.append(columns(catalog, "unknown", Filters(zone="unknown")))
    return Summary(totals, by_kind, by_level, by_zone, has_classic=catalog.has_classic)
