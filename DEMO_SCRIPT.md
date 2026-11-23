# Demo Script — IncuBrix PS2

**Maximum: 8 minutes, unedited, on the live demo URL.**

---

## Before you start recording

1. Open the live URL in your browser (not localhost)
2. Have a short video file ready (60–90 seconds, MP4)
3. Have the transcript JSON ready (use `samples/transcripts/interview_single.transcript.json`)
4. Have the API token ready (do not say it on camera; blur it if necessary)
5. Practice the steps below at least once

---

## Recording script (~7 minutes)

### 0:00 – 0:30 — Introduction

> "Hi, I'm [name]. I'm going to demonstrate my IncuBrix PS2 solution — a Prompt-Based Video Editing Engine."
> "The API is live at [your URL]. It accepts natural-language instructions and applies them to video files using FFmpeg."

### 0:30 – 1:30 — Create a session and upload

Using the `/docs` Swagger UI or curl:

```bash
# Create a session
curl -X POST https://your-url.com/sessions
# → copy the session_id

# Upload video + transcript
curl -X POST https://your-url.com/sessions/<SESSION_ID>/upload \
  -F "video=@samples/media/interview_single.mp4" \
  -F "transcript=@samples/transcripts/interview_single.transcript.json"
```

> "The engine now has the video and its word-level transcript loaded."

### 1:30 – 3:00 — Demonstrate phrase-anchored edit

```bash
curl -X POST https://your-url.com/sessions/<SESSION_ID>/edit \
  -H "Content-Type: application/json" \
  -d '{"instruction": "Remove everything before \"Good morning everyone\""}'
```

> "I asked the engine to remove everything before the phrase 'Good morning everyone'."
> "Notice the response: answer_a tells me what it did, answer_b tells me any limitations,
>  and answer_c suggests what to do next."
> "The anchor_start is [X] seconds — that's exactly where 'Good morning everyone' starts
>  in the transcript, snapped to the nearest silence gap."

### 3:00 – 4:00 — Cut a filler word

```bash
curl -d '{"instruction": "Remove everything between \"uh\" and \"today\""}' \
  -H "Content-Type: application/json" \
  https://your-url.com/sessions/<SESSION_ID>/edit
```

> "Now I've removed the filler word 'uh'. The engine found it in the transcript and cut precisely."

### 4:00 – 4:30 — Add a subtitle

```bash
curl -d '{"instruction": "Add subtitle \"Introduction\" from 0:00 to 0:05"}' \
  -H "Content-Type: application/json" \
  https://your-url.com/sessions/<SESSION_ID>/edit
```

### 4:30 – 5:00 — Undo

```bash
curl -d '{"instruction": "Undo"}' \
  -H "Content-Type: application/json" \
  https://your-url.com/sessions/<SESSION_ID>/edit
```

> "I can undo any step. The history now has one fewer step."

### 5:00 – 6:30 — Render

```bash
curl -X POST https://your-url.com/render/<SESSION_ID> \
  -H "Content-Type: application/json" \
  -d '{"output_format": "mp4"}'
# → copy job_id

curl https://your-url.com/render/<SESSION_ID>/<JOB_ID>
# Poll until status=done
```

> "The render is complete. The output URL contains the edited video."

### 6:30 – 7:00 — View history and explain architecture

```bash
curl https://your-url.com/sessions/<SESSION_ID>/history
```

> "The history shows every edit step, in order. This is what gets replayed into a single FFmpeg command on render."

### 7:00 – 7:30 — Wrap up

> "That's the demo. The API is fully documented at /docs, the OpenAPI spec is at /openapi.json,
>  and the full source is in the GitHub repository."

---

## Tips

- Keep the token off-camera or blur it in post
- If a command fails live, stay calm and retry — it's real software
- Mention: content-anchored edits, snap-to-silence, three-answer format, history replay
