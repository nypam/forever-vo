"""What the packs do not carry: quest text, titles, zones, levels, NPC names.

The sources are tools/data/bulk/*.json (fvo-classicdb writes classic.json from
VMaNGOS) under tools/data/capture.json, merged field by field with the capture
winning, which is generate.load_sources's rule; it is restated here because
tools.generate cannot be imported without fcntl and the GPU stack. A quest's
zone, when no capture names it, comes from the VMaNGOS snapshot itself.
"""

from __future__ import annotations

import contextlib
import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tools.admin.lines import EVENTS, Line, items
from tools.config import DATA_DIR

KINDS = ("quests", "gossip", "npcs")


@dataclass
class Texts:
    quests: dict[str, dict] = field(default_factory=dict)  # "<questID>-<event>"
    gossip: dict[str, dict] = field(default_factory=dict)  # "<speaker>|<hash>"
    npcs: dict[str, dict] = field(default_factory=dict)  # "<speaker>"
    has_classic: bool = False
    zones: dict[int, str] = field(
        default_factory=dict
    )  # quest ID -> zone, from the snapshot


def load_texts(data_dir: Path = DATA_DIR) -> Texts:
    texts = Texts()
    bulk = sorted(
        (data_dir / "bulk").glob("*.json"), key=lambda p: (p.stem != "classic", p.stem)
    )
    for path in [*bulk, data_dir / "capture.json"]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for kind in KINDS:
            merged = getattr(texts, kind)
            for key, entry in (data.get(kind) or {}).items():
                if not isinstance(entry, dict):
                    continue
                target = merged.setdefault(str(key), {})
                target.update(
                    {k: v for k, v in entry.items() if v is not None and v != ""}
                )
    texts.has_classic = (data_dir / "bulk" / "classic.json").exists()
    snapshot = next(iter(sorted(data_dir.glob("classicdb/**/mangos.sqlite"))), None)
    if snapshot is not None:
        texts.zones = snapshot_zones(snapshot)
    return texts


def snapshot_zones(db_path: Path) -> dict[int, str]:
    """Quest ID -> zone from VMaNGOS's quest_template.ZoneOrSort (a positive value
    is an area; a negative one is a quest sort, which names no place)."""
    zones: dict[int, str] = {}
    with contextlib.closing(
        sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    ) as conn:
        names: dict[int, str] = {}
        with contextlib.suppress(sqlite3.Error):
            names = dict(conn.execute("SELECT entry, name FROM area_template"))
        for quest_id, zone in conn.execute(
            "SELECT entry, ZoneOrSort FROM quest_template"
        ):
            if isinstance(zone, int) and zone > 0:
                zones[quest_id] = names.get(zone) or f"zone {zone}"
    return zones


def npc_names_of(tables_by_pack: list[dict[str, Any]]) -> dict[int, str]:
    """Speaker key -> name from each pack's `npcs` table, earlier packs winning."""
    names: dict[int, str] = {}
    for tables in tables_by_pack:
        for key, name in items(tables.get("npcs")):
            if isinstance(key, int) and isinstance(name, str) and name:
                names.setdefault(key, name)
    return names


def named(value: Any) -> str | None:
    return value if isinstance(value, str) and value and value != "Unknown" else None


def annotate(lines: list[Line], texts: Texts, npc_names: dict[int, str]) -> None:
    """Fills in text, title, level, zone and speaker name, in place."""
    gossip_zone: dict[str, str] = {}
    gossip_name: dict[str, str] = {}
    for entry in texts.gossip.values():
        npc = str(entry.get("npc"))
        if entry.get("zone"):
            gossip_zone.setdefault(npc, entry["zone"])
        if named(entry.get("name")):
            gossip_name.setdefault(npc, entry["name"])
    for line in lines:
        entry: dict = {}
        if line.quest_id is not None:
            entry = texts.quests.get(f"{line.quest_id}-{line.kind}", {})
            if line.text is None:
                line.text = entry.get("text")
            events = [
                texts.quests.get(f"{line.quest_id}-{event}", {}) for event, _ in EVENTS
            ]
            for attr in ("title", "level", "zone"):
                if getattr(line, attr) is None:
                    setattr(
                        line, attr, next((e[attr] for e in events if e.get(attr)), None)
                    )
            if line.zone is None:
                line.zone = texts.zones.get(line.quest_id)
        elif line.kind == "gossip" and line.speaker is not None:
            line.zone = line.zone or gossip_zone.get(str(line.speaker))
        if line.speaker is not None:
            line.speaker_name = (
                npc_names.get(line.speaker)
                or named((texts.npcs.get(str(line.speaker)) or {}).get("name"))
                or named(entry.get("name"))
                or gossip_name.get(str(line.speaker))
            )
