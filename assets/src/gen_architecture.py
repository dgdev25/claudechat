#!/usr/bin/env python3
"""Architecture: two ways in, one resident engine, two ways out."""
from pathlib import Path

LIGHT = dict(paper="#f5f5f5", ink="#2d3142", muted="#4f5d75", soft="#7a8399",
             rule="rgba(45,49,66,0.12)", accent="#00d7b6", tint="rgba(0,215,182,0.08)",
             nodefill="#ffffff", ext="rgba(45,49,66,0.03)", extstroke="rgba(45,49,66,0.30)")
DARK = dict(paper="#07090b", ink="#f5f7f8", muted="#a9b0b7", soft="#c8ccce",
            rule="rgba(245,247,248,0.14)", accent="#00d7b6", tint="rgba(0,215,182,0.12)",
            nodefill="#101419", ext="rgba(245,247,248,0.04)", extstroke="rgba(245,247,248,0.30)")

W, H = 968, 388
SIDE_W, SIDE_H = 192, 72
ENG_X, ENG_Y, ENG_W, ENG_H = 376, 124, 216, 112


def box(x, y, w, h, tag, title, sub, c, style="plain"):
    fill = {"plain": c["nodefill"], "focal": c["tint"], "ext": c["ext"]}[style]
    stroke = {"plain": c["ink"], "focal": c["accent"], "ext": c["extstroke"]}[style]
    dash = ' stroke-dasharray="4,3"' if style == "ext" else ""
    cx = x + w // 2
    tw = 8 * len(tag) + 12
    return f"""
  <rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" fill="{c['paper']}"/>
  <rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" fill="{fill}" stroke="{stroke}" stroke-width="1"{dash}/>
  <rect x="{x + 12}" y="{y + 10}" width="{tw}" height="12" rx="2" fill="none" stroke="{stroke}" stroke-opacity="0.45" stroke-width="0.8"/>
  <text x="{x + 12 + tw // 2}" y="{y + 19}" fill="{stroke}" font-size="7" font-family="'Geist Mono', monospace" text-anchor="middle" letter-spacing="0.08em">{tag}</text>
  <text x="{cx}" y="{y + 44}" fill="{c['ink']}" font-size="12" font-weight="600" font-family="'Geist', sans-serif" text-anchor="middle">{title}</text>
  <text x="{cx}" y="{y + 62}" fill="{c['muted']}" font-size="9" font-family="'Geist Mono', monospace" text-anchor="middle">{sub}</text>"""


def elbow(x1, y1, x2, y2, c, accent=False):
    mid = (x1 + x2) // 2
    stroke, marker = (c["accent"], "arrow-accent") if accent else (c["muted"], "arrow")
    if y2 < y1:
        d = f"M {x1},{y1} H {mid - 8} Q {mid},{y1} {mid},{y1 - 8} V {y2 + 8} Q {mid},{y2} {mid + 8},{y2} H {x2 - 8}"
    elif y2 > y1:
        d = f"M {x1},{y1} H {mid - 8} Q {mid},{y1} {mid},{y1 + 8} V {y2 - 8} Q {mid},{y2} {mid + 8},{y2} H {x2 - 8}"
    else:
        d = f"M {x1},{y1} H {x2 - 8}"
    return f'  <path d="{d}" fill="none" stroke="{stroke}" stroke-width="1.2" marker-end="url(#{marker})"/>'


def label(x, y, text, c, w=None):
    w = w or 8 * len(text) + 8
    return (f'  <rect x="{x - w // 2}" y="{y - 9}" width="{w}" height="12" rx="2" fill="{c["paper"]}"/>\n'
            f'  <text x="{x}" y="{y}" fill="{c["soft"]}" font-size="8" font-family="\'Geist Mono\', monospace" '
            f'text-anchor="middle" letter-spacing="0.06em">{text}</text>')


def build(c, slug):
    nodes = (
        box(40, 64, SIDE_W, SIDE_H, "HOOK", "Claude Code", "speaks its replies", c)
        + box(40, 248, SIDE_W, SIDE_H, "CLI", "Terminal client", "you talk, it answers", c)
        + box(ENG_X, ENG_Y, ENG_W, ENG_H, "DAEMON", "Engine", "Whisper + Kokoro resident", c, "focal")
        + f'\n  <text x="484" y="{ENG_Y + 88}" fill="{c["soft"]}" font-size="8" font-family="\'Geist Mono\', monospace" text-anchor="middle">unix socket · 0600</text>'
        + box(736, 64, SIDE_W, SIDE_H, "REMOTE", "Claude", "your existing login", c, "ext")
        + box(736, 248, SIDE_W, SIDE_H, "AUDIO", "Speakers", "sentence by sentence", c)
    )
    arrows = "\n".join([
        elbow(232, 100, ENG_X, 156, c),
        elbow(232, 284, ENG_X, 212, c),
        elbow(ENG_X + ENG_W, 156, 736, 100, c, accent=True),
        elbow(ENG_X + ENG_W, 212, 736, 284, c),
    ])
    labels = "\n".join([
        label(304, 90, "REPLY TEXT", c),
        label(268, 274, "VOICE", c),
        label(664, 90, "PROMPT", c),
        label(700, 274, "AUDIO", c),
    ])
    legend = f"""
  <line x1="24" y1="340" x2="944" y2="340" stroke="{c['rule']}" stroke-width="0.8"/>
  <text x="24" y="358" fill="{c['muted']}" font-size="8" font-family="'Geist Mono', monospace" letter-spacing="0.14em">LEGEND</text>
  <rect x="104" y="349" width="12" height="10" rx="2" fill="{c['tint']}" stroke="{c['accent']}" stroke-width="1"/>
  <text x="124" y="358" fill="{c['muted']}" font-size="9" font-family="'Geist', sans-serif">one process, always warm</text>
  <rect x="308" y="349" width="12" height="10" rx="2" fill="{c['ext']}" stroke="{c['extstroke']}" stroke-width="1" stroke-dasharray="3,2"/>
  <text x="328" y="358" fill="{c['muted']}" font-size="9" font-family="'Geist', sans-serif">off your machine</text>
  <text x="500" y="358" fill="{c['soft']}" font-size="9" font-family="'Geist', sans-serif" font-style="italic">Either door reaches the same engine.</text>"""

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="100%" role="img" aria-labelledby="{slug}-title {slug}-desc">
  <title id="{slug}-title">How claudechat fits together</title>
  <desc id="{slug}-desc">Two entry points reach one resident engine over a private Unix socket: a Claude Code hook that hands over finished replies, and a terminal client you talk to. The engine keeps the Whisper and Kokoro models in memory, sends prompts to Claude using your existing login, and plays speech through the speakers.</desc>
  <defs>
    <marker id="arrow" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto"><polygon points="0 0, 8 3, 0 6" fill="{c['muted']}"/></marker>
    <marker id="arrow-accent" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto"><polygon points="0 0, 8 3, 0 6" fill="{c['accent']}"/></marker>
  </defs>
  <rect width="100%" height="100%" fill="{c['paper']}"/>
{arrows}
{labels}
{nodes}
{legend}
</svg>"""


out = Path("/data/dev/claudechat/assets")
for name, colours in (("architecture-light", LIGHT), ("architecture-dark", DARK)):
    (out / f"{name}.svg").write_text(build(colours, name))
    print(f"wrote {name}.svg")
