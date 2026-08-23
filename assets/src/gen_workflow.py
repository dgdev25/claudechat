#!/usr/bin/env python3
"""Generate the 'one spoken turn' workflow diagram, light and dark.

One geometry definition, two skins, so the variants cannot drift apart.
Palette: diagram-design myportfolio-site profile (teal accent).
"""
from pathlib import Path

LIGHT = dict(paper="#f5f5f5", paper2="#ececec", ink="#2d3142", muted="#4f5d75",
             soft="#7a8399", rule="rgba(45,49,66,0.12)", accent="#00d7b6",
             tint="rgba(0,215,182,0.08)", nodefill="#ffffff",
             zone="rgba(45,49,66,0.02)", zoneline="rgba(45,49,66,0.20)")
DARK = dict(paper="#07090b", paper2="#101419", ink="#f5f7f8", muted="#a9b0b7",
            soft="#c8ccce", rule="rgba(245,247,248,0.14)", accent="#00d7b6",
            tint="rgba(0,215,182,0.12)", nodefill="#101419",
            zone="rgba(245,247,248,0.03)", zoneline="rgba(245,247,248,0.24)")

W, H = 968, 400
NODE_W, NODE_H, PITCH, X0, ROW_Y = 152, 80, 184, 40, 212
CY = ROW_Y + NODE_H // 2                     # 252

STEPS = [
    ("You speak", "hold a key", "1"),
    ("Whisper", "local speech to text", "2"),
    ("Strip &amp; chunk", "no code read aloud", "3"),
    ("Kokoro", "local text to speech", "4"),
    ("Speakers", "first words", "5"),
]


def node(x, title, sub, tag, c, focal=False):
    fill = c["tint"] if focal else c["nodefill"]
    stroke = c["accent"] if focal else c["ink"]
    cx = x + NODE_W // 2
    return f"""
  <rect x="{x}" y="{ROW_Y}" width="{NODE_W}" height="{NODE_H}" rx="6" fill="{c['paper']}"/>
  <rect x="{x}" y="{ROW_Y}" width="{NODE_W}" height="{NODE_H}" rx="6" fill="{fill}" stroke="{stroke}" stroke-width="1"/>
  <rect x="{x + 12}" y="{ROW_Y + 10}" width="16" height="12" rx="2" fill="none" stroke="{stroke}" stroke-opacity="0.40" stroke-width="0.8"/>
  <text x="{x + 20}" y="{ROW_Y + 19}" fill="{stroke}" fill-opacity="0.85" font-size="7" font-family="'Geist Mono', monospace" text-anchor="middle" letter-spacing="0.08em">{tag}</text>
  <text x="{cx}" y="{ROW_Y + 46}" fill="{c['ink']}" font-size="12" font-weight="600" font-family="'Geist', sans-serif" text-anchor="middle">{title}</text>
  <text x="{cx}" y="{ROW_Y + 64}" fill="{c['muted']}" font-size="9" font-family="'Geist Mono', monospace" text-anchor="middle">{sub}</text>"""


def build(c, slug):
    xs = [X0 + i * PITCH for i in range(5)]
    claude_x, claude_y, claude_w, claude_h = 384, 64, 200, 72

    arrows = []
    # straight horizontal hops between adjacent local steps (shared y — plain lines)
    for a, b in ((0, 1), (2, 3), (3, 4)):
        arrows.append(
            f'  <line x1="{xs[a] + NODE_W}" y1="{CY}" x2="{xs[b] - 8}" y2="{CY}" '
            f'stroke="{c["muted"]}" stroke-width="1.2" marker-end="url(#arrow)"/>')
    # Whisper -> Claude: leaves the machine. Exits the TOP so it never crosses
    # the Strip node, then transits above the row and rises into Claude's bottom.
    arrows.append(
        f'  <path d="M 300,{ROW_Y} V 176 Q 300,168 308,168 H 432 Q 440,168 440,160 V {claude_y + claude_h + 8}" '
        f'fill="none" stroke="{c["accent"]}" stroke-width="1.2" marker-end="url(#arrow-accent)"/>')
    # Claude -> Strip: straight back down into the machine
    arrows.append(
        f'  <path d="M 528,{claude_y + claude_h} V {ROW_Y - 8}" fill="none" '
        f'stroke="{c["accent"]}" stroke-width="1.2" marker-end="url(#arrow-accent)"/>')

    labels = f"""
  <rect x="330" y="146" width="52" height="12" rx="2" fill="{c['paper']}"/>
  <text x="356" y="155" fill="{c['soft']}" font-size="8" font-family="'Geist Mono', monospace" text-anchor="middle" letter-spacing="0.06em">YOUR WORDS</text>
  <rect x="540" y="150" width="56" height="12" rx="2" fill="{c['paper']}"/>
  <text x="568" y="159" fill="{c['soft']}" font-size="8" font-family="'Geist Mono', monospace" text-anchor="middle" letter-spacing="0.06em">SENTENCES</text>"""

    nodes = "".join(node(x, t, s, g, c) for x, (t, s, g) in zip(xs, STEPS))
    claude = f"""
  <rect x="{claude_x}" y="{claude_y}" width="{claude_w}" height="{claude_h}" rx="6" fill="{c['paper']}"/>
  <rect x="{claude_x}" y="{claude_y}" width="{claude_w}" height="{claude_h}" rx="6" fill="{c['tint']}" stroke="{c['accent']}" stroke-width="1"/>
  <rect x="{claude_x + 12}" y="{claude_y + 10}" width="36" height="12" rx="2" fill="none" stroke="{c['accent']}" stroke-opacity="0.50" stroke-width="0.8"/>
  <text x="{claude_x + 30}" y="{claude_y + 19}" fill="{c['accent']}" font-size="7" font-family="'Geist Mono', monospace" text-anchor="middle" letter-spacing="0.08em">REMOTE</text>
  <text x="484" y="{claude_y + 44}" fill="{c['ink']}" font-size="12" font-weight="600" font-family="'Geist', sans-serif" text-anchor="middle">Claude</text>
  <text x="484" y="{claude_y + 60}" fill="{c['muted']}" font-size="9" font-family="'Geist Mono', monospace" text-anchor="middle">claude -p · your login</text>"""

    zone = f"""
  <rect x="24" y="180" width="920" height="136" rx="8" fill="{c['zone']}" stroke="{c['zoneline']}" stroke-width="1" stroke-dasharray="4,4"/>
  <rect x="40" y="174" width="132" height="12" rx="2" fill="{c['paper']}"/>
  <text x="44" y="183" fill="{c['soft']}" font-size="8" font-family="'Geist Mono', monospace" letter-spacing="0.14em">ON YOUR MACHINE</text>"""

    legend = f"""
  <line x1="24" y1="344" x2="944" y2="344" stroke="{c['rule']}" stroke-width="0.8"/>
  <text x="24" y="362" fill="{c['muted']}" font-size="8" font-family="'Geist Mono', monospace" letter-spacing="0.14em">LEGEND</text>
  <rect x="104" y="353" width="12" height="10" rx="2" fill="{c['tint']}" stroke="{c['accent']}" stroke-width="1"/>
  <text x="124" y="362" fill="{c['muted']}" font-size="9" font-family="'Geist', sans-serif">leaves your machine</text>
  <rect x="284" y="353" width="12" height="10" rx="2" fill="{c['nodefill']}" stroke="{c['ink']}" stroke-width="1"/>
  <text x="304" y="362" fill="{c['muted']}" font-size="9" font-family="'Geist', sans-serif">runs locally on the CPU</text>
  <text x="500" y="362" fill="{c['soft']}" font-size="9" font-family="'Geist', sans-serif" font-style="italic">Speech starts while Claude is still writing.</text>"""

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="100%" role="img" aria-labelledby="{slug}-title {slug}-desc">
  <title id="{slug}-title">How one spoken turn works in claudechat</title>
  <desc id="{slug}-desc">A voice turn: your speech is transcribed locally by Whisper, the text goes out to Claude through the Claude Code CLI, and the streamed reply is stripped of code, split into sentences, spoken by a local Kokoro model, and played through the speakers. Every step except the Claude call runs on your own machine.</desc>
  <defs>
    <marker id="arrow" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto"><polygon points="0 0, 8 3, 0 6" fill="{c['muted']}"/></marker>
    <marker id="arrow-accent" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto"><polygon points="0 0, 8 3, 0 6" fill="{c['accent']}"/></marker>
  </defs>
  <rect width="100%" height="100%" fill="{c['paper']}"/>
{zone}
{chr(10).join(arrows)}
{labels}
{nodes}
{claude}
{legend}
</svg>"""


out = Path("/data/dev/claudechat/assets")
for name, colours in (("workflow-light", LIGHT), ("workflow-dark", DARK)):
    (out / f"{name}.svg").write_text(build(colours, name))
    print(f"wrote {name}.svg")
