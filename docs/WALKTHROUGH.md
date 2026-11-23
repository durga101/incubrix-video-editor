# Code Walkthrough

This guide walks you through the codebase so you can explain and modify any part during the live evaluation.

---

## 1. The Request Lifecycle

```
POST /sessions/{id}/edit  {"instruction": "Remove everything before 'Welcome back'"}
         │
         ▼
sessions.py:apply_edit()
         │
         ├─ 1. parse_instruction(instruction)   → ParsedInstruction
         │       engine/parser.py
         │       • Regex matching for 11 instruction types
         │       • Extracts: timestamps, quoted phrases, multipliers
         │
         ├─ 2. plan_edit(session, pi, duration) → EditStep
         │       engine/planner.py
         │       • Looks up phrase_start / phrase_end in transcript.find_phrase()
         │       • Calls _snap_to_silence() to move cut edge to gap
         │       • Clamps to [0, video_duration]
         │
         ├─ 3. history.apply(step)
         │       engine/history.py
         │       • If UNDO → pop last step
         │       • If RESTORE → truncate to named step
         │       • Otherwise → append
         │
         └─ 4. Build three-answer response (answer_a/b/c)
```

---

## 2. Content-Anchored Edits

**Question you will be asked**: "What happens when I say 'Remove everything before Welcome back' and the transcript doesn't have that phrase?"

**Answer**: `transcript.find_phrase()` returns `None`. The planner raises `ValueError("Phrase not found in transcript: ...")`. The API returns HTTP 422 with a helpful error message.

**Code**: `engine/models.py:Transcript.find_phrase()` — iterates over words, matches lowercased tokens.

---

## 3. Snap-to-Silence

**What it is**: After resolving a cut time (e.g., 4.3 s), the planner checks whether there is a silence gap (space between consecutive words) within ±0.5 s. If so, it moves the cut edge to the gap boundary (start or end).

**Why**: FFmpeg cuts at the nearest keyframe anyway, but snapping to silence avoids audio pop artefacts.

**Code**: `engine/planner._snap_to_silence()`.

**How to modify**: Change `_SNAP_RADIUS = 0.5` in `engine/planner.py` to widen or narrow the snap window.

---

## 4. Undo vs. Restore

| Feature | How it works |
|---------|-------------|
| `Undo` | Pops the last `EditStep` from `session.history` (like a stack) |
| `Restore to step X` | Truncates `session.history` to the step with `id == X`, keeping it |

After undo or restore, the **next render** replays the truncated history from scratch.

**Code**: `engine/history.py:EditHistory.undo()` and `.restore()`.

---

## 5. The FFmpeg Filter Graph

`engine/executor.build_ffmpeg_command()` translates the history into one `ffmpeg` command. Key filter mappings:

| Step kind | Video filter | Audio filter |
|-----------|-------------|-------------|
| TRIM | `trim=start:end,setpts=...` | `atrim=start:end,asetpts=...` |
| CUT | `select='not(between(t,...))'` | `aselect=...` |
| SILENCE | _(none)_ | `volume=0:enable='between(t,...)'` |
| SUBTITLE | `drawtext=...` | _(none)_ |
| SPEED | `setpts=1/rate*PTS` | `atempo=rate` (chained) |
| VOLUME | _(none)_ | `volume=factor` |
| FADE | `fade=...` | `afade=...` |

**How to add a new instruction type**:
1. Add a new `StepKind` value in `engine/models.py`
2. Add a regex branch in `engine/parser.py:parse_instruction()`
3. Add a filter fragment in `engine/executor.build_ffmpeg_command()`
4. Add tests in `tests/test_parser.py` and `tests/test_render.py`

---

## 6. The Three-Answer Format

Every `/edit` response has:

```json
{
  "answer_a": "I will keep only the segment from 2.00s to 8.00s, removing everything outside this range.",
  "answer_b": "No limitations for this operation.",
  "answer_c": "You can now add subtitles, adjust volume, or render the result."
}
```

Built in `app/routers/sessions.py:_build_answer_a/b/c()`. Modify these to change the response tone.

---

## 7. Quick Modification Examples

### Add a new instruction type: "blur from X to Y"

```python
# engine/models.py — add to StepKind:
BLUR = "blur"

# engine/parser.py — add branch:
if re.search(r"\bblur\b", lower):
    pi.kind = StepKind.BLUR
    pi = _resolve_range(pi, t, lower)
    return pi

# engine/executor.py — add fragment:
blurs = [s for s in steps if s.kind == StepKind.BLUR]
for s in blurs:
    a, b = s.anchor_start, s.anchor_end
    video_filters.append(f"boxblur=10:enable='between(t,{a},{b})'")
```

### Change the snap radius

```python
# engine/planner.py line 10:
_SNAP_RADIUS = 1.0  # was 0.5 — snap up to 1 second away
```

### Change the subtitle font size default

```python
# engine/parser.py inside the subtitle branch:
pi.params.setdefault("font_size", 32)  # was 24
```
