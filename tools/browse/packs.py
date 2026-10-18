"""The installed ForeverVO_Data* packs and their generated Data tables, read only.

A pack's tables are Lua files of `pack.<field> = { ... }` assignments
(tools/generate.py writes them); Pack.lua names the pack, its version and its
priority (tools/release_pack.py). The order is the addon's (Packs.lua): higher
priority first, then folder name.
"""

from __future__ import annotations

import contextlib
import functools
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tools.luatable import parse_value

# The same reading of Pack.lua as tools/audition's (not imported: audition
# brings in tools.generate, which needs fcntl and the GPU stack)
PACK_FIELD = re.compile(r'^\s*(name|priority|version)\s*=\s*"?([^",]+)"?', re.MULTILINE)
ASSIGNMENT = re.compile(r"^pack\.(\w+)\s*=", re.MULTILINE)
TABLE_FILES = ("Quests.lua", "Gossip.lua", "Books.lua", "Narrator.lua", "NPCs.lua")


@dataclass(frozen=True)
class Pack:
    folder: str
    label: str
    version: str
    priority: int
    root: Path  # the pack folder; its audio is under root / "Sounds"


def find_packs(addons: Path | None) -> list[Pack]:
    """Every ForeverVO_Data* folder with a Sounds folder, in the order the addon
    consults them."""
    if addons is None or not addons.is_dir():
        return []
    packs = []
    for folder in addons.glob("ForeverVO_Data*"):
        if not (folder / "Sounds").is_dir():
            continue
        fields: dict[str, str] = {}
        with contextlib.suppress(OSError):
            manifest = (folder / "Data" / "Pack.lua").read_text(encoding="utf-8")
            for key, value in PACK_FIELD.findall(manifest):
                fields.setdefault(key, value.strip())
        priority = 0
        with contextlib.suppress(ValueError):
            priority = int(fields.get("priority", 0))
        packs.append(
            Pack(
                folder.name,
                fields.get("name", folder.name),
                fields.get("version", ""),
                priority,
                folder,
            )
        )
    return sorted(packs, key=lambda p: (-p.priority, p.folder))


@functools.cache
def read_tables(pack: Pack) -> dict[str, Any]:
    """Every `pack.<field>` assignment in the pack's Data tables, by field. Cached:
    the catalog and the NPC names both read them, and Gossip.lua is large."""
    tables: dict[str, Any] = {}
    for name in TABLE_FILES:
        try:
            text = (pack.root / "Data" / name).read_text(encoding="utf-8")
        except OSError:
            continue
        for match in ASSIGNMENT.finditer(text):
            tables[match.group(1)] = parse_value(text[match.end() :])
    return tables
