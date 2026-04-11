# n8n Live Upgrade Guide

## What was added

The upgraded workflow now covers the full factory, not just script generation:

1. Fetch Reddit trends
2. Normalize top two topics
3. Generate draft A and draft B with Ollama
4. Judge the better draft
5. Keep one final `script`
6. Send the script to `tts-worker` for MP3 generation
7. Align spoken words into `.ass` captions
8. Render the final vertical video with background + audio + captions

The importable workflow file is here:

- `n8n/workflows/ai_video_factory_full.json`

## How to see the new flow live in n8n

1. Start the stack:

```powershell
docker compose up -d --build
```

2. Open n8n in your browser:

```text
http://localhost:5678
```

3. In n8n, choose **Import from File**.

4. Import this file:

```text
n8n/workflows/ai_video_factory_full.json
```

5. Open the imported workflow and you will see the full node graph visually.

6. Click **Execute workflow** to run it manually.

## What to expect after execution

Generated files are written to `output/`:

- `monologue_*.mp3`
- `captions_*.ass`
- `doc_*.mp4`

## Important service dependencies

Before running the flow, make sure these services are healthy:

- `n8n`
- `ollama`
- `tts-worker`

You will also need the Ollama models used by the workflow:

```powershell
docker exec ollama ollama pull qwen2.5:3b
docker exec ollama ollama pull llama3.2:3b
```

## Notes

- The worker expects a background clip at `/assets/bg/night1.mp4`.
- The render step uses `1080x1920` vertical output.
- If you want to edit the flow visually, do it inside n8n after import, then save it there.
