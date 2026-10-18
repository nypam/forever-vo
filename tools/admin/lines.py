"""A pack's tables as playable lines: one row per thing a player can hear.

The pack format is documented at the top of ForeverVO/Core/Packs.lua, which is
the authority here. A line with parts (the speaker's words and the narrator's
stage directions) plays its parts back to back, as the addon does; the
whole-line file beside them is only for addons that predate parts. A `$G` line
exists as m-/f- files and is a row per sex. Other-sex, other-speaker and
alternate-narrator recordings are rows of their own, named by `variant`.
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from tools.admin.packs import Pack, read_tables

EVENTS = (("accept", "a"), ("progress", "p"), ("complete", "c"))
GENDERS = (("male", "m-"), ("female", "f-"))


@dataclass
class Line:
    id: str
    kind: str  # accept | progress | complete | gossip | book
    variant: (
        str  # "", "male", "sex f", "speaker 1234", "narrator <voice>", joined by ", "
    )
    quest_id: int | None
    speaker: int | None  # creature ID, negative for game objects
    voice: str | None
    duration: float | None  # the whole line's, or the sum of its parts
    path: str  # the whole-line file relative to Sounds/: the comparison key
    files: list[str]  # what plays, in order, relative to Sounds/
    pack: str  # Pack.folder
    missing: bool = False
    text: str | None = None
    title: str | None = None
    zone: str | None = None
    level: int | None = None
    speaker_name: str | None = None


def items(value: Any) -> list[tuple[Any, Any]]:
    """A Lua table's entries: the parser makes a table keyed 1..n a list."""
    if isinstance(value, list):
        return list(enumerate(value, start=1))
    if isinstance(value, dict):
        return list(value.items())
    return []


def indexed(value: Any) -> dict[int, Any]:
    return {k: v for k, v in items(value) if isinstance(k, int)}


def number(value: Any) -> float | None:
    return (
        float(value) if isinstance(value, int | float) and value is not True else None
    )


def integer(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def parts_of(value: Any) -> list[dict]:
    return [
        part for _, part in sorted(indexed(value).items()) if isinstance(part, dict)
    ]


def total(parts: list[dict], whole: Any) -> float | None:
    if parts:
        durations = [number(part.get("d")) for part in parts]
        return sum(d for d in durations if d is not None) if any(durations) else None
    return number(whole)


def narrated_total(
    parts: list[dict], voiced: dict[int, Any], whole: Any
) -> float | None:
    """An alternate narrator's duration: its own recording of each narrator part
    it voiced (`voiced`, by part index) and the pack's own for the rest."""
    if not parts:
        return number(whole)
    swapped = [
        dict(part, d=voiced[i]) if part.get("n") and i in voiced else part
        for i, part in enumerate(parts, start=1)
    ]
    return total(swapped, None)


def joined(*labels: str) -> str:
    return ", ".join(label for label in labels if label)


def other_sex_voice(recorded: Any, letter: str) -> str | None:
    """The voice of a line's other-sex file, as OtherSex in Packs.lua names it:
    the recorded voice's race with the other sex (human-male-official, f ->
    human-female). None when the recorded voice names no race."""
    if not isinstance(recorded, str) or "-" not in recorded:
        return None
    race = recorded.split("-", 1)[0]
    return f"{race}-{'male' if letter == 'm' else 'female'}"


def gendered(g: Any, letter: str) -> bool:
    return g is True or (isinstance(g, str) and letter in g)


def sound_files(pack: Pack) -> set[str]:
    """Every file under the pack's Sounds/, as /-joined relative paths."""
    root = pack.root / "Sounds"
    found = set()
    for folder, _, names in os.walk(root):
        rel = os.path.relpath(folder, root).replace(os.sep, "/")
        prefix = "" if rel == "." else rel + "/"
        found.update(prefix + name for name in names)
    return found


def part_files(
    parts: list[dict],
    name: Callable[[int], str],
    folder: str,
    narrator_folder: str = "",
    voiced: dict[int, Any] | None = None,
) -> list[str]:
    """The files a line with parts plays, in order: part i is `name(i)` in
    `folder`, except a narrator part (n) the alternate voice recorded (`voiced`
    holds its index), which plays from `narrator_folder`."""
    voiced = voiced or {}
    return [
        (narrator_folder if part.get("n") and i in voiced else folder) + name(i)
        for i, part in enumerate(parts, start=1)
    ]


def quest_lines(pack: Pack, tables: dict[str, Any]) -> list[Line]:
    voices = indexed(tables.get("narratorVoices"))
    narrator = dict(items(tables.get("narrator")))
    out = []
    for qid, entry in items(tables.get("quests")):
        if not isinstance(entry, dict) or integer(qid) is None:
            continue
        npc = integer(entry.get("npc"))
        ender = integer(entry.get("ender"))
        for event, x in EVENTS:
            if x not in entry and f"{x}P" not in entry:  # parts only: a stage direction
                continue
            speaker = npc if x == "a" else (ender if ender is not None else npc)
            parts = parts_of(entry.get(f"{x}P"))
            base_line: dict[str, Any] = {
                "kind": event,
                "quest_id": qid,
                "speaker": speaker,
                "pack": pack.folder,
            }
            prefixes = GENDERS if gendered(entry.get("g"), x) else (("", ""),)
            for sex, pre in prefixes:
                base = f"{pre}{qid}-{event}"

                def part(
                    i: int, pre: str = pre, qid: int = qid, event: str = event
                ) -> str:
                    return f"{pre}{qid}-p{i}-{event}.mp3"

                out.append(
                    Line(
                        id=f"q:{qid}:{event}:{sex}" if sex else f"q:{qid}:{event}",
                        variant=sex,
                        voice=entry.get(f"v{x}"),
                        duration=total(parts, entry.get(x)),
                        path=f"Quests/{base}.mp3",
                        files=part_files(parts, part, "Quests/")
                        or [f"Quests/{base}.mp3"],
                        **base_line,
                    )
                )
                for letter, d in items(entry.get(f"s{x}")):
                    if letter in ("m", "f"):
                        path = f"Quests/Sex/{letter}/{base}.mp3"
                        out.append(
                            Line(
                                id=f"q:{qid}:{event}:{joined(sex, f'sex {letter}')}",
                                variant=joined(sex, f"sex {letter}"),
                                voice=other_sex_voice(entry.get(f"v{x}"), letter),
                                duration=number(d),
                                path=path,
                                files=[path],
                                **base_line,
                            )
                        )
                for i, voice in voices.items():
                    alt = indexed(narrator.get(qid)).get(i)
                    if not isinstance(voice, str) or not isinstance(alt, dict):
                        continue
                    if x not in alt and f"{x}P" not in alt:
                        continue
                    voiced = indexed(alt.get(f"{x}P"))
                    folder = f"Quests/Narrator/{voice}/"
                    variant = joined(sex, f"narrator {voice}")
                    out.append(
                        Line(
                            id=f"q:{qid}:{event}:{variant}",
                            variant=variant,
                            voice=voice,
                            duration=narrated_total(parts, voiced, alt.get(x)),
                            path=f"{folder}{base}.mp3",
                            files=part_files(parts, part, "Quests/", folder, voiced)
                            or [f"{folder}{base}.mp3"],
                            **base_line,
                        )
                    )
            for key, record in items(entry.get(f"x{x}")):
                if not isinstance(record, dict) or integer(key) is None:
                    continue
                for sex, pre in prefixes:
                    path = f"Quests/Speaker/{key}/{pre}{qid}-{event}.mp3"
                    variant = joined(sex, f"speaker {key}")
                    out.append(
                        Line(
                            id=f"q:{qid}:{event}:{variant}",
                            variant=variant,
                            voice=record.get("v"),
                            duration=number(record.get("d")),
                            path=path,
                            files=[path],
                            **{**base_line, "speaker": key},
                        )
                    )
    return out


def gossip_lines(pack: Pack, tables: dict[str, Any]) -> list[Line]:
    voices = indexed(tables.get("narratorVoices"))
    out = []
    for key, entries in items(tables.get("gossip")):
        if integer(key) is None:
            continue
        for _, entry in items(entries):
            if not isinstance(entry, dict) or not isinstance(entry.get("f"), str):
                continue
            name, h = entry["f"], str(entry.get("h", ""))
            head, _, tail = name.rpartition("-")
            parts = parts_of(entry.get("P"))
            prefixes = GENDERS if entry.get("g") else (("", ""),)
            common: dict[str, Any] = {
                "kind": "gossip",
                "quest_id": None,
                "speaker": key,
                "pack": pack.folder,
            }
            for sex, pre in prefixes:
                ident = f"g:{key}:{h or name}"

                def part(
                    i: int, pre: str = pre, head: str = head, tail: str = tail
                ) -> str:
                    return f"{pre}{head}-p{i}-{tail}.mp3"

                out.append(
                    Line(
                        id=f"{ident}:{sex}" if sex else ident,
                        variant=sex,
                        voice=entry.get("v"),
                        duration=total(parts, entry.get("d")),
                        path=f"Gossip/{pre}{name}.mp3",
                        files=part_files(parts, part, "Gossip/")
                        or [f"Gossip/{pre}{name}.mp3"],
                        text=entry.get("t"),
                        **common,
                    )
                )
                for letter, d in items(entry.get("s")):
                    if letter in ("m", "f"):
                        path = f"Gossip/Sex/{letter}/{pre}{name}.mp3"
                        variant = joined(sex, f"sex {letter}")
                        out.append(
                            Line(
                                id=f"{ident}:{variant}",
                                variant=variant,
                                voice=other_sex_voice(entry.get("v"), letter),
                                duration=number(d),
                                path=path,
                                files=[path],
                                text=entry.get("t"),
                                **common,
                            )
                        )
                narrated = indexed(entry.get("n"))
                narrated_parts = indexed(entry.get("nP"))
                for i in sorted(set(narrated) | set(narrated_parts)):
                    voice = voices.get(i)
                    voiced = indexed(narrated_parts.get(i))
                    if not isinstance(voice, str):
                        continue
                    folder = f"Gossip/Narrator/{voice}/"
                    variant = joined(sex, f"narrator {voice}")
                    out.append(
                        Line(
                            id=f"{ident}:{variant}",
                            variant=variant,
                            voice=voice,
                            duration=narrated_total(parts, voiced, narrated.get(i)),
                            path=f"{folder}{pre}{name}.mp3",
                            files=part_files(parts, part, "Gossip/", folder, voiced)
                            or [f"{folder}{pre}{name}.mp3"],
                            text=entry.get("t"),
                            **common,
                        )
                    )
    return out


def book_lines(pack: Pack, tables: dict[str, Any]) -> list[Line]:
    voices = indexed(tables.get("narratorVoices"))
    out = []
    for key, entry in items(tables.get("books")):
        if not isinstance(entry, dict):
            continue
        common: dict[str, Any] = {
            "kind": "book",
            "quest_id": None,
            "speaker": None,
            "pack": pack.folder,
            "text": entry.get("s") or entry.get("t"),
            "title": entry.get("b"),
        }
        prefixes = GENDERS if entry.get("g") else (("", ""),)
        for sex, pre in prefixes:
            ident = f"b:{key}"
            path = f"Books/{pre}{key}-page.mp3"
            out.append(
                Line(
                    id=f"{ident}:{sex}" if sex else ident,
                    variant=sex,
                    voice="narrator",
                    duration=number(entry.get("d")),
                    path=path,
                    files=[path],
                    **common,
                )
            )
            for i, d in indexed(entry.get("n")).items():
                voice = voices.get(i)
                if not isinstance(voice, str):
                    continue
                path = f"Books/Narrator/{voice}/{pre}{key}-page.mp3"
                variant = joined(sex, f"narrator {voice}")
                out.append(
                    Line(
                        id=f"{ident}:{variant}",
                        variant=variant,
                        voice=voice,
                        duration=number(d),
                        path=path,
                        files=[path],
                        **common,
                    )
                )
    return out


def lines_of(pack: Pack, tables: dict[str, Any]) -> list[Line]:
    out = (
        quest_lines(pack, tables)
        + gossip_lines(pack, tables)
        + book_lines(pack, tables)
    )
    present = sound_files(pack)
    for line in out:
        line.missing = any(f not in present for f in line.files)
    return out


KIND_ORDER = {"q": 0, "g": 1, "b": 2}


def natural(text: str) -> list[Any]:
    """Sort key: quests, then gossip, then books, and q:9 before q:10."""
    head = KIND_ORDER.get(text.split(":", 1)[0], len(KIND_ORDER))
    return [
        head,
        *(int(s) if s.lstrip("-").isdigit() else s for s in re.split(r"(-?\d+)", text)),
    ]


def merge(packs: list[Pack]) -> list[Line]:
    """Every pack's lines; a line two packs carry comes from the one the addon
    consults first (`packs` is in that order)."""
    chosen: dict[str, Line] = {}
    for pack in packs:
        for line in lines_of(pack, read_tables(pack)):
            chosen.setdefault(line.id, line)
    return sorted(chosen.values(), key=lambda line: natural(line.id))
