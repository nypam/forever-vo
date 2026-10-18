"""The library: every line forever-vo knows, voiced or not.

The packs hold the lines that have audio. capture.json and bulk/*.json hold the
text of every line players or Classic's database have shown, voiced or not:
progress text above all, which fvo-generate voices only with --progress. A known
line with no pack row joins the library as a text-only row, at the path its file
would have, so a comparison take for it still pairs by name.
"""

from __future__ import annotations

from tools.admin.lines import Line, line_key, natural
from tools.admin.texts import Texts


def speaker_of(entry: dict) -> int | None:
    npc = str(entry.get("npc") or "")
    return int(npc) if npc.lstrip("-").isdigit() else None


def known_lines(texts: Texts) -> list[Line]:
    """One text-only row per line in the sources, keyed as the packs key theirs."""
    out = []
    for key, entry in texts.quests.items():
        quest, _, event = key.partition("-")
        if not quest.isdigit() or event not in ("accept", "progress", "complete"):
            continue
        out.append(
            Line(
                id=f"q:{quest}:{event}",
                kind=event,
                variant="",
                quest_id=int(quest),
                speaker=speaker_of(entry),
                voice=None,
                duration=None,
                path=f"Quests/{quest}-{event}.mp3",
                files=[],
                pack="",
                text=entry.get("text"),
            )
        )
    for key, entry in texts.gossip.items():
        speaker, _, digest = key.partition("|")
        if not speaker.lstrip("-").isdigit() or not digest:
            continue
        out.append(
            Line(
                id=f"g:{speaker}:{digest}",
                kind="gossip",
                variant="",
                quest_id=None,
                speaker=int(speaker),
                voice=None,
                duration=None,
                path=f"Gossip/{speaker}-{digest}.mp3",
                files=[],
                pack="",
                text=entry.get("text"),
            )
        )
    for key, entry in texts.books.items():
        out.append(
            Line(
                id=f"b:{key}",
                kind="book",
                variant="",
                quest_id=None,
                speaker=None,
                voice=None,
                duration=None,
                path=f"Books/{key}-page.mp3",
                files=[],
                pack="",
                text=entry.get("text"),
                title=entry.get("title"),
            )
        )
    return out


def library_lines(pack_lines: list[Line], texts: Texts) -> list[Line]:
    """The packs' rows, plus a text-only row for every known line they lack."""
    have = {line_key(line) for line in pack_lines}
    extra = [line for line in known_lines(texts) if line.id not in have]
    return sorted([*pack_lines, *extra], key=lambda line: natural(line.id))
