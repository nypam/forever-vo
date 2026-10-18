"""The browser's lines in memory: filters, paging, facet counts, and which lines
have a take in the comparison folder.

The comparison folder is laid out like a pack's Sounds/ (Quests/<id>-<event>.mp3,
Gossip/<speaker>-<hash>.mp3, ...), so a line pairs with the file at its own
whole-line path. A `$G` row (m-/f-) also pairs with a plain file there, since a
pipeline that does not branch on the player's sex writes only that. The folder
is listed once at startup.
"""

from __future__ import annotations

import os
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tools.browse.lines import Line
from tools.browse.packs import Pack

MAX_LIMIT = 500


@dataclass
class Filters:
    kind: str = ""
    pack: str = ""
    voice: str = ""
    zone: str = ""  # "" any, "unknown" for lines with none
    level_min: int | None = None  # a line with no level never matches a bound
    level_max: int | None = None
    quest_id: int | None = None
    npc: str = ""  # a speaker key, or part of a speaker's name
    q: str = ""  # words, all of which appear in the text or the title
    compare: bool = False  # only lines with a comparison take


def listing(root: Path) -> set[str]:
    found = set()
    for folder, _, names in os.walk(root):
        rel = os.path.relpath(folder, root).replace(os.sep, "/")
        prefix = "" if rel == "." else rel + "/"
        found.update(prefix + name for name in names)
    return found


def counted(values: list[Any]) -> list[dict[str, Any]]:
    counts = Counter(v for v in values if v is not None)
    return [
        {"value": value, "count": count}
        for value, count in sorted(counts.items(), key=lambda kv: (-kv[1], str(kv[0])))
    ]


class Catalog:
    def __init__(
        self,
        lines: list[Line],
        packs: list[Pack],
        compare_dir: Path | None,
        addons: Path | None,
        has_classic: bool,
    ) -> None:
        self.lines = lines
        self.packs = packs
        self.compare_dir = compare_dir
        self.addons = addons
        self.has_classic = has_classic
        self.compare_files = (
            listing(compare_dir) if compare_dir and compare_dir.is_dir() else set()
        )
        self.compared = {line.id: self._pair(line) for line in lines}

    def _pair(self, line: Line) -> str | None:
        if not self.compare_files:
            return None
        if line.path in self.compare_files:
            return line.path
        if line.variant.split(", ")[0] in ("male", "female"):
            folder, _, name = line.path.rpartition("/")
            plain = f"{folder}/{name[2:]}" if name[:2] in ("m-", "f-") else None
            if plain in self.compare_files:
                return plain
        return None

    def compare_path(self, line: Line) -> str | None:
        return self.compared.get(line.id, self._pair(line))

    def matches(self, line: Line, f: Filters) -> bool:
        if f.kind and line.kind != f.kind:
            return False
        if f.pack and line.pack != f.pack:
            return False
        if f.voice and line.voice != f.voice:
            return False
        if f.zone == "unknown" and line.zone:
            return False
        if f.zone and f.zone != "unknown" and line.zone != f.zone:
            return False
        if f.level_min is not None and (line.level is None or line.level < f.level_min):
            return False
        if f.level_max is not None and (line.level is None or line.level > f.level_max):
            return False
        if f.quest_id is not None and line.quest_id != f.quest_id:
            return False
        if f.npc:
            npc = f.npc.strip()
            if npc.lstrip("-").isdigit():
                if line.speaker != int(npc):
                    return False
            elif npc.lower() not in (line.speaker_name or "").lower():
                return False
        if f.q:
            haystack = f"{line.text or ''} {line.title or ''}".lower()
            if not all(word in haystack for word in f.q.lower().split()):
                return False
        return not (f.compare and self.compare_path(line) is None)

    def query(
        self, f: Filters, offset: int = 0, limit: int = 100
    ) -> tuple[int, list[Line]]:
        found = [line for line in self.lines if self.matches(line, f)]
        offset = max(offset, 0)
        limit = min(max(limit, 1), MAX_LIMIT)
        return len(found), found[offset : offset + limit]

    def facets(self) -> dict[str, Any]:
        packs = {pack.folder: pack for pack in self.packs}
        zones = counted([line.zone for line in self.lines])
        unknown = sum(1 for line in self.lines if not line.zone)
        if unknown:
            zones.append({"value": "unknown", "count": unknown})
        return {
            "totals": {
                "lines": len(self.lines),
                "with_compare": sum(1 for v in self.compared.values() if v),
            },
            "kinds": counted([line.kind for line in self.lines]),
            "packs": [
                {
                    **entry,
                    "label": packs[entry["value"]].label
                    if entry["value"] in packs
                    else entry["value"],
                    "version": packs[entry["value"]].version
                    if entry["value"] in packs
                    else "",
                }
                for entry in counted([line.pack for line in self.lines])
            ],
            "voices": counted([line.voice for line in self.lines]),
            "zones": zones,
            "has_classic": self.has_classic,
            "compare_label": self.compare_dir.name if self.compare_dir else None,
            "addons": str(self.addons) if self.addons else None,
            "packs_found": len(self.packs),
        }
