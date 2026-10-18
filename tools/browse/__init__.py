"""Pack browser: every line in the installed voice packs, filterable and playable.

    uv run --no-group tts --group browse fvo-browse            # http://127.0.0.1:8766
    uv run --no-group tts --group browse fvo-browse --open --compare <folder>

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
from importlib import resources
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse

from tools.browse.catalog import Catalog, Filters
from tools.browse.lines import Line, merge
from tools.browse.packs import find_packs, read_tables
from tools.browse.texts import annotate, load_texts, npc_names_of
from tools.config import BETA_DIR, DATA_DIR

ADDONS_DIR = BETA_DIR / "Interface" / "AddOns"
SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9._-]+$")


def addons_from_env() -> Path:
    override = os.environ.get("AUDITION_ADDONS")
    return Path(override) if override else ADDONS_DIR


def whole(value: str) -> int | None:
    """A number filter from the query string, leniently: "7", "7.0" and "1.5"
    read as whole numbers, and anything else ("abc", "") as no filter, so a
    bookmarked or half-typed URL never fails the request."""
    try:
        return int(float(value))
    except (ValueError, OverflowError):
        return None


def build_catalog(
    addons: Path | None, compare_dir: Path | None, data_dir: Path = DATA_DIR
) -> Catalog:
    packs = find_packs(addons)
    lines = merge(packs)
    texts = load_texts(data_dir)
    annotate(lines, texts, npc_names_of([read_tables(pack) for pack in packs]))
    return Catalog(lines, packs, compare_dir, addons, texts.has_classic)


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


def create_app(catalog: Catalog) -> FastAPI:
    app = FastAPI(title="Forever Voiceover pack browser")
    page = (resources.files(__package__) / "index.html").read_text(encoding="utf-8")
    packs = {pack.folder: pack for pack in catalog.packs}

    def row(line: Line) -> dict[str, Any]:
        compared = catalog.compare_path(line)
        return {
            **dataclasses.asdict(line),
            "urls": []
            if line.missing
            else [f"/api/audio/pack/{quote(line.pack)}/{quote(f)}" for f in line.files],
            "compare_url": f"/api/audio/compare/{quote(compared)}"
            if compared
            else None,
        }

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return page

    @app.get("/api/facets")
    def facets() -> dict[str, Any]:
        return catalog.facets()

    @app.get("/api/lines")
    def lines(
        kind: str = "",
        pack: str = "",
        voice: str = "",
        zone: str = "",
        level_min: str = "",
        level_max: str = "",
        quest: str = "",
        npc: str = "",
        q: str = "",
        compare: bool = False,
        offset: str = "",
        limit: str = "",
    ) -> dict[str, Any]:
        filters = Filters(
            kind=kind,
            pack=pack,
            voice=voice,
            zone=zone,
            level_min=whole(level_min),
            level_max=whole(level_max),
            quest_id=whole(quest),
            npc=npc,
            q=q,
            compare=compare,
        )
        total, page_rows = catalog.query(
            filters, offset=whole(offset) or 0, limit=whole(limit) or 100
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
        f"fvo-browse: {facets['packs_found']} packs in {args.addons}, "
        f"{facets['totals']['lines']} lines"
        + (
            f", {facets['totals']['with_compare']} with a take in {args.compare}"
            if args.compare
            else ""
        )
    )
    if not facets["packs_found"]:
        print("fvo-browse: no packs there; set WOW_DIR or pass --addons")
    if not facets["has_classic"]:
        print(
            "fvo-browse: no tools/data/bulk/classic.json, so Classic quests show no "
            "text; run `uv run --no-group tts fvo-classicdb`"
        )
    url = f"http://{args.host}:{args.port}"
    print(f"fvo-browse: {url}")
    if args.open:
        threading.Timer(1.0, webbrowser.open, [url]).start()
    uvicorn.run(
        create_app(catalog), host=args.host, port=args.port, log_level="warning"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
