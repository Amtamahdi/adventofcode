# AI Video Factory

Simple project to generate a short video with:

- `n8n` for orchestration
- `ollama` for script generation
- `tts-worker` for text-to-speech, word alignment, and final video rendering

## Main folders

- `assets/`: background media used in the final video
- `data/`: temporary text/data files created during the pipeline
- `docs/`: project guide kept from the older GitHub repo
- `n8n/`: local n8n configuration and workflow database
- `output/`: generated audio, captions, and video files
- `scripts/`: small pipeline scripts
- `tts-worker/`: FastAPI service used by n8n

## Main files

- `docker-compose.yml`: starts the whole project
- `tts-worker/app.py`: API for TTS, subtitles, and rendering
- `tts-worker/Dockerfile`: Docker image for the worker

## Simple project flow

1. `scripts/fetch_trends.py` gets topics.
2. `scripts/generate_script.py` writes the final script.
3. `tts-worker` or `scripts/make_tts.py` creates audio.
4. `tts-worker` or `scripts/make_srt.py` creates captions.
5. `tts-worker` or `scripts/render_video.sh` renders the final video.

## What was cleaned

- Removed unused top-level Dockerfiles.
- Removed generated output files and n8n logs/execution artifacts.
- Kept the actual source code and current n8n database so the project state is not broken.

## Run

```bash
docker compose up --build
```

## Upgraded n8n flow

An importable full workflow is now included at:

- `n8n/workflows/ai_video_factory_full.json`

This upgraded flow covers:

1. Trend fetch
2. Draft generation
3. Draft judging
4. TTS generation
5. Word alignment
6. Vertical video rendering

To open it live in n8n, see:

- `docs/n8n_live_upgrade_guide.md`
