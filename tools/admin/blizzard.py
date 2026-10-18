"""Blizzard's own recordings behind a voice: an NPCSounds set's barks, and any
clip by FileDataID, fetched from wago.tools through tools.wowdata.

Every humanoid display is cast with an NPCSounds set, whose four sound kits are
its greeting, farewell and annoyed barks (and a rarely used fourth). Clips are
fetched on demand, never while a page renders, and cached under
tools/voices/raw/admin/<build>/ (wowdata also keeps its own copy in
tools/data/casc/). Offline, or for a clip this build lacks, nothing raises past
this module: barks are an empty list and a clip is ClipUnavailable.
"""

from __future__ import annotations

import functools
from dataclasses import dataclass
from pathlib import Path

import requests

from tools.config import BETA_BUILD, VOICES_DIR
from tools.wowdata import display_sound_set, fetch_file, is_dud, load_db2

KITS = ("greeting", "farewell", "annoyed", "other")  # NPCSounds.SoundID_0..3
# What wago and its cached tables raise: network trouble, a missing or partial
# file, a malformed row
WAGO_ERRORS = (requests.RequestException, OSError, ValueError, KeyError)


@dataclass(frozen=True)
class Bark:
    fdid: int
    kit: str


class ClipUnavailable(Exception):
    """wago could not give this clip: offline, not in the build, or a dud file."""


def npc_sound_set(display_id: int | None) -> int | None:
    """The NPCSounds set a creature display is cast with, or None."""
    if not display_id:
        return None
    try:
        return display_sound_set(display_id)
    except WAGO_ERRORS:  # no set rather than no page
        return None


@functools.cache
def kit_files() -> dict[str, tuple[int, ...]]:
    """SoundKitID -> its FileDataIDs, in table order."""
    kits: dict[str, list[int]] = {}
    for row in load_db2("SoundKitEntry").values():
        kits.setdefault(row["SoundKitID"], []).append(int(row["FileDataID"]))
    return {kit: tuple(files) for kit, files in kits.items()}


def set_barks(set_id: int) -> list[Bark]:
    """Every bark of an NPCSounds set, greetings first and annoyed last."""
    try:
        row = load_db2("NPCSounds").get(set_id)
        files = kit_files() if row else {}
    except WAGO_ERRORS:
        return []
    if not row:
        return []
    barks = []
    for i, kit in enumerate(KITS):
        kit_id = row.get(f"SoundID_{i}") or "0"
        if kit_id != "0":
            barks += [Bark(fdid, kit) for fdid in files.get(kit_id, ())]
    return barks


def clip_file(fdid: int, build: str | None = None) -> Path:
    """The clip on disk, fetched from wago.tools the first time."""
    build = build or BETA_BUILD
    dest = VOICES_DIR / "raw" / "admin" / build / f"{fdid}.ogg"
    try:
        path = fetch_file(fdid, dest, build)
        if is_dud(path):
            raise ClipUnavailable(f"{fdid} is not audio in build {build}")
    except ClipUnavailable:
        raise
    except WAGO_ERRORS as error:
        raise ClipUnavailable(f"{fdid}: {error}") from error
    return path


@functools.cache
def model_displays() -> dict[int, int]:
    """Model file -> the lowest creature display that uses it."""
    models = {
        model_id: int(row.get("FileDataID") or 0)
        for model_id, row in load_db2("CreatureModelData").items()
    }
    displays: dict[int, int] = {}
    for display_id, row in sorted(load_db2("CreatureDisplayInfo").items()):
        model_file = models.get(int(row.get("ModelID") or 0))
        if model_file:
            displays.setdefault(model_file, display_id)
    return displays


def model_display(model_file_id: int | None) -> int | None:
    """A display of the same model, for a portrait only. Forever's own NPCs are
    captured with a model file and no display; a model is cast with many voice
    sets and skins, so this display names the picture, never the NPC's voice."""
    if not model_file_id:
        return None
    try:
        return model_displays().get(model_file_id)
    except WAGO_ERRORS:
        return None
