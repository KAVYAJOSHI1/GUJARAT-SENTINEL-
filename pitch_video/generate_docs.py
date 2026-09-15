#!/usr/bin/env python3
"""Generates COMPLETE_SYSTEM_VIDEO_TIMELINE.md and the voiceover .docx
from the REAL logged timestamps in full_demo_timeline.json, so the
documents always match the actual recorded video, not a plan."""
import json
import os

BASE = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(BASE, "full_demo_timeline.json")) as f:
    log = json.load(f)
with open(os.path.join(BASE, "narration_draft.json")) as f:
    narration = json.load(f)

timeline = log["timeline"]
total = log["totalDuration"]


def fmt(t):
    m = int(t // 60)
    s = t - m * 60
    return f"{m}:{s:05.2f}"


def fmt_short(t):
    m = int(t // 60)
    s = int(t % 60)
    return f"{m:02d}:{s:02d}"


# ---------- 1. Timeline markdown ----------
lines = []
lines.append("# SENTINEL — Complete System Video Timeline\n")
lines.append(
    f"Generated directly from the actual recorded run's logged timestamps "
    f"(`full_demo_timeline.json`) — every number below matches "
    f"`COMPLETE_SENTINEL_SYSTEM_DEMO.mp4` exactly, not a plan.\n"
)
lines.append(
    "| # | Start | End | Duration | Page | Route | Action | What Viewer Sees | Purpose | Voiceover Topic |"
)
lines.append("|---|---|---|---|---|---|---|---|---|---|")

for i, sec in enumerate(timeline, 1):
    name = sec["name"]
    dur = sec["end"] - sec["start"]
    n = narration.get(name, {})
    on_screen = n.get("onScreen", "—")
    say_short = (n.get("say", "")[:70] + "…") if len(n.get("say", "")) > 70 else n.get("say", "")
    lines.append(
        f"| {i} | {fmt_short(sec['start'])} | {fmt_short(sec['end'])} | {dur:.1f}s | "
        f"{name} | `{sec['route']}` | Navigate + interact | {on_screen} | {sec['purpose']} | {say_short} |"
    )

lines.append(f"\n**TOTAL VIDEO DURATION: {fmt_short(total)} ({total:.1f}s)**\n")

if log.get("sectionErrors"):
    lines.append("## Non-fatal recording notes\n")
    lines.append(
        "The following sub-steps did not find their expected element during recording "
        "(e.g. a hover target) and were skipped automatically without interrupting the "
        "section or the recording; the section's page navigation and core content still "
        "played and is on screen for its full duration:\n"
    )
    for e in log["sectionErrors"]:
        lines.append(f"- **{e['name']}**: {e['error']}")
else:
    lines.append("## Recording notes\n\nNo sub-step errors occurred during recording.\n")

lines.append(f"\nConsole errors observed during the entire recording: **{len(log.get('consoleErrors', []))}**\n")

with open(os.path.join(BASE, "COMPLETE_SYSTEM_VIDEO_TIMELINE.md"), "w") as f:
    f.write("\n".join(lines))
print("Wrote COMPLETE_SYSTEM_VIDEO_TIMELINE.md")


# ---------- 2. DOCX voiceover ----------
from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH

doc = Document()

title = doc.add_heading("SENTINEL — Complete System Video Voiceover Script", level=0)

meta = doc.add_paragraph()
meta.add_run(
    f"Total video duration: {fmt_short(total)}  |  Resolution: 1920×1080  |  FPS: 30\n"
    f"Timestamps below are generated directly from the actual recorded run and match "
    f"COMPLETE_SENTINEL_SYSTEM_DEMO.mp4 exactly."
).italic = True

doc.add_paragraph(
    "Read at a natural, confident, professional pace. This is a real product being "
    "demonstrated for a police/government hackathon jury — explain what the viewer is "
    "seeing and why it matters, not implementation detail, and don't read UI labels verbatim."
)

for i, sec in enumerate(timeline, 1):
    name = sec["name"]
    dur = sec["end"] - sec["start"]
    n = narration.get(name, {})

    doc.add_heading(f"[{fmt_short(sec['start'])} – {fmt_short(sec['end'])}]  {name.upper()}", level=2)

    p = doc.add_paragraph()
    p.add_run("ROUTE: ").bold = True
    p.add_run(sec["route"])
    p.add_run(f"   |   DURATION: {dur:.1f}s")

    p = doc.add_paragraph()
    p.add_run("WHAT IS ON SCREEN: ").bold = True
    p.add_run(n.get("onScreen", ""))

    p = doc.add_paragraph()
    p.add_run("WHAT I SHOULD SAY:").bold = True
    quote = doc.add_paragraph()
    quote.paragraph_format.left_indent = Inches(0.3)
    run = quote.add_run(f"“{n.get('say', '')}”")
    run.italic = True

    if n.get("keyPoints"):
        p = doc.add_paragraph()
        p.add_run("KEY POINTS TO EXPLAIN:").bold = True
        for kp in n["keyPoints"]:
            b = doc.add_paragraph(style="List Bullet")
            b.add_run(kp)

    doc.add_paragraph()  # spacer

doc.save(os.path.join(BASE, "SENTINEL_COMPLETE_SYSTEM_VIDEO_VOICEOVER.docx"))
print("Wrote SENTINEL_COMPLETE_SYSTEM_VIDEO_VOICEOVER.docx")
