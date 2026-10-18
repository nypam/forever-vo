# Pack Browser Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A local read-only web page (`fvo-browse`, port 8766) that lists every voiced line in the installed `ForeverVO_Data*` packs, with filters and playback the way the addon plays it, plus a second play button for a take from a comparison folder.

**Architecture:** At startup a new package, `tools/browse/`, reads each pack's `Data/*.lua` tables. They are parsed with a new `tools.luatable.parse_value`. The tables become `Line` rows, one per playable line, with variants and parts resolved. When several packs have the same row, the one the addon would play is kept. Rows are annotated with text, title, zone and level from `capture.json`, `bulk/*.json` and the optional VMaNGOS snapshot. They are held in a `Catalog` that filters, pages and pairs rows with the comparison folder. A FastAPI app serves the JSON and the MP3s, plus one `index.html` with no build step.

**Tech Stack:** Python 3.12 (uv), FastAPI + uvicorn (new `browse` dependency group), pytest + FastAPI TestClient, plain HTML/CSS/JS.

**Spec:** `docs/superpowers/specs/2026-10-18-pack-browser-design.md`

## Global Constraints

- Read only. Nothing under `Interface/AddOns`, `configs/` or `tools/data/` is ever written.
- `tools/browse` must never import `tools.generate` or `tools.audition`, directly or through another module, and nothing that pulls in torch or chatterbox.
- Runs on Windows and Linux: `uv run --no-group tts --group browse fvo-browse`.
- Dependencies: add the group `browse = ["fastapi", "uvicorn"]` under `[dependency-groups]` and the script `fvo-browse = "tools.browse:main"` under `[project.scripts]`. Do not touch `[project].dependencies` or `default-groups`. Run `uv lock` afterwards.
- Default host `127.0.0.1`, port `8766`.
- Packs: `--addons`, else `AUDITION_ADDONS`, else `tools.config.BETA_DIR / "Interface" / "AddOns"`. A pack is a `ForeverVO_Data*` folder that has `Sounds/`. Its name, version and priority come from `Data/Pack.lua`.
- Pack order, where the addon looks first: priority descending, then folder name ascending. The first pack that has a row wins.
- Comparison folder: `--compare`, else `FVO_COMPARE`. Its label is the folder's name.
- Style: ruff check and format clean; tests in `tests/test_browse.py`; read `CLAUDE.md` first.
- Commands: tests `uv run --no-group tts --group dev pytest tests/test_browse.py -v`; lint `uv run --no-group tts --group dev ruff check tools/browse tools/luatable.py tests/test_browse.py` and `uv run --no-group tts --group dev ruff format --check tools/browse tools/luatable.py tests/test_browse.py`.

## Review Focus

1. **A table that names a file the pack does not have.** The row is still listed, with `missing: true` and no play button, and the page doesn't crash. (Task 2, `test_missing_file_flagged`)
2. **No packs found** (WOW_DIR unset on Windows, wrong `--addons`). The page loads, `/api/facets` returns `packs_found: 0` and the addons path it looked in, and the page shows that path and the `WOW_DIR` / `--addons` hint. (Task 5, `test_no_packs_found`)
3. **Path traversal or unknown pack in an audio URL** (`..`, backslashes, a pack folder not in the list). The answer is 404, never a file outside the root. (Task 5, `test_audio_path_refused`)
4. **Older or odd table shapes:** `g = true` versus `g = "a"`, a missing `va`, a part list with no `n`, a narrator list given as a positional table. The row is built with blanks rather than raising. (Task 2, `test_tolerates_old_shapes`)
5. **A huge or negative `limit`/`offset`.** `limit` is clamped to 1..500, a negative `offset` is treated as 0, and an empty result is `{total: 0, rows: []}`. (Task 4, `test_paging_clamped`)

---

### Task 1: Read pack tables

**Files:**
- Modify: `tools/luatable.py` (add a public function after `parse_saved_variables`)
- Create: `tools/browse/packs.py`
- Create: `tools/browse/__init__.py` (a docstring only for now, so the package imports)
- Test: `tests/test_browse.py`

**Interfaces:**
- Produces:
  - `tools.luatable.parse_value(text: str) -> Any`: parses the first Lua value in `text` with the existing `_Parser`.
  - In `tools/browse/packs.py`:
    - `@dataclass(frozen=True) class Pack: folder: str; label: str; version: str; priority: int; root: Path` (`root` is the pack folder; sounds are under `root / "Sounds"`).
    - `find_packs(addons: Path | None) -> list[Pack]`, in pack order (see Global Constraints). Empty if `addons` is None or missing.
    - `read_tables(pack: Pack) -> dict[str, Any]`: every `pack.<field> = <value>` in `Data/Quests.lua`, `Gossip.lua`, `Books.lua`, `Narrator.lua` and `NPCs.lua`, merged into one dict keyed by field (`quests`, `gossip`, `books`, `narrator`, `narratorVoices`, `npcs`, `models`, `sexes`, `maps`). A missing file contributes nothing.
  - In `tests/test_browse.py`, a helper `make_pack(addons: Path, folder: str, *, priority: int = 100, version: str = "2026.10.18", tables: dict[str, str] | None = None, files: list[str] = ()) -> Path`. It writes `Data/Pack.lua` in the released format (`name = "…"`, `version = "…"`, `priority = N`, as in the installed packs), writes each `tables[filename]` (Lua source) to `Data/<filename>`, and creates each relative path in `files` as an empty file under `Sounds/`. Later tasks reuse it.

- [ ] **Step 1: Write the failing tests**

```python
def test_parse_value_reads_pack_assignment():
    assert parse_value('{ [2] = { a=16.6, va="narrator" }, [5] = { c=5.1 } }') == {
        2: {"a": 16.6, "va": "narrator"}, 5: {"c": 5.1}}

def test_find_packs_order(tmp_path):
    make_pack(tmp_path, "ForeverVO_Data_B", priority=100)
    make_pack(tmp_path, "ForeverVO_Data_A", priority=100)
    make_pack(tmp_path, "ForeverVO_Data_Old", priority=50)
    (tmp_path / "ForeverVO").mkdir()                       # the player addon, not a pack
    (tmp_path / "ForeverVO_Data_NoSounds" / "Data").mkdir(parents=True)
    assert [p.folder for p in find_packs(tmp_path)] == [
        "ForeverVO_Data_A", "ForeverVO_Data_B", "ForeverVO_Data_Old"]
    assert find_packs(None) == [] and find_packs(tmp_path / "nope") == []

def test_read_tables_merges_fields(tmp_path):
    root = make_pack(tmp_path, "ForeverVO_Data_X", tables={
        "Quests.lua": 'local pack = X\npack.quests = {\n\t[7] = { a=13.1, va="human-male-official", npc=197 },\n}\n',
        "Narrator.lua": 'local pack = X\npack.narratorVoices = { "skyborne-female" }\npack.narrator = {\n\t[2] = { [1]={ a=18.7 } },\n}\n'})
    t = read_tables(find_packs(tmp_path)[0])
    assert t["quests"][7]["npc"] == 197
    assert t["narrator"][2][1]["a"] == 18.7
    assert t["narratorVoices"] == ["skyborne-female"]       # positional tables parse as lists
    assert "gossip" not in t
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run --no-group tts --group dev pytest tests/test_browse.py -v`
Expected: FAIL with ImportError (`parse_value`, `tools.browse.packs`).

- [ ] **Step 3: Implement `parse_value`, `Pack`, `find_packs` and `read_tables`**

`read_tables` splits each file on lines matching `^pack\.(\w+)\s*=` and passes the text after each `=` to `parse_value`. The repo's `_TOKEN` drops the `.` in `pack.quests`, so the whole file cannot go through `parse_saved_variables`. `find_packs` reads `Pack.lua` with the same regex audition uses: `^\s*(name|priority|version)\s*=\s*"?([^",]+)"?` (MULTILINE). Copy it; do not import audition.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --no-group tts --group dev pytest tests/test_browse.py -v`
Expected: PASS

- [ ] **Step 5: Parse the real packs once (smoke check, no commit of output)**

Run: `uv run --no-group tts --group dev python -c "from pathlib import Path; from tools.browse.packs import find_packs, read_tables; ps = find_packs(Path(r'C:/Program Files (x86)/World of Warcraft/_classic_beta_/Interface/AddOns')); print([(p.folder, len(read_tables(p).get('quests', {})), len(read_tables(p).get('gossip', {}))) for p in ps])"`
Expected: 6 packs, with no exception. Classic Quests has thousands of quests and Classic Gossip thousands of speakers.

- [ ] **Step 6: Commit**

```bash
git add tools/luatable.py tools/browse/__init__.py tools/browse/packs.py tests/test_browse.py
git commit -m "Pack browser: read installed pack tables"
```

---

### Task 2: Turn tables into playable lines

**Files:**
- Create: `tools/browse/lines.py`
- Test: `tests/test_browse.py`

**Interfaces:**
- Consumes: `Pack`, `find_packs`, `read_tables` (Task 1).
- Produces:

```python
@dataclass
class Line:
    id: str                    # "q:<qid>:<event>[:<variant>]", "g:<speaker>:<hash>[:<variant>]", "b:<key>[:<variant>]"
    kind: str                  # "accept" | "progress" | "complete" | "gossip" | "book"
    variant: str               # "" | "male" | "female" | "sex f" | "sex m" | "speaker <key>" | "narrator <voice>"
    quest_id: int | None
    speaker: int | None        # creature id, negative for game objects; None for books and item-started quests
    voice: str | None
    duration: float | None     # the whole line's, or the sum of its parts
    path: str                  # whole-line file relative to Sounds/, e.g. "Quests/Sex/f/100-accept.mp3"; the comparison key
    files: list[str]           # what plays, in order, relative to Sounds/
    pack: str                  # Pack.folder
    missing: bool = False      # some entry of `files` is not on disk
    text: str | None = None    # filled by Task 3 for quests; set here for gossip (entry t) and books (entry s, else t)
    title: str | None = None   # filled by Task 3; books set it here from entry b
    zone: str | None = None
    level: int | None = None
    speaker_name: str | None = None
```

  - `lines_of(pack: Pack, tables: dict[str, Any]) -> list[Line]`
  - `merge(packs: list[Pack]) -> list[Line]`: calls `read_tables` and `lines_of` for each pack in order, keeps the first row per `id`, and returns rows sorted by `id`.

**The rules** (from `ForeverVO/Core/Packs.lua`, the authority; `prefix` is `m-`/`f-` for a gendered row, else empty; `<e>` is the event, and `x` is its letter `a`/`p`/`c`):
- Quest event: present when key `x` is in the entry. Speaker: `npc` for accept; `ender` if present, else `npc`, for progress and complete. Voice: `v<x>`.
- Gendered: `g is True`, or `g` is a string containing `x`. Then there are two rows (`male`, `female`) with the prefix and no plain row.
- Whole-line path: `Quests/<prefix><qid>-<e>.mp3`. Parts `<x>P` (a list): files `Quests/<prefix><qid>-p<i>-<e>.mp3` for i = 1..n, which replace the whole file in `files`; the duration is the sum of the parts' `d`.
- Other sex `s<x> = {m|f: d}`: row `sex <m|f>`, path and file `Quests/Sex/<m|f>/<prefix><qid>-<e>.mp3`, never parts.
- Other speakers `x<x> = {key: record|true|false}`: only a dict record makes a row, `speaker <key>`, with path and file `Quests/Speaker/<key>/<qid>-<e>.mp3`, voice `record["v"]` and speaker `key`.
- Narrator alternates: `narratorVoices[i]` names voice i (1-based, list or dict). `narrator[qid][i]` with key `x` gives row `narrator <voice>`, path `Quests/Narrator/<voice>/<prefix><qid>-<e>.mp3`, voice `<voice>`. When the base event has parts, the files are the base parts, except that each narrator part (`n` true) whose index is in `narrator[qid][i][<x>P]` plays from `Quests/Narrator/<voice>/<prefix><qid>-p<i>-<e>.mp3`.
- Gossip entry `{f, h, t, d, v, g, n, s, P, nP}` under speaker key `k`: path `Gossip/<prefix><f>.mp3`. The parts files are `Gossip/<prefix><k>-p<i>-<h>.mp3`; `g` true gives male and female rows. `s = {m|f: d}` gives `Gossip/Sex/<m|f>/<prefix><f>.mp3`. `n = {i: d}` gives `Gossip/Narrator/<voice>/<prefix><f>.mp3`, with `nP[i]` as for quests (`Gossip/Narrator/<voice>/<prefix><k>-p<j>-<h>.mp3`).
- Book `books[key] = {d, t, s, b, p, x, g, n}`: path `Books/<prefix><key>-page.mp3`, voice `"narrator"`; `g` true gives male and female rows, as gossip does; `n` gives `Books/Narrator/<voice>/<prefix><key>-page.mp3`.
- A table written as a mapping where a list is expected (`{ [1]=… }`), or the other way round, is read either way: index from 1, and skip non-table items.
- `missing` is True when any file in `files` does not exist under `pack.root / "Sounds"`. Use one `os.walk` of the pack's Sounds into a set, not a stat per file. `files` must never be empty: a row with no parts lists its whole-line path even when that file is missing.

- [ ] **Step 1: Write the failing tests** (use `make_pack` with tables and files built for each case)

```python
def test_quest_events_and_speakers(tmp_path):      # [7] = { a=13.1, va="v1", npc=197, c=13.6, vc="v2", ender=250 }
    rows = {r.id: r for r in merge(find_packs(tmp_path))}
    assert rows["q:7:accept"].speaker == 197 and rows["q:7:accept"].files == ["Quests/7-accept.mp3"]
    assert rows["q:7:complete"].speaker == 250 and rows["q:7:complete"].voice == "v2"
    assert "q:7:progress" not in rows

def test_parts_play_in_order(tmp_path):            # cP = { { d=1.1 }, { d=1.4, n=true }, { d=0.6 } }, no whole file on disk
    r = {r.id: r for r in merge(find_packs(tmp_path))}["q:9:complete"]
    assert r.files == ["Quests/9-p1-complete.mp3", "Quests/9-p2-complete.mp3", "Quests/9-p3-complete.mp3"]
    assert r.path == "Quests/9-complete.mp3" and r.duration == pytest.approx(3.1) and not r.missing

def test_gendered_rows_replace_plain(tmp_path):    # g="a": accept gendered, complete plain
    ids = {r.id for r in merge(find_packs(tmp_path))}
    assert {"q:5:accept:male", "q:5:accept:female", "q:5:complete"} <= ids and "q:5:accept" not in ids

def test_variants(tmp_path):                       # sa={f=2.1}, xc={[1234]={d=2.0,v="human-female"}, [99]=true}, narrator[5][1].a
    rows = {r.id: r for r in merge(find_packs(tmp_path))}
    assert rows["q:5:accept:sex f"].files == ["Quests/Sex/f/5-accept.mp3"]
    assert rows["q:5:complete:speaker 1234"].voice == "human-female"
    assert "q:5:complete:speaker 99" not in rows
    assert rows["q:5:accept:narrator skyborne-female"].path == "Quests/Narrator/skyborne-female/5-accept.mp3"

def test_narrator_parts_swap(tmp_path):            # aP={ {d=1}, {d=2,n=true} }, narrator[3][1] = { a=3.1, aP={ [2]=2.2 } }
    r = {r.id: r for r in merge(find_packs(tmp_path))}["q:3:accept:narrator skyborne-female"]
    assert r.files == ["Quests/3-p1-accept.mp3", "Quests/Narrator/skyborne-female/3-p2-accept.mp3"]

def test_gossip_and_books(tmp_path):               # gossip [68] = { { f="68-0135d8e6", h="0135d8e6", t="Nothing like…", d=12.9, v="human-male-official", s={f=13.0} } }; books["003512ce"] = { d=34.8, t="raw", s="prose", b="A Letter" }
    rows = {r.id: r for r in merge(find_packs(tmp_path))}
    g = rows["g:68:0135d8e6"]
    assert g.text.startswith("Nothing like") and g.path == "Gossip/68-0135d8e6.mp3" and g.speaker == 68
    assert rows["g:68:0135d8e6:sex f"].files == ["Gossip/Sex/f/68-0135d8e6.mp3"]
    b = rows["b:003512ce"]
    assert b.text == "prose" and b.title == "A Letter" and b.files == ["Books/003512ce-page.mp3"]

def test_priority_wins(tmp_path):                  # same q:7 in priority 100 and 50 packs
    assert {r.id: r for r in merge(find_packs(tmp_path))}["q:7:accept"].pack == "ForeverVO_Data_New"

def test_missing_file_flagged(tmp_path):           # table has a=, no file on disk
    r = {r.id: r for r in merge(find_packs(tmp_path))}["q:8:accept"]
    assert r.missing and r.files == ["Quests/8-accept.mp3"]

def test_tolerates_old_shapes(tmp_path):           # g=true, no va, part without n, narratorVoices as { [1]="x" }
    rows = merge(find_packs(tmp_path))
    assert any(r.id == "q:4:accept:male" and r.voice is None for r in rows)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run --no-group tts --group dev pytest tests/test_browse.py -v -k "quest or parts or gendered or variants or narrator or gossip or priority or missing or tolerates"`
Expected: FAIL with ImportError on `tools.browse.lines`.

- [ ] **Step 3: Implement `Line`, `lines_of` and `merge` in `tools/browse/lines.py`, following the rules above**

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --no-group tts --group dev pytest tests/test_browse.py -v`
Expected: PASS

- [ ] **Step 5: Count the real packs (smoke check)**

Run: `uv run --no-group tts --group dev python -c "from pathlib import Path; from collections import Counter; from tools.browse.packs import find_packs; from tools.browse.lines import merge; rs = merge(find_packs(Path(r'C:/Program Files (x86)/World of Warcraft/_classic_beta_/Interface/AddOns'))); print(len(rs), Counter(r.kind for r in rs), sum(r.missing for r in rs))"`
Expected: tens of thousands of rows across all five kinds, with very few `missing` (each one worth a look). On disk, `sum(len(r.files) for r in rs)` should come close to the 24,103 MP3s, because parts count as files.

- [ ] **Step 6: Commit**

```bash
git add tools/browse/lines.py tests/test_browse.py
git commit -m "Pack browser: lines, parts and variants from the pack tables"
```

---

### Task 3: Text, titles, zones and levels

**Files:**
- Create: `tools/browse/texts.py`
- Test: `tests/test_browse.py`

**Interfaces:**
- Consumes: `Line` (Task 2), `tools.config.DATA_DIR`, `tools.config.CAPTURE_JSON` (`tools.config` is safe to import).
- Produces:
  - `@dataclass class Texts: quests: dict[str, dict]; gossip: dict[str, dict]; npcs: dict[str, dict]; has_classic: bool; zones: dict[int, str]`
  - `load_texts(data_dir: Path = DATA_DIR) -> Texts`: merges `data_dir/"bulk"/*.json` (`classic` first, then the other names in sorted order) and `data_dir/"capture.json"`, with capture last. Within each of `quests`, `gossip` and `npcs`, the merge goes field by field: a later non-empty value replaces an earlier one, and `None` or `""` never does. That is the rule in `generate.load_sources`; re-implement it here, never import it. `has_classic` is True when `bulk/classic.json` exists. `zones` is `snapshot_zones(...)` on the first `data_dir.glob("classicdb/**/mangos.sqlite")`, else `{}`.
  - `snapshot_zones(db_path: Path) -> dict[int, str]`: opens the file read-only (`sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)`), reads `quest_template(entry, ZoneOrSort)` and keeps `ZoneOrSort > 0`. Names come from `area_template(entry, name)` when that table exists, else `f"zone {id}"`. If the first snapshot shows the columns are named differently, adjust the query to them and keep the test's fixture in step.
  - `annotate(lines: list[Line], texts: Texts, npc_names: dict[int, str]) -> None`, in place:
    - Quest rows: `text` = `texts.quests[f"{qid}-{kind}"]["text"]`. `title`, `level` and `zone` come from the first of the accept, progress and complete entries that has each one.
    - Quest `zone` falls back to `texts.zones[qid]`.
    - Gossip `zone` comes from `texts.gossip` entries whose `npc` equals the row's speaker.
    - `speaker_name` = `npc_names[speaker]`, else `texts.npcs[str(speaker)]["name"]`, else a source entry's `name`. Skip `"Unknown"`.
  - `npc_names_of(tables_by_pack: list[dict[str, Any]]) -> dict[int, str]`: the `npcs` field of each pack's tables, earlier packs winning.

- [ ] **Step 1: Write the failing tests**

```python
def test_capture_beats_classic(tmp_path):     # bulk/classic.json quests["7-accept"]={"text":"old","title":"T","level":5}; capture.json quests["7-accept"]={"text":"new","title":None,"zone":"Elwynn Forest"}
    t = load_texts(tmp_path)
    assert t.quests["7-accept"] == {"text": "new", "title": "T", "level": 5, "zone": "Elwynn Forest"} and t.has_classic

def test_annotate_quest_and_gossip(tmp_path): # quest 7 rows, gossip row for speaker 68 with capture gossip {"68|0135d8e6": {"npc": "68", "zone": "Stormwind City", "name": "Thomas"}}
    annotate(rows, load_texts(tmp_path), {197: "Marshal McBride"})
    assert q7_complete.title == "T" and q7_accept.speaker_name == "Marshal McBride"
    assert gossip68.zone == "Stormwind City" and gossip68.speaker_name == "Thomas"

def test_snapshot_zones(tmp_path):            # sqlite with quest_template(entry,ZoneOrSort)=(7,12),(8,-1) and area_template(entry,name)=(12,"Elwynn Forest")
    assert snapshot_zones(db) == {7: "Elwynn Forest"}

def test_no_sources(tmp_path):
    t = load_texts(tmp_path)
    assert t.quests == {} and not t.has_classic and t.zones == {}
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run --no-group tts --group dev pytest tests/test_browse.py -v -k "capture or annotate or snapshot or no_sources"`
Expected: FAIL with ImportError on `tools.browse.texts`.

- [ ] **Step 3: Implement `Texts`, `load_texts`, `snapshot_zones`, `annotate` and `npc_names_of`**

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --no-group tts --group dev pytest tests/test_browse.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tools/browse/texts.py tests/test_browse.py
git commit -m "Pack browser: text, titles, zones and levels from capture and Classic"
```

---

### Task 4: Catalog: filters, facets, paging, comparison pairs

**Files:**
- Create: `tools/browse/catalog.py`
- Test: `tests/test_browse.py`

**Interfaces:**
- Consumes: `Line` (Task 2), `Pack` (Task 1).
- Produces:

```python
@dataclass
class Filters:
    kind: str = ""; pack: str = ""; voice: str = ""
    zone: str = ""             # "" any, "unknown" = no zone, else exact
    level_min: int | None = None; level_max: int | None = None   # a line with no level never matches a level bound
    quest_id: int | None = None
    npc: str = ""              # all digits (optionally a leading "-"): speaker == int; else a case-insensitive substring of speaker_name
    q: str = ""                # every word, case-insensitive, appears in text or title
    compare: bool = False      # only rows with a comparison take

class Catalog:
    def __init__(self, lines: list[Line], packs: list[Pack], compare_dir: Path | None, addons: Path | None, has_classic: bool) -> None
    def compare_path(self, line: Line) -> str | None
    def query(self, f: Filters, offset: int = 0, limit: int = 100) -> tuple[int, list[Line]]
    def facets(self) -> dict[str, Any]
```

  - `compare_path`: `line.path` if that file exists in the comparison folder. Otherwise, for a `male`/`female` row, the same path with the `m-`/`f-` prefix taken off the file name. Otherwise None. The comparison folder is walked once in `__init__` into a set of `/`-joined relative paths; a change in it needs a restart. With no folder, it is always None.
  - `query`: the matching rows in their sorted order. `limit` is clamped to 1..500 and a negative `offset` becomes 0. Returns `(total_matching, page)`.
  - `facets()`: `{"totals": {"lines": int, "with_compare": int}, "kinds": [{"value", "count"}], "packs": [{"value": folder, "label", "version", "count"}], "voices": [...], "zones": [... plus {"value": "unknown", "count"} when any row lacks a zone], "has_classic": bool, "compare_label": str | None, "addons": str | None, "packs_found": int}`. Value lists are sorted by count descending, then value.

- [ ] **Step 1: Write the failing tests** (build `Line` objects directly; a `tmp_path` comparison folder with a few files)

```python
def test_filters_combine(): ...       # kind+voice+zone, zone="unknown", level range drops level None, npc "197" vs "mcbride", q "crystal lake" needs both words
def test_compare_pairing(tmp_path):   # compare has Quests/7-accept.mp3 and Quests/5-accept.mp3
    c = Catalog(rows, [], tmp_path, None, True)
    assert c.compare_path(q7_accept) == "Quests/7-accept.mp3"
    assert c.compare_path(q5_accept_male) == "Quests/5-accept.mp3"      # plain pairs with both gendered rows
    assert c.compare_path(q7_complete) is None
    assert c.facets()["totals"]["with_compare"] == 3 and c.facets()["compare_label"] == tmp_path.name
    assert c.query(Filters(compare=True))[0] == 3
def test_gendered_compare_prefers_own(tmp_path):  # compare has both Quests/m-5-accept.mp3 and Quests/5-accept.mp3
    assert c.compare_path(q5_accept_male) == "Quests/m-5-accept.mp3"
def test_paging_clamped():
    assert c.query(Filters(), offset=-5, limit=10_000)[1] == rows[:500]
    assert c.query(Filters(), offset=0, limit=0)[1] == rows[:1]
    assert c.query(Filters(kind="nope")) == (0, [])
def test_facets_counts(): ...         # kinds and voices counted, "unknown" zone present
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run --no-group tts --group dev pytest tests/test_browse.py -v -k "filters or compare or paging or facets"`
Expected: FAIL with ImportError on `tools.browse.catalog`.

- [ ] **Step 3: Implement `Filters` and `Catalog`**

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --no-group tts --group dev pytest tests/test_browse.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tools/browse/catalog.py tests/test_browse.py
git commit -m "Pack browser: catalog with filters, facets and comparison pairs"
```

---

### Task 5: The app, the page, and the command

**Files:**
- Modify: `tools/browse/__init__.py` (module docstring as usage, like audition's; `create_app`, `build_catalog`, `main`)
- Create: `tools/browse/index.html`
- Modify: `pyproject.toml` (the `browse` group and the `fvo-browse` script, see Global Constraints), `uv.lock` (`uv lock`)
- Modify: `README.md`: a "Browsing the voice packs" subsection under Development, giving the command, `WOW_DIR` on Windows (`$env:WOW_DIR = "C:\Program Files (x86)\World of Warcraft"`), `--compare`, the comparison folder's layout, and running `fvo-classicdb` for the Classic text.
- Test: `tests/test_browse.py`

**Interfaces:**
- Consumes: everything above.
- Produces:
  - `build_catalog(addons: Path | None, compare_dir: Path | None, data_dir: Path = DATA_DIR) -> Catalog`: `find_packs`, then `merge`, then `annotate` with `load_texts(data_dir)` and the packs' npc names.
  - `create_app(catalog: Catalog) -> FastAPI` with these routes:
    - `GET /` serves `index.html`, read with `importlib.resources` as audition does.
    - `GET /api/facets` returns `catalog.facets()`.
    - `GET /api/lines` takes the `Filters` fields as query parameters (`quest` maps to `quest_id`, `compare=1`) plus `offset` and `limit`. It returns `{"total": int, "rows": [row]}`. Each row has the `Line` fields plus `"urls": ["/api/audio/pack/<pack>/<file>", …]` (empty when `missing`) and `"compare_url": "/api/audio/compare/<path>" | None`.
    - `GET /api/audio/pack/{pack}/{path:path}`: `pack` must be a known `Pack.folder`. Every `/`-separated segment of `path` must match `^[A-Za-z0-9._-]+$`, must not be `..`, and must end with `.mp3`. The resolved file must sit inside `pack.root / "Sounds"`. Anything else is a 404. It serves a `FileResponse` with `audio/mpeg`.
    - `GET /api/audio/compare/{path:path}`: the same checks against the comparison folder, and a 404 when no folder is set.
  - `main(argv: list[str] | None = None) -> int` takes the argparse options `--addons`, `--compare`, `--host` (127.0.0.1), `--port` (8766) and `--open` (opens the browser). It prints the packs found and the line counts, then runs `uvicorn.run(create_app(...), host=…, port=…)`. Import uvicorn inside `main` so the tests need only fastapi.

**The page (`index.html`):** keep audition's look (plain CSS and system fonts are fine).

- **Top:** the totals line. When `packs_found` is 0, a notice shows the `addons` path and says to set `WOW_DIR` or use `--addons`. When `has_classic` is false, a notice says to run `uv run --no-group tts fvo-classicdb` for the Classic text.
- **Filter bar:** selects for kind, pack, voice and zone, filled from `/api/facets` with their counts; inputs for level min and max, quest id, NPC and words; a "with comparison" checkbox that only shows when `compare_label` is set. The filters live in `location.search`, so reloading or bookmarking keeps the view. Changes are debounced by 250 ms.
- **Table**, with 100 rows per page and prev/next buttons. Columns:
  - kind (with the variant)
  - quest `id · title` or NPC `name (id)`
  - zone
  - text (two lines, the full text on click; "text unknown" in muted style when null)
  - voice
  - duration in `m:ss`
  - pack
  - **▶ theirs**, which plays `urls` one after another on a single shared `Audio` element
  - **▶ <compare_label>** when `compare_url` is set
- **Playback:** only one thing plays at a time. Clicking the playing button stops it. A `missing` row shows "file missing" instead of the play button.

- [ ] **Step 1: Write the failing tests** (TestClient over `create_app(build_catalog(addons_tmp, compare_tmp, data_tmp))`, as in `tests/test_audition.py`)

```python
def test_lines_api_and_audio(tmp_path):
    r = client.get("/api/lines", params={"kind": "accept", "quest": 7}).json()
    assert r["total"] == 1 and r["rows"][0]["urls"] == ["/api/audio/pack/ForeverVO_Data_New/Quests/7-accept.mp3"]
    assert client.get(r["rows"][0]["urls"][0]).headers["content-type"] == "audio/mpeg"
    assert r["rows"][0]["compare_url"] == "/api/audio/compare/Quests/7-accept.mp3"
    assert client.get(r["rows"][0]["compare_url"]).status_code == 200

def test_audio_path_refused(tmp_path):
    for url in ["/api/audio/pack/ForeverVO_Data_New/../Data/Pack.lua", "/api/audio/pack/ForeverVO_Data_New/Quests/..%2F..%2FPack.lua",
                "/api/audio/pack/NotAPack/Quests/7-accept.mp3", "/api/audio/pack/ForeverVO_Data_New/Quests/7-accept.lua",
                "/api/audio/compare/../secret.mp3"]:
        assert client.get(url).status_code == 404

def test_no_packs_found(tmp_path):
    c = TestClient(create_app(build_catalog(tmp_path / "missing", None, tmp_path)))
    f = c.get("/api/facets").json()
    assert f["packs_found"] == 0 and f["addons"].endswith("missing") and c.get("/").status_code == 200

def test_browse_does_not_import_the_pipeline():
    out = subprocess.run([sys.executable, "-c", "import sys, tools.browse; print(sorted(m for m in ('tools.generate','tools.audition','torch','chatterbox','fcntl') if m in sys.modules))"],
                         capture_output=True, text=True, check=True, cwd=ROOT)
    found = set(eval(out.stdout))
    assert not found - ({"fcntl"} if sys.platform != "win32" else set())   # the stdlib may load fcntl on Linux; the pipeline modules never
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run --no-group tts --group dev pytest tests/test_browse.py -v -k "api or refused or no_packs or pipeline"`
Expected: FAIL (`create_app` or `build_catalog` is not defined).

- [ ] **Step 3: Implement `build_catalog`, `create_app` and `main`; write `index.html`; edit `pyproject.toml`; run `uv lock`; add the README section**

- [ ] **Step 4: Run the whole test file and lint**

Run: `uv run --no-group tts --group dev pytest tests/test_browse.py -v`, then the two lint commands from Global Constraints.
Expected: PASS, and ruff reports no issues.

- [ ] **Step 5: Run the whole suite without the GPU stack** (the same way CI does)

Run: `uv run --no-group tts --group dev pytest`
Expected: the same pass/fail as on `main` before this branch (write the baseline down first with `git stash`, or by running it on `main`). No new failures.

- [ ] **Step 6: Commit**

```bash
git add tools/browse tests/test_browse.py pyproject.toml uv.lock README.md
git commit -m "Pack browser: fvo-browse, the page and its API"
```

---

### Task 6: Check it against the real packs

**Files:** none, unless a fix turns up. Any fix goes into the task it belongs to, with a test.

- [ ] **Step 1: Start it on the installed packs.** Add `.claude/launch.json` (gitignored locally, not committed) with the name `fvo-browse`, `runtimeExecutable` set to `uv`, and `runtimeArgs` set to `["run","--no-group","tts","--group","browse","fvo-browse","--addons","C:/Program Files (x86)/World of Warcraft/_classic_beta_/Interface/AddOns"]` on port 8766. Start it with preview_start.
- [ ] **Step 2: Check the totals.** The page loads in a few seconds. The totals line lists six packs and tens of thousands of lines, and the console shows no errors.
- [ ] **Step 3: Check the filters and playback.** Filter by kind = accept and quest 7: one row from Classic Quests, and it plays. Try a gossip row from Classic Gossip, a line with parts (it plays through every part), a `male`/`female` pair, a narrator alternate, and a book page.
- [ ] **Step 4: Check the comparison pairing.** Make a throwaway comparison folder in the scratchpad with a `Quests/7-accept.mp3` copied from the pack, and restart with `--compare <it>`. The "with comparison" filter now shows that one row with two play buttons. Remove the folder afterwards.
- [ ] **Step 5: Take a screenshot for the hand-over.** If any fixes were needed, commit them.
