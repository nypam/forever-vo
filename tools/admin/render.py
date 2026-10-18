"""The admin's look, ported from Talk2Me's admin (pipeline/admin.py in
nypam/talk2me): Basecoat (shadcn/ui as plain CSS) from a CDN, a dark theme with
a gold accent, round play buttons that share one <audio>.

Every value put into a page goes through `esc`.
"""

from __future__ import annotations

import html
import json

BASECOAT = "https://cdn.jsdelivr.net/npm/basecoat-css@1.0.2/dist/basecoat.cdn.min.css"
WOWHEAD = "https://www.wowhead.com/forever"
NAV = (("Dashboard", "/"), ("Lines", "/lines"), ("Voices", "/voices"))

CSS = """
.dark{--primary:oklch(0.84 0.16 84);--primary-foreground:oklch(0.22 0.04 84);--ring:oklch(0.84 0.16 84 / .45);
  --background:oklch(0.16 0.02 265);--card:oklch(0.19 0.02 265);--border:oklch(0.84 0.16 84 / .16)}
html{background:var(--background)}
body{background:var(--background) radial-gradient(ellipse 1100px 600px at 20% -100px,oklch(0.32 0.07 265 / .6),transparent) no-repeat;min-height:100vh}
a:not(.btn,.badge,.brand,[role=tab]){color:oklch(0.78 0.11 240)}a:not(.btn,.badge,[role=tab]):hover{text-decoration:underline}
.topbar{position:sticky;top:0;z-index:10;border-bottom:1px solid var(--border);backdrop-filter:blur(10px);background:color-mix(in oklab,var(--background) 80%,transparent)}
.topbar>div,.shell{max-width:1600px;margin:0 auto;padding-inline:24px}
.topbar>div{display:flex;align-items:center;gap:4px;height:56px}
.brand{display:flex;align-items:center;gap:8px;font-weight:600;margin-right:20px}
.brand i{width:10px;height:10px;border-radius:50%;background:var(--primary);box-shadow:0 0 10px var(--primary)}
.shell{padding-block:28px;display:grid;gap:20px}
h1{font-size:1.6rem;font-weight:600;letter-spacing:-.02em}
.muted{color:var(--muted-foreground)}.small{font-size:12px}.mono{font-family:ui-monospace,Menlo,monospace;font-size:12px}
.row{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.stack{display:grid;gap:6px;justify-items:start}
.stats{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:12px}
.stat b{display:block;font-size:1.6rem;font-weight:600;font-variant-numeric:tabular-nums;color:var(--primary)}
.stat a{text-decoration:none!important}.stat span{font-size:13px;color:var(--muted-foreground)}
.notice{border:1px solid oklch(0.8 0.15 80 / .6);color:oklch(0.85 0.12 80);border-radius:10px;padding:10px 14px;font-size:13px}
.filters .input:not([type=checkbox]),.filters .select{width:auto}
.table td{vertical-align:top}.table td.text{max-width:520px;white-space:normal;line-height:1.5}
.table.lines{table-layout:fixed;min-width:1100px}.table.lines td{white-space:normal;overflow-wrap:anywhere}
.table tr[data-kind=accept] td:first-child{box-shadow:inset 3px 0 oklch(0.84 0.16 84)}.table tr[data-kind=progress] td:first-child{box-shadow:inset 3px 0 var(--muted-foreground)}
.table tr[data-kind=complete] td:first-child{box-shadow:inset 3px 0 oklch(0.8 0.2 145)}.table tr[data-kind=gossip] td:first-child{box-shadow:inset 3px 0 oklch(0.65 0.17 250)}
.table tr[data-kind=book] td:first-child{box-shadow:inset 3px 0 oklch(0.7 0.12 30)}
.table td.num,.table th.num{text-align:right;font-variant-numeric:tabular-nums}
.dot{display:inline-block;width:7px;height:7px;border-radius:50%;margin-right:5px;vertical-align:middle;background:var(--muted-foreground)}
.dot.voiced{background:oklch(0.75 0.18 150)}.dot.text_only{background:oklch(0.8 0.15 80)}.dot.missing{background:var(--destructive)}
.dot.yours{background:oklch(0.78 0.11 240)}.dot.variant{background:oklch(0.68 0.17 295)}
.who{display:flex;gap:10px;align-items:flex-start}
.avatar.npc{flex:none;width:44px;height:44px;overflow:hidden;border-radius:50%;background:radial-gradient(circle at 50% 40%,oklch(0.38 0.05 265),oklch(0.18 0.01 265));box-shadow:0 0 0 2px oklch(0.84 0.16 84 / .55)}
.avatar.npc.bust>img{transform:scale(2);transform-origin:50% 3%}
.wh{font-size:12px;color:oklch(0.75 0.17 55)}.wh:before{content:"\\2197  "}
.bar{display:flex;height:10px;min-width:140px;border-radius:999px;overflow:hidden;background:var(--muted)}
.bar>span{background:oklch(0.75 0.18 150)}.bar>span.yours{background:oklch(0.78 0.11 240)}
.play{flex:none;width:30px;height:30px;border-radius:50%;display:inline-grid;place-items:center;border:1px solid var(--border);background:var(--secondary);color:var(--foreground);cursor:pointer}
.play svg{width:11px;height:11px;margin-left:2px;fill:currentColor}
.play.playing svg{display:none}.play.playing:before{content:"";width:10px;height:11px;border-inline:3px solid}
.play:hover{border-color:var(--primary)}.play:focus-visible{outline:2px solid var(--ring);outline-offset:2px}
.play.yours{border-color:oklch(0.78 0.11 240 / .7)}
.play.broken{opacity:.35;cursor:not-allowed}
.players{display:grid;gap:6px}.players .row{flex-wrap:nowrap}
/* NPC and voice pages: character sheet */
.sheet{display:grid;grid-template-columns:300px minmax(0,1fr) 420px;gap:20px;align-items:start}
@media(max-width:1280px){.sheet{grid-template-columns:280px minmax(0,1fr)}.sheet>.soundboard{grid-column:1/-1}}
.sc{font-variant:small-caps;letter-spacing:.08em;font-size:14px!important;color:oklch(0.84 0.16 84 / .9);font-weight:600!important}
.pane{padding-top:0;gap:0;overflow:hidden}
.pane .art{height:220px;display:grid;place-items:center;border-bottom:1px solid var(--border);background:radial-gradient(circle at 50% 55%,oklch(0.36 0.07 265),oklch(0.13 0.02 265) 72%)}
.pane .art img{max-height:200px;max-width:100%}
.pane h1{font-family:Georgia,"Iowan Old Style",serif;font-size:1.9rem;color:oklch(0.9 0.12 84);padding:16px 18px 2px}
.pane>p{padding:0 18px 8px}
.facts{display:grid;padding:4px 18px 16px}
.facts div{display:flex;justify-content:space-between;gap:12px;padding:7px 0;border-bottom:1px dashed var(--border);font-size:13px}
.facts div span:first-child{color:var(--muted-foreground)}
.tiles{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}
.tile{position:relative;padding:14px 6px 10px;border:1px solid var(--border);border-radius:12px;display:grid;justify-items:center;gap:4px;background:oklch(0.21 0.03 265)}
.tile .play{width:36px;height:36px}.tile b{font-size:13px;font-weight:500;text-transform:capitalize}.tile small{font-size:11px;color:var(--muted-foreground);min-height:14px}
"""

# Every .play button plays through one shared <audio>, so only one clip sounds at a
# time. A button carries one file (data-src) or a line's parts in order (data-srcs,
# a JSON list), which play back to back as the addon plays them. A clip that fails
# to load (a Blizzard clip while offline) marks its button.
PLAYER_JS = """
const player = new Audio();
let current = null, queue = [];
const mark = on => current && current.classList.toggle("playing", on);
const next = () => {
  const src = queue.shift();
  if (!src) { mark(false); return; }
  player.src = src;
  player.play().catch(e => { if (e.name !== "AbortError") mark(false); });
};
document.addEventListener("click", e => {
  const btn = e.target.closest(".play[data-src], .play[data-srcs]");
  if (!btn || btn.classList.contains("broken")) return;
  e.preventDefault();
  if (btn === current && !player.paused) { queue = []; player.pause(); return; }
  mark(false);
  current = btn;
  queue = btn.dataset.srcs ? JSON.parse(btn.dataset.srcs) : [btn.dataset.src];
  next();
});
player.onplay = () => mark(true);
player.onpause = () => { if (!queue.length) mark(false); };
player.onended = next;
player.onerror = () => {
  if (!current) return;
  current.classList.add("broken");
  current.title = "Clip not available offline";
  const note = current.parentElement && current.parentElement.querySelector(".clip-note");
  if (note) note.textContent = "clip not available offline";
  queue = [];
  mark(false);
};
"""

PLAY_ICON = (
    '<svg viewBox="0 0 10 10" aria-hidden="true"><path d="M1 0L10 5L1 10z"/></svg>'
)


def esc(value: object) -> str:
    return html.escape("" if value is None else str(value))


def play(srcs: list[str] | str, label: str, css: str = "") -> str:
    """A round play button: one file, or a line's parts played in order."""
    files = [srcs] if isinstance(srcs, str) else srcs
    source = (
        f'data-src="{esc(files[0])}"'
        if len(files) == 1
        else f'data-srcs="{esc(json.dumps(files))}"'
    )
    return (
        f'<button type="button" class="play {css}" {source} aria-label="{esc(label)}"'
        f' title="{esc(label)}">{PLAY_ICON}</button>'
    )


def badge(label: str, dot: str = "") -> str:
    return (
        f'<span class="badge" data-variant="outline"><i class="dot {esc(dot or label)}"></i>'
        f"{esc(label)}</span>"
    )


def model_image(display_id: int) -> str:
    """Wowhead's pre-rendered thumbnail of a creature display."""
    return (
        "https://wow.zamimg.com/modelviewer/classic/webthumbs/npc/"
        f"{display_id & 255}/{display_id}.webp"
    )


def avatar(display_id: int | None) -> str:
    if not display_id:
        return ""
    return (
        f'<span class="avatar npc bust"><img loading="lazy" alt="" src="{model_image(display_id)}"'
        ' onerror="this.parentNode.remove()"></span>'
    )


def duration(seconds: float | None) -> str:
    if seconds is None:
        return ""
    seconds = round(seconds)
    return f"{seconds // 60}:{seconds % 60:02d}"


def page(title: str, body: str, here: str = "") -> str:
    links = "".join(
        f'<a class="btn" data-size="sm" data-variant="{"secondary" if href == here else "ghost"}"'
        f' href="{href}">{label}</a>'
        for label, href in NAV
    )
    return f"""<!doctype html><html lang="en" class="dark"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{esc(title)} · Forever Voiceover admin</title>
<link rel="stylesheet" href="{BASECOAT}"><style>{CSS}</style></head><body>
<nav class="topbar"><div><a class="brand" href="/"><i></i>Forever Voiceover</a>{links}</div></nav>
<main class="shell">{body}</main><script>{PLAYER_JS}</script></body></html>"""
