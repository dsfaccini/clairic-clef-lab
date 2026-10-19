#!/usr/bin/env python3
"""Render deterministic social media cards and a short replay animation."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from clairic_clef_lab.cli import IntakeCard

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
PAPER = "#F5F0E6"
INK = "#17212B"
BLUE = "#2654D8"
RED = "#DB513F"
MUTED = "#716F6A"
RULE = "#C9C1B5"
W, H = 1600, 1200


def font(
    size: int, mono: bool = False, bold: bool = False
) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    if mono:
        paths = [
            "/System/Library/Fonts/Menlo.ttc",
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        ]
    elif bold:
        paths = [
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ]
    else:
        paths = [
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]
    for path in paths:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size=size)


def make_card(card: IntakeCard) -> Image.Image:
    source = card.source_state
    span = card.verified_target_span
    target = card.candidate.target
    effective = card.field_evidence["effective_date"]
    probabilities = card.operation_evidence.probabilities
    ordered = sorted(probabilities.items(), key=lambda item: item[1], reverse=True)
    assert span is not None
    assert target is not None
    assert isinstance(effective.guess, str)
    assert effective.p_null is not None

    im = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(im)
    serif = font(52, bold=True)
    sans = font(24)
    small = font(18)
    mono = font(25, mono=True)
    target_font = font(20, mono=True)
    d.text((82, 60), "CLAIRIC + CLEF LAB", font=small, fill=BLUE)
    d.text((82, 98), "A missing date stays missing.", font=serif, fill=INK)
    d.line((82, 180, 1518, 180), fill=RULE, width=2)

    d.text((82, 215), "SOURCE TEXT  ·  FICTIONAL AMENDMENT", font=small, fill=MUTED)
    d.rounded_rectangle((82, 252, 1518, 370), radius=8, fill="#ECE5D9")
    prefix = source[: span[0]]
    before = source[span[0] : span[1]]
    suffix = source[span[1] :]
    prefix_width = d.textlength(prefix, font=sans)
    target_width = d.textlength(before, font=sans)
    d.text((112, 292), prefix, font=sans, fill=INK)
    target_x = 112 + prefix_width
    d.rounded_rectangle(
        (target_x - 3, 287, target_x + target_width + 1, 324), radius=4, fill="#DCE4FA"
    )
    d.text((target_x, 292), before, font=sans, fill=BLUE)
    d.text((target_x + target_width + 2, 292), suffix, font=sans, fill=INK)
    d.text(
        (82, 387),
        f"Verified source offsets  [{span[0]}, {span[1]}]",
        font=small,
        fill=BLUE,
    )

    d.text((82, 435), "CLAIRIC  /  EXTRACTED CANDIDATE", font=small, fill=MUTED)
    candidate = card.candidate
    rows = [
        ("target", target),
        ("article_number", str(candidate.article_number)),
        (
            "effective_date",
            "null"
            if candidate.effective_date is None
            else str(candidate.effective_date),
        ),
        (
            "publication_date",
            "null"
            if candidate.publication_date is None
            else str(candidate.publication_date),
        ),
    ]
    y = 476
    for key, value in rows:
        d.line((82, y + 42, 730, y + 42), fill=RULE, width=1)
        d.text((90, y), key, font=small, fill=MUTED)
        color = RED if value == "null" else INK
        value_font = target_font if key == "target" else mono
        d.text((350, y - 2), value, font=value_font, fill=color)
        y += 54
    d.text(
        (90, 704),
        f"separate model guess  {effective.guess}   ·   p_null {effective.p_null:.7f}",
        font=small,
        fill=MUTED,
    )

    d.line((782, 435, 782, 735), fill=RULE, width=2)
    d.text((830, 435), "CLEF  /  MODEL PROBABILITY", font=small, fill=MUTED)
    d.text((830, 470), f"operation = {card.operation.value}", font=mono, fill=INK)
    y = 526
    for label, value in ordered:
        d.text((830, y), label, font=small, fill=INK)
        d.rounded_rectangle((1030, y + 4, 1420, y + 24), radius=7, fill="#E1DACE")
        fill = BLUE if label != card.operation.value else RED
        d.rounded_rectangle(
            (1030, y + 4, 1030 + max(3, int(390 * value)), y + 24), radius=7, fill=fill
        )
        d.text((1440, y - 3), f"{value * 100:.2f}%", font=small, fill=INK)
        y += 43

    d.rounded_rectangle((82, 780, 1518, 1084), radius=10, fill="#F0DCD5")
    d.text((112, 810), "NEEDS REVIEW", font=font(30, bold=True), fill=RED)
    for index, reason in enumerate(card.review.reasons):
        d.text((112, 864 + index * 49), reason, font=sans, fill=INK)
    d.line((82, 1122, 1518, 1122), fill=RULE, width=2)
    assert card.run is not None
    assert card.run.recorded_on is not None
    d.text(
        (82, 1144),
        f"Captured {card.run.recorded_on}  ·  fictional document  ·  legal effect/applicability not determined",
        font=small,
        fill=MUTED,
    )
    d.text(
        (1225, 1144), "CLI replay visualized · fictional example", font=small, fill=INK
    )
    return im


def make_animation(card_data: IntakeCard, card: Image.Image, gif_path: Path) -> None:
    source = card_data.source_state
    target = card_data.candidate.target
    target_span = card_data.verified_target_span
    effective = card_data.field_evidence["effective_date"]
    publication = card_data.candidate.publication_date
    effective_date = card_data.candidate.effective_date
    probabilities = card_data.operation_evidence.probabilities
    selected_operation = card_data.operation.value
    assert target is not None
    assert target_span is not None
    assert isinstance(effective.guess, str)
    assert effective.p_null is not None
    frames: list[Image.Image] = []
    base = Image.new("RGB", (W, H), PAPER)
    label = font(20)
    headline = font(56, bold=True)
    sans = font(30)
    mono = font(32, mono=True)
    # 2 seconds: source text and verified target.
    for i in range(2):
        frame = base.copy()
        d = ImageDraw.Draw(frame)
        d.text(
            (82, 52),
            "Visualization of CLI replay · fictional example",
            font=label,
            fill=MUTED,
        )
        d.text((82, 190), "A source with no date.", font=headline, fill=INK)
        d.rounded_rectangle((82, 360, 1518, 610), radius=12, fill="#ECE5D9")
        d.text((120, 410), source, font=sans, fill=INK)
        d.rounded_rectangle(
            (120, 470, 120 + d.textlength(target, font=sans) + 24, 520),
            radius=5,
            fill="#DCE4FA",
        )
        d.text((132, 478), target, font=sans, fill=BLUE)
        d.text(
            (82, 670),
            f"Verified target  ·  source offsets [{target_span[0]}, {target_span[1]}]",
            font=label,
            fill=BLUE,
        )
        d.line((82, 760, 1518, 760), fill=BLUE, width=3)
        d.ellipse((760 + i * 18, 750, 780 + i * 18, 770), fill=BLUE)
        frames.append(frame)
    # 3 seconds: accepted fields remain null; guess shown separately.
    for i in range(3):
        frame = base.copy()
        d = ImageDraw.Draw(frame)
        d.text(
            (82, 52),
            "Visualization of CLI replay · fictional example",
            font=label,
            fill=MUTED,
        )
        d.text((82, 155), "Clairic candidate", font=headline, fill=INK)
        d.text((120, 310), "effective_date", font=label, fill=MUTED)
        d.text(
            (570, 295),
            "null" if effective_date is None else str(effective_date),
            font=mono,
            fill=RED,
        )
        d.text((120, 390), "publication_date", font=label, fill=MUTED)
        d.text(
            (570, 375),
            "null" if publication is None else str(publication),
            font=mono,
            fill=RED,
        )
        d.line((82, 470, 1518, 470), fill=RULE, width=2)
        d.text((120, 530), "separate model guess", font=label, fill=MUTED)
        d.text((570, 515), effective.guess, font=mono, fill=INK)
        d.text((120, 590), "p_null", font=label, fill=MUTED)
        d.text((570, 575), f"{effective.p_null:.7f}", font=mono, fill=BLUE)
        d.line((82, 760, 1518, 760), fill=BLUE, width=3)
        d.ellipse((760 + (i % 2) * 18, 750, 780 + (i % 2) * 18, 770), fill=BLUE)
        frames.append(frame)
    # 3 seconds: sorted native probability bars.
    ordered = sorted(probabilities.items(), key=lambda x: x[1], reverse=True)
    for i in range(3):
        frame = base.copy()
        d = ImageDraw.Draw(frame)
        d.text(
            (82, 52),
            "Visualization of CLI replay · fictional example",
            font=label,
            fill=MUTED,
        )
        d.text(
            (82, 155), f"Clef operation: {selected_operation}", font=headline, fill=INK
        )
        d.text((82, 245), "model probability", font=label, fill=MUTED)
        y = 340
        for name, value in ordered:
            d.text((120, y), name, font=sans, fill=INK)
            d.rounded_rectangle((470, y + 3, 1380, y + 38), radius=10, fill="#E1DACE")
            d.rounded_rectangle(
                (470, y + 3, 470 + max(4, int(910 * value)), y + 38),
                radius=10,
                fill=RED if name == selected_operation else BLUE,
            )
            d.text((1410, y), f"{value * 100:.2f}%", font=label, fill=INK)
            y += 82
        d.line((82, 760, 1518, 760), fill=BLUE, width=3)
        d.ellipse((760 + (i % 2) * 18, 750, 780 + (i % 2) * 18, 770), fill=BLUE)
        frames.append(frame)
    # 4 seconds: final card held for the close.
    frames.extend([card.copy() for _ in range(4)])
    palette_frames = [
        f.convert("P", palette=Image.Palette.ADAPTIVE, colors=128) for f in frames
    ]
    palette_frames[0].save(
        gif_path,
        save_all=True,
        append_images=palette_frames[1:],
        duration=1000,
        loop=0,
        optimize=True,
        disposal=2,
    )


def main() -> None:
    ASSETS.mkdir(exist_ok=True)
    cli = shutil.which("clairic-clef-lab")
    if cli is None:
        raise SystemExit(
            "clairic-clef-lab must be available on PATH; run through uv from the repository root."
        )
    replay = subprocess.run(
        [cli, "--replay", "missing-date"], check=True, capture_output=True, text=True
    )
    card_data = IntakeCard.model_validate_json(replay.stdout)
    card = make_card(card_data)
    card.save(ASSETS / "intake-card.png", optimize=True)
    make_animation(card_data, card, ASSETS / "replay.gif")
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-i",
                str(ASSETS / "replay.gif"),
                "-movflags",
                "+faststart",
                str(ASSETS / "replay.mp4"),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    print("Rendered assets/intake-card.png (1600x1200), assets/replay.gif (12 seconds)")
    if ffmpeg:
        print("Rendered assets/replay.mp4")


if __name__ == "__main__":
    main()
