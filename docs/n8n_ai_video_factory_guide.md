# n8n + Ollama + TTS Worker: End-to-End Setup and Flow

This document captures the full project setup and upgrades from start to finish, including Docker, n8n flow design, TTS generation, and vertical documentary-style video rendering.

## 1) Project structure

```text
.
├── docker-compose.yml
├── n8n/
├── output/
├── assets/
│   └── bg/
│       └── night1.mp4
└── tts-worker/
    ├── Dockerfile
    └── app.py
```

## 2) Docker services

The stack has three services:

- `n8n`: workflow orchestration UI (`http://localhost:5678`)
- `ollama`: local LLM endpoint (`http://ollama:11434` from Docker network)
- `tts-worker`: helper API for TTS and vertical rendering (`http://localhost:8000`)

### Why this architecture

- n8n stays visual and orchestrates everything.
- Media-heavy steps (TTS/render) live in dedicated worker service.
- Output is persisted to `./output` on host.

## 3) Start / stop commands

```bash
# Start everything
cd /path/to/repo
docker compose up -d --build

# Pull lightweight local model
docker exec ollama ollama pull qwen2.5:1.5b

# Stop everything
docker compose down
```

## 4) n8n flow from start to finish

### Existing flow (content selection)

1. Manual trigger
2. Fetch Reddit trends
3. Normalize to `trendA` and `trendB`
4. Generate two drafts (`AI writer A` and `AI Writer B`)
5. Merge drafts
6. Judge best draft
7. Final code node outputs `script` (selected transcript)

### Upgrades for media output (no second LLM call)

Add these nodes after your final code node that returns `script`:

1. **TTS** (`POST http://tts-worker:8000/tts-save`)
   - body fields:
     - `text` = `{{$json.script}}`
     - `voice` = `en-US-AndrewMultilingualNeural`
     - `filename` = `={{"monologue_" + $now.format("yyyyLLdd_HHmmss") + ".mp3"}}`
   - response format: JSON

2. **Render Vertical** (`POST http://tts-worker:8000/render-vertical`)
   - body fields:
     - `script` = `{{$node["Code in JavaScript1"].json["script"]}}`
     - `audio_path` = `{{$node["TTS"].json["saved_to_container"]}}`
     - `bg_path` = `/assets/bg/night1.mp4`
     - `output_name` = `={{"doc_" + $now.format("yyyyLLdd_HHmmss") + ".mp4"}}`
     - `resolution` = `1080x1920`
     - `subtitle_position` = `center`

Result: rendered `.mp4` and `.srt` are saved to `./output` on host.

## 5) Important bug fixes discovered during setup

- Keep **Set node field names exact** (no trailing spaces):
  - `draftA`, `topicA`, `urlA`
  - `draftB`, `topicB`, `urlB`
- `topicB`/`urlB` must read from `trendB` (not `trendA`).
- Judge prompt must return strict JSON only.
- In PowerShell, use single quotes when echoing Linux env vars in `docker exec`:

```powershell
docker exec n8n sh -lc 'echo RESTRICT=$N8N_RESTRICT_FILE_ACCESS_TO'
```

## 6) iPhone vertical documentary output settings

Worker render endpoint enforces:

- `1080x1920` output
- center subtitle alignment
- white text + black outline for readability
- `-shortest` to match video length to narration audio

## 7) Health checks

```bash
# Services running
docker ps

# Worker health
curl http://localhost:8000/health

# n8n env check
docker exec n8n sh -lc 'env | grep N8N_RESTRICT_FILE_ACCESS_TO'
```

## 8) Host output paths

- MP3: `./output/monologue_*.mp3`
- SRT: `./output/doc_*.srt`
- Video: `./output/doc_*.mp4`

## 9) Notes on free background video

Use royalty-free clips in `assets/bg/`, for example static night monument shots from free libraries (ensure license compliance).

