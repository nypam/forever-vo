# Pack browser: design

Date: 2026-10-18. Branch `nypam/pack-browser` on the fork `nypam/forever-vo`.

## Intent

We want to know, with real evidence, whether the Talk2Me pipeline
(VoiceStudio: OmniVoice, IndexTTS 2.5, plus acting notes, a lexicon and quality
checks) sounds better than Forever Voiceover's Chatterbox packs. Before any
voting site, we need to *hear* their catalogue: every line in the installed
voice packs, findable by quest, NPC, zone or voice, and playable. When a line
also has a take from another pipeline, that take plays right beside theirs.

The audition page (`uv run audition`) does not do this. It is a tuning lab for
one line at a time: search by words, random line, or all lines of one voice,
then generate new Chatterbox takes and keep settings. It has no catalogue view
or filters. It also cannot start on Windows: it imports `tools.generate`, and
both modules import `fcntl`. It needs the CUDA stack as well.

The browser is built in the fork, in the repo's own style, so it could be
offered upstream as a pull request later.

## Goals

1. **List every voiced line in the installed packs.** That covers quest accept,
   progress and complete; gossip and greetings; books; and the narrator's
   alternate voices. Each row shows the line's text, its quest (id and title) or
   speaker (NPC id and name), the voice that read it, the duration, and the pack
   and pack version it came from.
2. **Filter and search.** Filter by kind, pack, voice, quest id, NPC id or name,
   zone, quest level when known, and "has a comparison take". Search the text for
   words. Paging is done on the server, because there are about 24,000 files.
3. **Play.** Each row has a play button that streams the MP3 from the pack folder
   where it is installed.
4. **Comparison slot.** `--compare <dir>` (or `FVO_COMPARE`) points at a folder
   laid out like a pack's `Sounds/`. Rows whose file also exists there get a
   second play button labelled with that folder's name. The "has a comparison
   take" filter can then narrow the list to the pairs.
5. **Runs on Windows and Linux** with `uv run --no-group tts --group browse fvo-browse`. It needs
   no GPU, no torch and no Chatterbox.

## Non-goals

- Generating or regenerating audio. The audition page and `fvo-generate` own that.
- Editing `configs/`, the sound index, pins or pack tables.
- Voting, comments, or anything shown to other people. The public side-by-side
  site comes later and will be built from the pairs this tool finds.
- Changing the addon (`ForeverVO/`) or the pack format.
- Replacing the Talk2Me admin page. It stays the tool for Talk2Me's own pipeline.
- The Talk2Me export that fills the comparison folder. It is a separate change in
  the talk2me repo (see "Comparison folder" below).

## Anti-goals (a failure even if it works)

- Writing anything inside `Interface/AddOns`, `configs/` or `tools/data/`. The
  browser only reads.
- Importing `tools.generate` or `tools.audition`. That brings back `fcntl` and
  the torch stack, and the browser would stop starting on Windows.
- Drifting from the repo's conventions in a way that would make an upstream PR
  awkward. That includes new runtime dependencies in `[project].dependencies`, a
  JavaScript build step, or a reformatted shared module.
- Showing a line as "theirs" when the file actually came from the comparison
  folder, or the other way round.

## Constraints and conventions (from the repo)

- Python 3.12 through uv; `ruff check` and `ruff format` must pass; tests live in
  `tests/` and run under pytest in CI without the `tts` group. `CLAUDE.md` at the
  repo root is required reading.
- Web UI style follows `tools/audition`: a package with `__init__.py` (a FastAPI
  app plus `main()`) and one `index.html` with no build step, served by the app.
- FastAPI and uvicorn are currently only in the `dev` and `tts` groups. Add a
  dependency group (`browse = ["fastapi", "uvicorn"]`) rather than touching
  `[project].dependencies`, and a console script `fvo-browse =
  "tools.browse:main"` in `[project.scripts]`. Update `uv.lock`.
- Default port 8766. Audition and the Talk2Me admin both use 8765.
- Lua tables are parsed with `tools/luatable.py`, the repo's own reader.
- Pack folders are found the way audition finds them: `--addons`, else
  `AUDITION_ADDONS`, else `<WOW_DIR>/_classic_beta_/Interface/AddOns`. The default
  `WOW_DIR` is a Faugus install, so on Windows the user sets `WOW_DIR` (here
  `C:\Program Files (x86)\World of Warcraft`). Every `ForeverVO_Data*` folder
  with a `Sounds/` folder is a pack. `Data/Pack.lua` gives its name, version and
  priority.

## Data: where each field comes from

All of it is read once at startup and held in memory. 24k rows is small.

| Field | Source |
|---|---|
| Quest lines, voice, duration, hashes, `npc`, `ender` | `<pack>/Data/Quests.lua`: `pack.quests[id] = { a=, va=, ha=, p=, vp=, c=, vc=, npc=, ender= }`. `a`/`p`/`c` are the durations of accept/progress/complete, `va`/`vp`/`vc` the voices. File `Sounds/Quests/<id>-<accept\|progress\|complete>.mp3` |
| Gossip lines, text, voice, duration | `<pack>/Data/Gossip.lua`: `pack.gossip[npc] = { { f=, h=, t=, d=, v=, ... } }`. File `Sounds/Gossip/<f>.mp3` |
| Quest table's other keys | `ForeverVO/Core/Packs.lua` is the authority. `aP`/`pP`/`cP` (and gossip `P`/`nP`) are **parts** (see below). `g` marks `$G` lines, `s*` other-sex variants under `Sex/`, `xa`/`xp`/`xc` per-speaker variants under `Speaker/<key>/`, and `w*` the "wanted" capture hints, which the browser ignores. Each sex or speaker variant with its own file is a row of its own, labelled with that variant |
| Books | `<pack>/Data/Books.lua`: `pack.books["<hash>"] = { d=, t=, s= }` (`t` is the raw page and `s` the prose shown). File `Sounds/Books/<hash>-page.mp3` |
| Narrator alternates | `<pack>/Data/Narrator.lua`: `pack.narratorVoices`, `pack.narrator[id] = { [i] = { a=, c= } }`. Files under `Sounds/<Quests\|Gossip>/Narrator/<voice>/` |
| NPC sex / model | `<pack>/Data/NPCs.lua` |
| Quest text, title, zone, NPC names | `tools/data/capture.json` (in git), merged under `tools/data/bulk/*.json` when present (`fvo-classicdb` writes `bulk/classic.json` from VMaNGOS). Capture wins field by field, the same rule as `generate.load_sources`. Re-implement that small merge in the browser; do not import it |
| Quest level | `bulk/classic.json` when present; otherwise blank |
| Zone | `capture.json` (`zone`) first. Then, if the VMaNGOS snapshot that `fvo-classicdb` downloads is under `tools/data/classicdb/`, the quest's `ZoneOrSort`, read straight from that SQLite file, read only, with a name if the snapshot has an area-name table and the id otherwise. `classicdb.py` is not changed. A line with no zone shows "zone unknown", and the zone filter has an "unknown" entry |

**Setup step.** Run `uv run --no-group tts fvo-classicdb` once, so `bulk/classic.json`
exists. It is plain Python plus `requests`, and portable. Without it, about 2,950
Classic quests have audio but no text, title or level. The browser still lists
them, and says at the top that the Classic text is missing and how to fetch it.

A line with audio but no known text still shows. It gets a "text unknown" mark,
because the audio is what we are comparing.

When two packs carry the same file (an old Base pack beside the new ones), the
row comes from the pack the addon would play: higher `priority` first, then name,
as `Packs.lua` and `audition.sound_packs` order them. The row says which pack.

### Parts, and gendered lines (decided)

- **A line plays the way the addon plays it.** When a line has parts (the speaker's
  words in their voice, each stage direction in the narrator's), "▶ theirs" plays
  the parts back to back, in order. That is what players hear, so it is the fair
  thing to compare. A line is one row, whatever its number of parts. The packs
  have about 503 such lines, and 53 have no whole-line file at all. The kept
  whole-line file (speaker only, for older addons) is not played. Totals count
  lines, not files.
- **`$G` lines** exist only as `m-<base>.mp3` and `f-<base>.mp3`. Each is a row,
  labelled male or female. A comparison file `m-<base>.mp3` / `f-<base>.mp3`
  pairs with its own row. Failing that, a plain `<base>.mp3` in the comparison
  folder pairs with both rows. The Talk2Me export may write either.

## Comparison folder

The folder is laid out like a pack's `Sounds/`: `Quests/<id>-<event>.mp3`,
`Gossip/<npc>-<hash>.mp3`, and `Books/...` if it has books. Any pipeline can fill
it. The first one will be a Talk2Me export, a later change in the talk2me repo,
which maps Talk2Me keys like this:

| Talk2Me key | forever-vo file |
|---|---|
| `detail_<id>` | `Quests/<id>-accept.mp3` |
| `progress_<id>` | `Quests/<id>-progress.mp3` |
| `complete_<id>` | `Quests/<id>-complete.mp3` |
| `gossip_<npc>_<djb2>` | `Gossip/<npc>-<HashText>.mp3`, with the hash from `tools/textkey.py` on the line's text |

The browser only checks whether `<compare>/<subfolder>/<base>.mp3` exists and
serves it. The folder's name is the label on the second play button.

## Interface

One page in the style of the audition page (plain HTML, CSS and JS in
`index.html`):

- A filter bar: kind, pack, voice (each a list of the values actually present),
  zone, a level range, quest id, NPC (id or name), word search, and a "with
  comparison" checkbox. The filters are written to the URL query string, so a
  filtered view can be bookmarked.
- A results table: kind, quest (id and title) or NPC (id and name), the text (cut
  short, full text on expand), voice, duration, pack, then a **▶ theirs** button
  and, when there is one, a **▶ <compare-label>** button. Only one clip plays at
  a time.
- A header line with the totals: lines, lines matching the filter, and lines with
  a comparison take.

API (read only): `GET /api/facets` (the filter values and counts), `GET
/api/lines?…filters…&offset=&limit=`, `GET /api/audio/pack/<pack>/<subfolder>/<name>`
and `GET /api/audio/compare/<subfolder>/<name>`. Path parts are checked against a
safe-name pattern (as audition's `SAFE_NAME` does) and resolved inside their root.

## Testing

pytest without the `tts` group: build a tiny fake AddOns folder in `tmp_path` (two
packs with overlapping files and different priorities, a few `Data/*.lua` tables,
empty MP3 files), plus a fake compare folder and a small capture JSON. Then check:
rows parsed per kind, priority resolution, text merged from capture, the
comparison pairing, filters and paging, path traversal refused, and that importing
`tools.browse` does not import `tools.generate` or `fcntl`.

## Left to the builder

- Module layout inside `tools/browse/`, and how the Lua tables become rows.
- How the narrator alternates show: extra rows, or extra play buttons on the
  default narrator row.
- The page's look, within "like audition".
- Whether books need anything beyond the general row.
