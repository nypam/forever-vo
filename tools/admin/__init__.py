"""Pack browser: every line in the installed voice packs, filterable and playable.

    uv run --no-group tts --group admin fvo-admin            # http://127.0.0.1:8766
    uv run --no-group tts --group admin fvo-admin --open --compare <folder>

Reads the ForeverVO_Data* packs from --addons, else AUDITION_ADDONS, else the
client's Interface/AddOns under WOW_DIR, and never writes anything. A line plays
the way the addon plays it (a line with parts, part by part). --compare (or
FVO_COMPARE) names a folder laid out like a pack's Sounds/; a line whose file is
there too gets a second play button, so two pipelines can be heard side by
side. Quest text comes from tools/data/capture.json and, once fvo-classicdb has
run, Classic's tools/data/bulk/classic.json.

No GPU stack: this never imports tools.generate or tools.audition.
"""

from __future__ import annotations

import argparse
import dataclasses
import os
import re
import sys
import threading
import webbrowser
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse

from tools.admin import blizzard
from tools.admin.catalog import Catalog, filters_from_query, whole
from tools.admin.dashboard import summary
from tools.admin.library import library_lines
from tools.admin.lines import Line, as_int, merge
from tools.admin.packs import find_packs, read_tables
from tools.admin.pages import (
    Clip,
    audio_urls,
    compare_url,
    dashboard_page,
    lines_page,
    npc_page,
    voice_page,
    voices_page,
)
from tools.admin.people import Npc, VoiceInfo, npcs_of, voice_info, voices_in_use
from tools.admin.render import esc
from tools.admin.texts import Texts, annotate, load_texts, npc_names_of
from tools.config import BETA_BUILD, BETA_DIR, DATA_DIR, Config, load_config

ADDONS_DIR = BETA_DIR / "Interface" / "AddOns"
SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9._-]+$")
VOICE_NAME = re.compile(r"^[A-Za-z0-9._-]+$")


def addons_from_env() -> Path:
    override = os.environ.get("AUDITION_ADDONS")
    return Path(override) if override else ADDONS_DIR


def build_catalog(
    addons: Path | None, compare_dir: Path | None, data_dir: Path = DATA_DIR
) -> Catalog:
    packs = find_packs(addons)
    texts = load_texts(data_dir)
    lines = library_lines(merge(packs), texts)
    annotate(lines, texts, npc_names_of([read_tables(pack) for pack in packs]))
    catalog = Catalog(lines, packs, compare_dir, addons, texts.has_classic)
    catalog.texts = texts
    return catalog


def safe_file(root: Path, path: str) -> Path:
    """`root/path` for an MP3 path made of plain segments that stays inside
    `root`; a 404 for anything else."""
    segments = path.split("/")
    if not path.endswith(".mp3") or any(
        not SAFE_SEGMENT.match(s) or s in (".", "..") for s in segments
    ):
        raise HTTPException(404)
    file = (root / Path(*segments)).resolve()
    if not file.is_relative_to(root.resolve()) or not file.is_file():
        raise HTTPException(404)
    return file


def notices(catalog: Catalog) -> list[str]:
    """What the dashboard says is missing, as HTML."""
    out = []
    if not catalog.packs:
        out.append(
            f"No voice packs found in <code>{esc(catalog.addons or '(none)')}</code>. Set "
            "<code>WOW_DIR</code> to the folder holding <code>_classic_beta_</code>, or start "
            "with <code>--addons &lt;Interface/AddOns&gt;</code>."
        )
    if not catalog.has_classic:
        out.append(
            "Classic quests show no text, level or display until you run "
            "<code>uv run --no-group tts fvo-classicdb</code> (it writes "
            "<code>tools/data/bulk/classic.json</code>), then restart."
        )
    return out


def npc_soundboard(
    npc: Npc, infos: dict[str, VoiceInfo | None]
) -> tuple[str, list[Clip]]:
    """The Blizzard recordings an NPC page plays: its own NPCSounds set when its
    display is known, else the clips behind the voice it is cast with, labelled
    as that voice's. A model is never guessed into a set: one model is cast with
    many (the human male model with 15)."""
    set_id = blizzard.npc_sound_set(npc.display_id)
    if set_id:
        clips = [Clip(bark.fdid, bark.kit) for bark in blizzard.set_barks(set_id)]
        return f"Blizzard voice set {set_id}", clips
    for voice, _ in npc.voices.most_common():
        info = infos.get(voice)
        if info and info.pick:
            borrowed = (
                f" (borrowed from {info.borrowed_from})" if info.borrowed_from else ""
            )
            clips = [
                Clip(fdid, f"clip {i}", info.pick_build or "")
                for i, fdid in enumerate(info.pick, 1)
            ]
            return f"Blizzard clips behind {voice}{borrowed}", clips
    return "No Blizzard recordings known for this NPC.", []


def create_app(catalog: Catalog, config: Config | None = None) -> FastAPI:
    app = FastAPI(title="Forever Voiceover admin")
    config = config or load_config()
    packs = {pack.folder: pack for pack in catalog.packs}
    npcs = npcs_of(
        catalog.lines,
        catalog.texts or Texts(),
        [read_tables(pack) for pack in catalog.packs],
    )
    names = {key: npc.name for key, npc in npcs.items() if npc.name}
    in_use: dict[str, VoiceInfo] = {}
    for voice in voices_in_use(catalog.lines):
        info = voice_info(voice, config, catalog.lines)
        if info:
            in_use[voice] = info
    voices_html = voices_page(in_use, names)
    # A clip is fetched from the default build or one a pick names, nothing else:
    # the build is part of the cache path
    builds = {BETA_BUILD} | {
        source.build for source in config.voices.sources.values() if source.build
    }
    # The library does not change while the admin runs: count it once
    dashboard = dashboard_page(
        summary(catalog, len(npcs), len(voices_in_use(catalog.lines))),
        notices(catalog),
    )

    def row(line: Line) -> dict[str, Any]:
        return {
            **dataclasses.asdict(line),
            "urls": audio_urls(line),
            "compare_url": compare_url(catalog, line),
        }

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return dashboard

    @app.get("/lines", response_class=HTMLResponse)
    def lines_html(request: Request) -> str:
        return lines_page(catalog, request.url.query)

    @app.get("/npc/{key}", response_class=HTMLResponse)
    def npc(key: str) -> str:
        speaker = as_int(key)
        if speaker is None or speaker not in npcs:
            raise HTTPException(404)
        found = npcs[speaker]
        infos: dict[str, VoiceInfo | None] = {v: in_use.get(v) for v in found.voices}
        title, clips = npc_soundboard(found, infos)
        return npc_page(catalog, found, infos, title, clips)

    @app.get("/voice/{name}", response_class=HTMLResponse)
    def voice(name: str) -> str:
        info = (
            in_use.get(name) or voice_info(name, config, catalog.lines)
            if VOICE_NAME.match(name)
            else None
        )
        if info is None:
            raise HTTPException(404)
        return voice_page(catalog, info, names)

    @app.get("/voices", response_class=HTMLResponse)
    def voices() -> str:
        return voices_html

    @app.get("/clip/{fdid}.ogg")
    def clip(fdid: str, build: str = "") -> FileResponse:
        number = as_int(fdid)
        if number is None or number < 0 or (build and build not in builds):
            raise HTTPException(404)
        try:
            path = blizzard.clip_file(number, build or None)
        except blizzard.ClipUnavailable as error:
            raise HTTPException(404) from error
        return FileResponse(path, media_type="audio/ogg")

    @app.get("/api/facets")
    def facets() -> dict[str, Any]:
        return catalog.facets()

    @app.get("/api/lines")
    def lines(request: Request) -> dict[str, Any]:
        query = request.url.query
        given = {k: v[-1] for k, v in parse_qs(query).items()}
        total, page_rows = catalog.query(
            filters_from_query(query),
            offset=whole(given.get("offset", "")) or 0,
            limit=whole(given.get("limit", "")) or 100,
        )
        return {"total": total, "rows": [row(line) for line in page_rows]}

    @app.get("/api/audio/pack/{pack}/{path:path}")
    def pack_audio(pack: str, path: str) -> FileResponse:
        if pack not in packs:
            raise HTTPException(404)
        return FileResponse(
            safe_file(packs[pack].root / "Sounds", path), media_type="audio/mpeg"
        )

    @app.get("/api/audio/compare/{path:path}")
    def compare_audio(path: str) -> FileResponse:
        if catalog.compare_dir is None:
            raise HTTPException(404)
        return FileResponse(
            safe_file(catalog.compare_dir, path), media_type="audio/mpeg"
        )

    return app


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument(
        "--addons",
        type=Path,
        default=addons_from_env(),
        help="directory of ForeverVO_Data* packs "
        "(default: AUDITION_ADDONS, else the client's AddOns from WOW_DIR)",
    )
    parser.add_argument(
        "--compare",
        type=Path,
        default=Path(os.environ["FVO_COMPARE"])
        if os.environ.get("FVO_COMPARE")
        else None,
        help="a folder laid out like a pack's Sounds/ whose takes play beside the "
        "pack's (default: FVO_COMPARE)",
    )
    parser.add_argument(
        "--open", action="store_true", help="open the page in the browser"
    )
    args = parser.parse_args(argv)

    import uvicorn

    catalog = build_catalog(args.addons, args.compare)
    facets = catalog.facets()
    print(
        f"fvo-admin: {facets['packs_found']} packs in {args.addons}, "
        f"{facets['totals']['lines']} lines"
        + (
            f", {facets['totals']['with_compare']} with a take in {args.compare}"
            if args.compare
            else ""
        )
    )
    if not facets["packs_found"]:
        print("fvo-admin: no packs there; set WOW_DIR or pass --addons")
    if not facets["has_classic"]:
        print(
            "fvo-admin: no tools/data/bulk/classic.json, so Classic quests show no "
            "text; run `uv run --no-group tts fvo-classicdb`"
        )
    url = f"http://{args.host}:{args.port}"
    print(f"fvo-admin: {url}")
    if args.open:
        threading.Timer(1.0, webbrowser.open, [url]).start()
    uvicorn.run(
        create_app(catalog), host=args.host, port=args.port, log_level="warning"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
