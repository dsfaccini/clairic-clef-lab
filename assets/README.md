# Demo media assets

`cover.png` is the unaltered built-in imagegen output (1672 × 941). `intake-card.png`, `replay.gif`, and `replay.mp4` are deterministic renders of the actual `clairic-clef-lab --replay missing-date` JSON.

Regenerate the card and replay animation from the repository root:

```sh
uv run --with pillow python scripts/render_media.py
```

The renderer validates the CLI output as an `IntakeCard`. Replay reads only the checked-in fictional capture and makes no model requests. The GIF is 12 seconds: 2 seconds of source and verified target, 3 seconds of extracted fields and separate guess, 3 seconds of Clef probabilities, then 4 seconds holding the `needs_review` card. When `ffmpeg` is available, the renderer also writes `replay.mp4` from that GIF.

The cover was generated with the built-in Codex `image_gen` tool and copied without alteration. It is a complete generated image; the card and animation are composed by `scripts/render_media.py`.

Final cover prompt:

> Use case: ads-marketing. Asset type: polished wide project cover, 16:9 landscape intended for 1600x900. Primary request: finished editorial dossier cover visualizing a fictional Spanish amendment moving through evidence toward review. Scene/backdrop: warm paper #F5F0E6 with subtle tactile grain and generous clean margins. Subject: abstract unlabeled paper document collage on the left, thin cobalt #2654D8 evidence line connecting it to one vermilion #DB513F review tab on right. Style/medium: distinctive restrained print design, editorial, crisp typography, generous whitespace. Composition/framing: 16:9 landscape; headline upper half, abstract collage below; strong focal monospace value near right. Color palette: warm paper #F5F0E6, ink #17212B, cobalt #2654D8 evidence, vermilion #DB513F null/review. Materials/textures: paper collage, hairline rules, subtle grain. Text (verbatim, render exactly): “When a date is missing, keep it missing.”; “Clairic + Clef lab”; “Fictional Spanish amendment → evidence → review”; “effective_date = null”; “CLI replay visualized · fictional example”. Oversized refined serif headline; crisp sans labels; monospace focal value. Constraints: typeset only the exact phrases listed; preserve all spelling, punctuation and the underscore. No emblems or seals, no buildings, no charts, no graphs, no maps, no official document insignia. Keep the source document abstract with only neutral lines, not legible extra print. Avoid: legal imagery, courthouse, gavel, justice scales, flags, logos, brands, endorsement, UI controls, percentages, watermark, extra text.

All visuals are labeled as fictional replay examples. Clef values are model probabilities, not accuracy or calibration claims.
