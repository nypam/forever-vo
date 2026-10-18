"""The admin's pages, as HTML strings in the style of Talk2Me's admin."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import parse_qs, quote, urlencode

from tools.admin.catalog import Catalog, Filters, filters_from_query, query_of, whole
from tools.admin.dashboard import Count, Summary
from tools.admin.lines import Line, is_variant, voiced
from tools.admin.people import Npc, VoiceInfo
from tools.admin.render import WOWHEAD, badge, duration, esc, model_image, page, play

PAGE_SIZE = 100
KINDS = ("accept", "progress", "complete", "gossip", "book")
STATUSES = (
    ("voiced", "voiced"),
    ("text_only", "text only"),
    ("audio_only", "audio only"),
    ("no_text", "no text"),
    ("yours", "with your take"),
)


def audio_urls(line: Line) -> list[str]:
    """What "▶ theirs" plays: the line's files, in order; nothing when missing."""
    if line.missing or not line.files:
        return []
    return [f"/api/audio/pack/{quote(line.pack)}/{quote(f)}" for f in line.files]


def compare_url(catalog: Catalog, line: Line) -> str | None:
    compared = catalog.compare_path(line)
    return f"/api/audio/compare/{quote(compared)}" if compared else None


def plural(n: int, word: str) -> str:
    return f"{n:,} {word}" if n == 1 else f"{n:,} {word}s"


# --------------------------------------------------------------------------
# Dashboard
# --------------------------------------------------------------------------
def stat(count: Count) -> str:
    return (
        f'<div class="card stat" data-size="sm"><section><a href="{esc(count.link)}">'
        f"<b>{count.value:,}</b><span>{esc(count.label)}</span></a></section></div>"
    )


def number(count: Count) -> str:
    return f'<td class="num"><a href="{esc(count.link)}">{count.value:,}</a></td>'


def breakdown(title: str, first: str, heads: list[str], rows: list[list[Count]]) -> str:
    head = "".join(f'<th class="num">{esc(h)}</th>' for h in heads)
    body = ""
    for row in rows:
        known, voiced_count = row[0].value, row[1].value
        share = 100 * voiced_count / known if known else 0
        body += (
            f'<tr><td><a href="{esc(row[0].link)}">{esc(row[0].label)}</a></td>'
            + "".join(number(count) for count in row)
            + f'<td><div class="bar"><span style="width:{share:.2f}%"></span></div></td>'
            f'<td class="num">{share:.1f}%</td></tr>'
        )
    if not rows:
        body = (
            f'<tr><td colspan="{len(heads) + 3}" class="muted">Nothing yet.</td></tr>'
        )
    return (
        f'<div class="card" style="padding-block:4px"><header><h2>{esc(title)}</h2></header>'
        f'<div class="table-container"><table class="table"><thead><tr><th>{esc(first)}</th>'
        f'{head}<th>voiced</th><th class="num">voiced %</th></tr></thead><tbody>{body}'
        "</tbody></table></div></div>"
    )


def dashboard_page(s: Summary, notices: list[str]) -> str:
    """`notices` are trusted HTML (built from escaped values)."""
    body = (
        '<div><h1>Library</h1><p class="muted">Every line forever-vo knows: the voice '
        "packs' audio, the text captured in game or exported from Classic, and your "
        "takes beside them. Every number opens the lines it counts.</p></div>"
        + "".join(f'<div class="notice">{notice}</div>' for notice in notices)
        + f'<div class="stats">{"".join(stat(count) for count in s.totals)}</div>'
        + breakdown(
            "By kind", "Kind", ["known", "voiced", "text only", "yours"], s.by_kind
        )
        + breakdown("By level", "Level", ["known", "voiced", "yours"], s.by_level)
        + breakdown("By zone", "Zone", ["known", "voiced", "yours"], s.by_zone)
    )
    return page("Dashboard", body, "/")


# --------------------------------------------------------------------------
# Lines
# --------------------------------------------------------------------------
def select(name: str, label: str, options: list[tuple[str, str]], value: str) -> str:
    choices = "".join(
        f'<option value="{esc(v)}"{" selected" if v == value else ""}>{esc(text)}</option>'
        for v, text in options
    )
    return f'<select class="select" name="{name}"><option value="">{esc(label)}</option>{choices}</select>'


def text_input(name: str, placeholder: str, value: object, width: str = "") -> str:
    style = f' style="width:{width}"' if width else ""
    shown = "" if value is None else value
    return (
        f'<input class="input" name="{name}" placeholder="{esc(placeholder)}"'
        f' value="{esc(shown)}"{style}>'
    )


def checkbox(name: str, label: str, on: bool) -> str:
    return (
        f'<label class="label"><input class="input" type="checkbox" name="{name}" value="1"'
        f"{' checked' if on else ''}> {esc(label)}</label>"
    )


def filter_form(catalog: Catalog, f: Filters) -> str:
    facets = catalog.facets()
    packs = [(p["value"], p["label"]) for p in facets["packs"] if p["value"]]
    voices = [(v["value"], v["value"]) for v in facets["voices"]]
    zones = [(z["value"], z["value"]) for z in facets["zones"]]
    level_unknown = (
        '<input type="hidden" name="level_unknown" value="1">'
        if f.level_unknown
        else ""
    )
    compare = (
        checkbox("compare", f"with a take in {catalog.compare_dir.name}", f.compare)
        if catalog.compare_dir
        else ""
    )
    return f"""<form method="get" action="/lines" class="card filters"><section class="row">
{select("kind", "kind", [(k, k) for k in KINDS], f.kind)}
{select("status", "status", list(STATUSES), f.status)}
{select("pack", "pack", packs, f.pack)}
{select("voice", "voice", voices, f.voice)}
{select("zone", "zone", zones, f.zone)}
{text_input("level_min", "level from", f.level_min, "90px")}
{text_input("level_max", "to", f.level_max, "70px")}
{text_input("quest", "quest id", f.quest_id, "100px")}
{text_input("npc", "NPC id or name", f.npc)}
{text_input("q", "words in the text or title", f.q)}
{checkbox("variants", "other recordings", f.variants)} {compare}{level_unknown}
<button class="btn" data-variant="secondary">Filter</button>
<a class="btn" data-variant="ghost" href="/lines">Clear</a></section></form>"""


def line_cell(line: Line) -> str:
    badges = [badge(line.kind, "voiced" if voiced(line) else "text_only")]
    if line.missing:
        badges.append(badge("file missing", "missing"))
    if line.variant:
        badges.append(badge(line.variant, "variant" if is_variant(line) else ""))
    quest = ""
    if line.quest_id is not None:
        level = f" · lv{line.level}" if line.level else ""
        quest = (
            f'<span class="muted small">[{line.quest_id}] <a target="_blank" rel="noopener"'
            f' href="{WOWHEAD}/quest={line.quest_id}">{esc(line.title or "quest")}</a>{level}</span>'
        )
    elif line.kind == "book" and line.title:
        quest = f'<span class="muted small">{esc(line.title)}</span>'
    return f'<div class="stack"><div class="row">{"".join(badges)}</div>{quest}</div>'


def speaker_cell(line: Line) -> str:
    if line.speaker is None:
        return '<span class="muted small">narrator</span>'
    return (
        f'<a href="/npc/{line.speaker}">{esc(line.speaker_name or "Unknown")}</a>'
        f'<br><span class="muted small">{line.speaker}</span>'
    )


def players(catalog: Catalog, line: Line) -> str:
    theirs = audio_urls(line)
    yours = compare_url(catalog, line)
    cells = []
    if theirs:
        cells.append(
            f'<div class="row">{play(theirs, "Play their take")}<span class="small">theirs</span></div>'
        )
    elif line.missing:
        cells.append('<span class="small muted">file missing</span>')
    if yours and catalog.compare_dir:
        label = catalog.compare_dir.name
        cells.append(
            f'<div class="row">{play(yours, f"Play the take in {label}", "yours")}'
            f'<span class="small">{esc(label)}</span></div>'
        )
    return f'<div class="players">{"".join(cells)}</div>'


def line_row(catalog: Catalog, line: Line) -> str:
    voice = (
        f'<a class="mono" href="/voice/{quote(line.voice)}">{esc(line.voice)}</a>'
        if line.voice
        else ""
    )
    zone = esc(line.zone) if line.zone else '<span class="muted">unknown</span>'
    text = (
        esc(line.text)
        if line.text is not None
        else '<span class="muted">text unknown</span>'
    )
    return (
        f'<tr data-kind="{esc(line.kind)}"><td>{line_cell(line)}</td><td>{speaker_cell(line)}</td>'
        f'<td>{zone}</td><td class="text">{text}</td><td>{voice}</td>'
        f'<td class="num">{duration(line.duration)}</td><td>{players(catalog, line)}</td></tr>'
    )


def lines_table(catalog: Catalog, rows: list[Line]) -> str:
    columns = (
        ("Line", 210),
        ("Speaker", 190),
        ("Zone", 140),
        ("Text", 0),
        ("Voice", 190),
        ("Length", 70),
        ("", 150),
    )
    cols = "".join(f'<col style="width:{w}px">' if w else "<col>" for _, w in columns)
    head = "".join(f"<th>{h}</th>" for h, _ in columns)
    body = "".join(line_row(catalog, line) for line in rows) or (
        '<tr><td colspan="7" class="muted">No lines match.</td></tr>'
    )
    return (
        '<div class="card" style="padding-block:4px"><div class="table-container">'
        f'<table class="table lines"><colgroup>{cols}</colgroup><thead><tr>{head}</tr></thead>'
        f"<tbody>{body}</tbody></table></div></div>"
    )


def lines_page(catalog: Catalog, query: str) -> str:
    f = filters_from_query(query)
    given = {k: v[-1] for k, v in parse_qs(query).items()}
    page_no = max(whole(given.get("page", "")) or 1, 1)
    rows_total, rows = catalog.query(
        f, offset=(page_no - 1) * PAGE_SIZE, limit=PAGE_SIZE
    )
    lines_total = catalog.count_lines(f)
    base = query_of(f)
    nav = ""
    if page_no > 1:
        nav += (
            f'<a class="btn" data-variant="outline" data-size="sm"'
            f' href="/lines?{esc(urlencode([*parse_qs(base).items(), ("page", page_no - 1)], doseq=True))}">Previous</a> '
        )
    if page_no * PAGE_SIZE < rows_total:
        nav += (
            f'<a class="btn" data-variant="outline" data-size="sm"'
            f' href="/lines?{esc(urlencode([*parse_qs(base).items(), ("page", page_no + 1)], doseq=True))}">Next</a>'
        )
    body = (
        f'<div><h1>Lines</h1><p class="muted">{plural(lines_total, "line")} '
        f"({plural(rows_total, 'row')}). Page {page_no}.</p></div>"
        f'{filter_form(catalog, f)}{lines_table(catalog, rows)}<div class="row">{nav}</div>'
    )
    return page("Lines", body, "/lines")


# --------------------------------------------------------------------------
# NPC, voice and voices pages
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Clip:
    """A Blizzard recording on a soundboard; played lazily from /clip/."""

    fdid: int
    label: str
    build: str = ""

    @property
    def url(self) -> str:
        return f"/clip/{self.fdid}.ogg?build={quote(self.build)}"


def soundboard(title: str, clips: list[Clip], empty: str) -> str:
    if clips:
        tiles = (
            '<div class="tiles">'
            + "".join(
                f'<div class="tile">{play(clip.url, f"Play Blizzard clip {clip.fdid}")}'
                f'<b>{esc(clip.label)}</b><small class="clip-note mono">{clip.fdid}</small></div>'
                for clip in clips
            )
            + "</div>"
        )
    else:
        tiles = f'<p class="muted small">{esc(empty)}</p>'
    return (
        '<div class="card soundboard"><header><h2 class="sc">Soundboard · Blizzard</h2>'
        f'<p class="muted small">{esc(title)}</p></header><section>{tiles}</section></div>'
    )


def facts(pairs: list[tuple[str, str]]) -> str:
    """Rows of a character sheet; values are trusted HTML. A row with no label is
    a list item, read left to right."""
    rows = "".join(
        f"<div><span>{esc(k)}</span><span>{v}</span></div>"
        if k
        else f"<div><span>{v}</span></div>"
        for k, v in pairs
    )
    return f'<div class="facts">{rows}</div>'


def voice_links(npc: Npc, infos: dict[str, VoiceInfo | None]) -> str:
    if not npc.voices:
        return '<p class="muted small">No voiced line yet.</p>'
    pairs = []
    for voice, rows in npc.voices.most_common():
        info = infos.get(voice)
        shared = len(info.speakers) if info else 0
        pairs.append(
            (
                "",
                (
                    f'<a class="mono" href="/voice/{quote(voice)}">{esc(voice)}</a> '
                    f'<span class="muted">{plural(rows, "line")} · shared by {plural(shared, "NPC")}</span>'
                ),
            )
        )
    return facts(pairs)


def npc_page(
    catalog: Catalog,
    npc: Npc,
    infos: dict[str, VoiceInfo | None],
    board_title: str,
    clips: list[Clip],
    portrait: int | None = None,
) -> str:
    """`portrait` is the display the picture shows when the NPC has none of its
    own: one of the same model (Forever's NPCs are captured with a model file)."""
    rows_total, rows = catalog.query(
        Filters(npc=str(npc.key), variants=True), limit=500
    )
    sexes = {"m": "male", "f": "female", "mf": "male and female"}.get(
        npc.sexes, "unknown"
    )
    portrait = npc.display_id or portrait
    if npc.display_id:
        model = f"display {npc.display_id}"
    elif npc.model_file_id and portrait:
        model = f"model file {npc.model_file_id} · picture from display {portrait}"
    elif npc.model_file_id:
        model = f"model file {npc.model_file_id}"
    else:
        model = "unknown"
    art = ""
    if portrait:
        art = (
            f'<div class="art"><img alt="" src="{model_image(portrait)}"'
            ' onerror="this.remove()"></div>'
        )
    wowhead = ""
    if npc.key > 0:
        wowhead = (
            f' · <a class="wh" target="_blank" rel="noopener" href="{WOWHEAD}/npc={npc.key}">'
            "wowhead</a>"
        )
    kind = "game object" if npc.is_object else "creature"
    sheet = (
        f'<div class="card pane">{art}<h1>{esc(npc.name or "Unknown")}</h1>'
        f'<p class="muted small">{kind} {npc.key}{wowhead}</p>'
        + facts(
            [
                ("Sex", esc(sexes)),
                ("Model", esc(model)),
                ("Zones", esc(", ".join(npc.zones[:4]) or "unknown")),
                ("Lines", f"{npc.lines:,}"),
            ]
        )
        + "</div>"
    )
    voices = (
        '<div class="card"><header><h2 class="sc">Voices</h2><p class="muted small">'
        "Tuning a voice changes every NPC who shares it.</p></header>"
        f"<section>{voice_links(npc, infos)}</section></div>"
    )
    board = soundboard(board_title, clips, "No Blizzard recordings known for this NPC.")
    more = ""
    if rows_total > 500:
        more = f'<p class="muted small">Showing 500 of {rows_total:,} rows.</p>'
    body = (
        f'<div class="sheet">{sheet}{voices}{board}</div>'
        f'<div><h2 class="sc">Lines</h2>{more}</div>{lines_table(catalog, rows)}'
    )
    return page(npc.name or f"NPC {npc.key}", body)


def voice_page(catalog: Catalog, info: VoiceInfo, names: dict[int, str]) -> str:
    if info.pick and info.borrowed_from:
        source = f"Picked by ear, borrowed from {info.borrowed_from}"
    elif info.pick:
        source = "Picked by ear"
    else:
        source = "Automatic reference (no clips picked by ear)"
    clips = [
        Clip(fdid, f"clip {i}", info.pick_build or "")
        for i, fdid in enumerate(info.pick, 1)
    ]
    if info.tuning:
        tuning = [(k, esc(v)) for k, v in info.tuning.items()]
    else:
        tuning = [("own row", '<span class="muted">none: the defaults apply</span>')]
    defaults = [
        (f"default {k}", f'<span class="muted">{esc(v)}</span>')
        for k, v in info.defaults.items()
    ]
    chain = (
        " → ".join(esc(v) for v in info.fallbacks) or '<span class="muted">none</span>'
    )
    pinned = ", ".join(
        f'<a href="/npc/{esc(k)}">{esc(k)}</a>' for k in info.pinned_speakers
    )
    settings = (
        '<div class="card"><header><h2 class="sc">Settings · as configured</h2>'
        '<p class="muted small">configs/tts.toml and configs/voices.toml; edit them in audition.'
        "</p></header><section>"
        + facts(
            [
                *tuning,
                *defaults,
                ("fallbacks", chain),
                ("pinned speakers", pinned or "none"),
            ]
        )
        + "</section></div>"
    )
    users = info.speakers.most_common()
    who = [
        (
            "",
            (
                f'<a href="/npc/{key}">{esc(names.get(key) or "Unknown")}</a> '
                f'<span class="muted">{plural(rows, "line")}</span>'
            ),
        )
        for key, rows in users[:50]
    ]
    if len(users) > 50:
        who.append(("", f'<span class="muted">and {len(users) - 50:,} more</span>'))
    usage = (
        '<div class="card"><header><h2 class="sc">Who uses it</h2><p class="muted small">'
        f"{plural(len(users), 'NPC')}, {plural(info.rows, 'voiced line')}</p></header>"
        f"<section>{facts(who or [('nobody yet', '')])}</section></div>"
    )
    sample = sorted(
        (
            line
            for line in catalog.lines
            if line.voice == info.name and voiced(line) and not is_variant(line)
        ),
        key=lambda line: -(line.duration or 0),
    )[:20]
    empty = "The reference is composed automatically from the voice's own recordings."
    body = (
        f'<div><h1>{esc(info.name)}</h1><p class="muted">{esc(source)}</p></div>'
        f'<div class="sheet">{settings}{usage}{soundboard(source, clips, empty)}</div>'
        f'<div><h2 class="sc">Longest lines in this voice</h2></div>{lines_table(catalog, sample)}'
    )
    return page(info.name, body, "/voices")


def voices_page(infos: dict[str, VoiceInfo], names: dict[int, str]) -> str:
    rows = ""
    for name, info in sorted(infos.items(), key=lambda kv: (-kv[1].rows, kv[0])):
        if info.borrowed_from:
            source = "borrowed"
        elif info.pick:
            source = "picked"
        else:
            source = "automatic"
        examples = ", ".join(
            esc(names.get(key) or str(key)) for key, _ in info.speakers.most_common(3)
        )
        tuned = "yes" if info.tuning else '<span class="muted">no</span>'
        rows += (
            f'<tr><td><a class="mono" href="/voice/{quote(name)}">{esc(name)}</a></td>'
            f'<td class="num"><a href="/lines?voice={quote(name)}&amp;variants=1">{info.rows:,}</a></td>'
            f'<td class="num">{len(info.speakers):,}</td>'
            f"<td>{badge(source, 'voiced' if source != 'automatic' else '')}</td>"
            f'<td>{tuned}</td><td class="text">{examples}</td></tr>'
        )
    body = (
        f'<div><h1>Voices</h1><p class="muted">{plural(len(infos), "voice")} read the packs. '
        "A voice is a reference clip built from Blizzard's own recordings and its Chatterbox "
        "settings; every NPC cast with it shares it.</p></div>"
        '<div class="card" style="padding-block:4px"><div class="table-container"><table class="table">'
        '<thead><tr><th>Voice</th><th class="num">Lines</th><th class="num">NPCs</th>'
        "<th>Clone source</th><th>Tuned</th><th>Examples</th></tr></thead>"
        f"<tbody>{rows}</tbody></table></div></div>"
    )
    return page("Voices", body, "/voices")
