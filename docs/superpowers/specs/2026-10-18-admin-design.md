# Admin over the forever-vo library: design

Date: 2026-10-18. Branch `nypam/admin` on the fork `nypam/forever-vo`, built on
`nypam/pack-browser`. This is project 1 of 3:

1. **This one:** the Talk2Me admin, ported into the fork and run on
   forever-vo's own data.
2. The Talk2Me VoiceStudio engine: "regenerate" writes your takes beside theirs.
3. Talk2Me's extra lines exported as `tools/data/bulk/talk2me.json`.

## Intent

The owner of Talk2Me (a second voiceover pipeline for WoW Forever, built on
VoiceStudio) wants to show that their voices sound better than Forever
Voiceover's Chatterbox packs. If they do, the work goes upstream as pull
requests to `quinn-dougherty/forever-vo`.

The tool for that is Talk2Me's admin page (`pipeline/admin.py` in
`nypam/talk2me`), which the owner already likes. Its pages:

- a lines list with filters and players
- NPC pages with voice settings and the original Blizzard barks
- a voice-sets page
- quest progress by level and zone
- a "Run the pipeline" card

It should become the face of forever-vo's library: every line forever-vo
knows, their audio, the NPCs and the voices behind them, and the Blizzard
recordings those voices come from. Project 2 then adds your takes and
regeneration, and project 3 adds your lines. The pack browser built on
`nypam/pack-browser` was a first step, and its look is retired. Its data layer
(`tools/browse/packs.py`, `lines.py`, `texts.py`, `catalog.py`) is what this
builds on.

## Decisions already made by the owner

- **Forever-vo's data format stays the source of truth.** `capture.json`,
  `bulk/*.json`, the installed packs' tables and audio, and `configs/` are read
  as they are. Nothing is converted into a Talk2Me corpus.
- **The admin moves into the fork** and follows the fork's conventions. It is
  not a Talk2Me feature that reads their files.
- **The goal is an upstream PR when ready**, so it must be something Quinn could
  accept next to his own tools.
- **Comparison is the point.** Every line shows their take and, from project 2
  on, yours, side by side. Their packs are never overwritten.
- **Keep the Blizzard inspiration.** The original Blizzard recordings behind a
  voice stay audible in the admin, next to the generated takes.
- **Voice first, NPC as the way in.** You notice a problem on an NPC page; the
  fix usually belongs to the voice that NPC shares with others, and the voice
  page is where the Blizzard material and the tuning live. Per-NPC overrides are
  the exception (project 2).
- **The dashboard is an overview of the whole library:** total quests, total
  lines, total voiced, and so on.
- **Talk2Me's look** (Basecoat, shadcn/ui as plain CSS) rather than audition's
  own CSS.

## Goals

1. **Dashboard** (`/`). The library at a glance:
   - **Totals:** quests known; lines known by kind (accept, progress, complete,
     gossip, book); lines with audio in the packs, overall and by kind; lines
     with a take in the comparison folder; NPCs that speak; voices in use.
   - **Decided: a "line" is a distinct line, not a table row.** A line's
     variant rows (alternate narrators, other sex, other speakers) are not
     counted as lines; there are about 4,400 of them on today's packs. They are
     shown as their own total ("variant recordings"). A `$G` line's male and
     female rows count once. The Lines page shows main rows by default, with a
     "show variants" toggle, so each dashboard link reproduces its count.
   - **Gaps:** lines with text but no audio; lines with audio but no text;
     progress lines (they aren't voiced unless `fvo-generate --progress`).
   - **Breakdowns** by level bracket and by zone, in the style of Talk2Me's
     Quests page. **Decided:** they count lines (known, voiced, your takes, with
     a voiced percentage), not quest states. "Partly voiced quests" can't be
     reproduced by a line filter, and progress text, which they don't voice by
     default, would leave almost every quest partly voiced. Progress gets its
     own column. The level breakdown needs `bulk/classic.json`; without it,
     the dashboard says so, like the Classic-text notice.
   - **Links:** every number opens the Lines page filtered to exactly those
     lines.
2. **Lines** (`/lines`). Talk2Me's lines table on forever-vo's catalogue.
   - **Filters:** kind, pack, voice, zone, level range, quest (id or title), NPC
     (id or name), words, and a status of "voiced", "text only", "with your take"
     or "no text".
   - **Each row:** the kind and variant, quest or NPC (linking to the NPC page),
     zone, text, voice (linking to the voice page) and duration, plus
     **▶ theirs**, and **▶ yours** when a comparison take exists.
   - **Rows without audio** are listed too, because the library is everything
     known, not only what the packs voice.
3. **NPC page** (`/npc/<speaker>`). The way in.
   - **Identity:** name, speaker key, sex, model (display ID or model file ID),
     and the zones where it was met.
   - **Voices:** their voice for this NPC as the packs actually use it (the
     voices found on its lines; more than one is possible) and the Blizzard
     NPCSounds set of its display.
   - **"Shared by N NPCs"** for each voice, linking to the voice page.
   - **Soundboard:** the Blizzard barks of its NPCSounds set (greeting,
     farewell, annoyed), playable.
   - **All its lines** with both players.
4. **Voice page** (`/voice/<name>`). Where tuning lives. For one of their voices
   (`human-male-official`, `narrator`, ...):
   - **Clone source:** the Blizzard clips their reference is built from (see
     Data), each playable.
   - **Settings:** shown as configured, not edited:
     - its own `[tts.voices.<voice>]` row from `configs/tts.toml` if it has one,
       else "no row of its own" with the `[tts]` defaults
     - its fallback chain from `configs/voices.toml`, as text
     - any `[voices.speakers]` pins

     **Decided:** this is a plain read of the config, labelled "as configured".
     It doesn't re-implement `generate`'s resolution (a variant voice takes
     its race's row, and a voice with no clip takes its fallback's). That would
     mean re-implementing code that can't be imported, and it depends on
     gitignored reference wavs.
   - **Who uses it:** the NPCs on it, with counts and links, and a sample of its
     lines with players.
5. **Voices** (`/voices`). Every voice in use: line count, NPC count, whether it
   has picked clips and tuning, and example NPCs. In the style of Talk2Me's
   "Blizzard voice sets" page.
6. **Runs on Windows and Linux** with no GPU stack:
   `uv run --no-group tts --group admin fvo-admin`.

## Non-goals (this project)

- **Generating anything,** and the "Run the pipeline" card. That is project 2.
- **Editing settings.** Talk2Me's NPC settings form (persona, design, acting
  notes, engine, speed, seed, clone reference) belongs to the engine in project
  2. Their own settings (`tts.toml`, `voices.toml`, source picks) stay edited in
  their audition page; this admin only shows them.
- **Flags and other review state.** Project 2 decides where your review state
  lives.
- **Talk2Me's lines and corpus.** Project 3.
- **Replacing or changing audition.** It stays Quinn's tuning lab.
- **Karaoke captions, the progress bar, the avatar-only UI and the launcher.**
  Later.

## Anti-goals

- **Changing anything a player or the pipeline reads:** packs, `configs/`,
  `capture.json`, `bulk/`, `sound_index.json`. The only things written are
  gitignored caches, through `tools.wowdata`'s own helpers:
  - `tools/data/casc/<build>/` (clips)
  - `tools/data/db2/` (tables such as SoundKitEntry, fetched on first use)
  - `tools/voices/raw/admin/` (links to the clips the page plays)
- **Importing `tools.generate` or `tools.audition`,** directly or indirectly.
  That pulls in `fcntl` and torch, and the admin would stop starting on Windows.
  `tools.wowdata`, `tools.config`, `tools.soundpaths` and `tools.textkey` are
  safe; check any other module before importing it.
- **A JavaScript build step, new runtime dependencies in
  `[project].dependencies`, or reformatting shared modules.** Any of these would
  make the upstream PR awkward.
- **A row that plays the wrong file.** That covers their take shown as yours,
  a variant's file shown for the plain line, and a Blizzard clip from another
  set.

## Constraints and conventions

- **The fork's conventions.** Python 3.12 through uv; ruff check and format;
  `ty check` clean on new code; pytest under `tests/` passing without the `tts`
  group; read `CLAUDE.md` first. On Windows, 18 existing test files cannot load
  because they import `fcntl`, and one existing test fails. That is the
  baseline and must not get worse.
- **App shape.** A FastAPI app in a package `tools/admin/` with server-rendered
  HTML pages, ported from Talk2Me's `admin.py` string templates (`page`,
  `table`, `row`, `badge`, `play`, `avatar`...). Basecoat comes from the same
  CDN URL Talk2Me uses (`basecoat-css@1.0.2`). There is no build step, and
  a little inline JS for players and filters.
- **Packaging.** Rename the pack browser's package to `tools/admin/`: keep its
  `packs.py`, `lines.py`, `texts.py` and `catalog.py`, and drop its
  `index.html` page and the `fvo-browse` command (never released). Rename the
  dependency group `browse` to `admin`, and the script to
  `fvo-admin = "tools.admin:main"`. Keep `uv.lock` at `revision = 3`, the
  format their uv writes. The README's "Browsing the voice packs" section
  becomes "The admin".
- **Command-line options.** Default port 8766, and `--open`. `--addons`,
  `AUDITION_ADDONS` and `WOW_DIR` find the packs, as now. `--compare` and
  `FVO_COMPARE` name the comparison folder ("yours"), as now; project 2 writes
  there.
- **Already built and kept:** the pack browser's rules for parts, `$G` m-/f-
  rows, other-sex and other-speaker variants, alternate narrators, retired
  packs, and safe audio paths.

## Data: where each thing comes from

| Thing | Source |
|---|---|
| Voiced lines, their voice and duration | the installed packs, through the pack browser's `merge(find_packs(...))` |
| Known lines (with or without audio) | `capture.json`, merged over `bulk/*.json` (`texts.load_texts`). A quest line is a `quests["<id>-<event>"]` entry, and a gossip line a `gossip["<speaker>\|<hash>"]` entry. A known line with no pack row becomes a "text only" row whose `files` list is empty |
| Lines with audio but no known text | pack rows that `annotate` leaves with `text` None |
| A known line paired with its pack row | quests by (quest id, event). Gossip by speaker plus `tools.textkey.text_key` of the text, which equals the pack's gossip `h`, with `$G` text resolved as the pack does |
| NPC name, sex, display ID, model file ID, zones | the packs' `npcs`/`sexes`/`models`, then `npcs[...]` and the `zone`/`mapID` of entries in `capture.json` and `bulk/*.json` |
| NPCSounds set of an NPC | `tools.wowdata.display_sound_set(displayID)`, when a display ID is known. Classic NPCs get one from `bulk/classic.json` (VMaNGOS) once `fvo-classicdb` has run; captures and packs almost never carry one (9 of 1,867 captured NPCs). **Decided:** with no display ID, no set is guessed from the model, because a model maps to several sets (the human male model to 15). The soundboard then plays the Blizzard clips of the NPC's *voice* (the voice page's clone source), labelled "Blizzard clips behind <voice>", not as the NPC's own set. No model-to-display code |
| Barks of a set | the NPCSounds row's sound kits (greeting, farewell, annoyed) through `wowdata.load_db2`. Talk2Me's `sources.voice_set_barks` reads the same tables and shows the joins |
| Blizzard clip audio | `tools.wowdata.fetch_file(fdid, dest)`, which fetches from wago.tools on first use and caches under `tools/voices/raw/admin/` (gitignored). The page plays `.ogg`. When offline it shows "clip not available offline" and the page still works |
| A voice's clone source | **Decided:** the pick in use, `[voices.sources.<voice>]` in `configs/voices.sources.toml` (`clips`, plus `build` when it is not the default), through `tools.config.load_config()`. `tools/data/source_picks.json` is audition's undo history (newest first) and is not the source. A voice with no pick that borrows another voice's clip (`[voices.fallbacks]`) shows that voice's pick, labelled "borrowed from <voice>". A voice with neither says "automatic reference (no clips picked by ear)", with no clips listed |
| A voice's settings | `configs/tts.toml` and `configs/voices.toml`, through `tools.config.load_config()` (read only) |
| Your takes | the comparison folder, through `Catalog.compare_path` |

Everything is loaded once at startup (about 1 second for 22,900 rows). Blizzard
clips are fetched lazily, when a page that shows them is opened.

## Testing

- **Fixtures, no network.** Build on `tests/test_browse.py` (renamed
  `tests/test_admin.py`). Use the fake AddOns folder, a small `capture.json` and
  `bulk/classic.json`, and a comparison folder. Replace `fetch_file` with one
  that copies a fixture `.ogg`, and stub `wowdata`'s db2 lookups with small
  tables.
- **Check:**
  - the dashboard totals and that each link's filter reproduces its count
  - text-only rows, and audio-only rows
  - gossip pairing through `text_key`
  - the NPC page's voices and "shared by"
  - the voice page's picks and settings
  - bark playback through the cache, and the offline message
  - 404s for unknown NPCs and voices, and the existing path-safety cases
  - the no-import guard (`tools.generate`, `tools.audition`, torch, chatterbox)

## Left to the builder

- Module layout inside `tools/admin/` (pages, rendering, wago access).
- The exact dashboard layout, within "an overview of the whole library" in
  Talk2Me's style.
- How variants (`sex f`, `speaker …`, narrator alternates) show on the NPC and
  voice pages.
- How many sample lines a voice page shows, and how NPC lists are capped.
