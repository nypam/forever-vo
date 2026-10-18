"""Who speaks and in which voice: NPCs and voices, from the lines and the config.

A voice is forever-vo's name for a reference clip and its Chatterbox settings
(`human-male-official`, `narrator`); many NPCs share one. Everything about a
voice here is read from configs/ as configured. What generate.VoiceCatalog
resolves at generation time (which clip wins, whose settings a borrowed clip
brings) depends on reference wavs that are not in git, so it is not repeated.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from tools.admin.lines import Line, as_int, items, line_key, voiced
from tools.admin.texts import Texts
from tools.config import Config
from tools.wowdata import base_voice, is_archetype

SETTINGS = ("exaggeration", "cfg_weight", "tempo", "pitch", "speed")


@dataclass
class Npc:
    key: int  # speaker key; negative for game objects
    name: str | None = None
    sexes: str = ""
    display_id: int | None = None
    model_file_id: int | None = None
    is_object: bool = False
    zones: list[str] = field(default_factory=list)
    voices: Counter[str] = field(default_factory=Counter)  # voice -> voiced rows
    lines: int = 0  # distinct lines spoken, voiced or not


@dataclass
class VoiceInfo:
    name: str
    tuning: dict[str, Any] | None  # its own [tts.voices.<name>] row, set fields only
    defaults: dict[str, Any]  # the [tts] defaults
    fallbacks: list[str]  # where a voice without a clip of its own borrows one
    pick: list[int]  # clip FileDataIDs of the pick in use, own or borrowed
    pick_build: str | None
    borrowed_from: str | None  # the voice whose pick is shown, when not this one
    pinned_speakers: list[str]  # [voices.speakers] keys pinned to this voice
    speakers: Counter[int]  # speaker -> voiced rows in this voice
    rows: int  # voiced rows in this voice


def integer(value: Any) -> int | None:
    return as_int(value)


def npcs_of(
    lines: list[Line], texts: Texts, tables_by_pack: list[dict[str, Any]]
) -> dict[int, Npc]:
    """One Npc per speaker on any row. Pack tables win over the sources, earlier
    packs over later ones, as the addon reads them."""
    npcs: dict[int, Npc] = {}
    spoken: dict[int, set[str]] = {}
    zones: dict[int, Counter[str]] = {}
    for line in lines:
        if line.speaker is None:
            continue
        npc = npcs.setdefault(line.speaker, Npc(line.speaker))
        spoken.setdefault(line.speaker, set()).add(line_key(line))
        if line.zone:
            zones.setdefault(line.speaker, Counter())[line.zone] += 1
        if line.voice and voiced(line):
            npc.voices[line.voice] += 1
    for key, npc in npcs.items():
        npc.lines = len(spoken.get(key, ()))
        npc.zones = [zone for zone, _ in (zones.get(key) or Counter()).most_common()]
        record = texts.npcs.get(str(key)) or {}
        npc.is_object = key < 0 or bool(record.get("isObject"))
        npc.display_id = integer(record.get("displayID"))
        npc.model_file_id = integer(record.get("modelFileID"))
        name = record.get("name")
        npc.name = (
            name if isinstance(name, str) and name and name != "Unknown" else None
        )
        sexes = record.get("sexes")
        npc.sexes = sexes if isinstance(sexes, str) else ""
    for tables in reversed(tables_by_pack):  # earlier packs win: applied last
        for key, name in items(tables.get("npcs")):
            if key in npcs and isinstance(name, str) and name:
                npcs[key].name = name
        for key, sexes in items(tables.get("sexes")):
            if key in npcs and isinstance(sexes, str):
                npcs[key].sexes = sexes
        for key, model in items(tables.get("models")):
            if key in npcs and integer(model):
                npcs[key].model_file_id = integer(model)
    return npcs


def voices_in_use(lines: list[Line]) -> Counter[str]:
    return Counter(line.voice for line in lines if line.voice and voiced(line))


def fallback_chain(name: str, fallbacks: dict[str, str]) -> list[str]:
    """Where `name` borrows a clip when it has none: an archetype's base voice
    (human-male-official -> human-male), then [voices.fallbacks] by race
    (felorc -> orc), keeping the sex. Stops at a voice it has seen."""
    chain: list[str] = []
    seen = {name}
    current = name
    if is_archetype(name):
        current = base_voice(name)
        chain.append(current)
        seen.add(current)
    while True:
        race, _, rest = current.partition("-")
        gender = rest.split("-")[0] if rest else ""
        fallback = fallbacks.get(race)
        if not fallback:
            return chain
        candidate = (
            fallback if "-" in fallback or not gender else f"{fallback}-{gender}"
        )
        if candidate in seen:
            return chain
        chain.append(candidate)
        seen.add(candidate)
        current = candidate


def fallback_voice(name: str, fallbacks: dict[str, str]) -> bool:
    """A voice nothing uses yet but generation could cast: <race>-<male|female>,
    optionally with an archetype, for a race that borrows another's clip."""
    parts = name.split("-")
    return len(parts) >= 2 and parts[0] in fallbacks and parts[1] in ("male", "female")


def voice_info(name: str, config: Config, lines: list[Line]) -> VoiceInfo | None:
    """Everything the config says about a voice, and who uses it; None for a
    name nothing uses and the config does not know."""
    voices = config.voices
    tts = config.tts
    speakers: Counter[int] = Counter(
        line.speaker
        for line in lines
        if line.voice == name and voiced(line) and line.speaker is not None
    )
    rows = sum(1 for line in lines if line.voice == name and voiced(line))
    own_tuning = tts.voices.get(name)
    tuning = own_tuning.model_dump(exclude_none=True) if own_tuning else None
    pinned = sorted(key for key, voice in voices.speakers.items() if voice == name)
    chain = fallback_chain(name, voices.fallbacks)
    known = rows or tuning or name in voices.sources or pinned
    if not known and not fallback_voice(name, voices.fallbacks):
        return None
    source, borrowed_from = voices.sources.get(name), None
    if source is None:
        for candidate in chain:
            if candidate in voices.sources:
                source, borrowed_from = voices.sources[candidate], candidate
                break
    return VoiceInfo(
        name=name,
        tuning=tuning,
        defaults={setting: getattr(tts, setting) for setting in SETTINGS},
        fallbacks=chain,
        pick=list(source.clips) if source else [],
        pick_build=source.build if source else None,
        borrowed_from=borrowed_from,
        pinned_speakers=pinned,
        speakers=speakers,
        rows=rows,
    )
