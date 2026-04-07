from __future__ import annotations

import os
import re
import uuid
from pathlib import Path

import edge_tts
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="n8n TTS/Video Helper")

OUTPUT_DIR = Path("/output")
ASSETS_DIR = Path("/assets")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
ASSETS_DIR.mkdir(parents=True, exist_ok=True)


class TTSIn(BaseModel):
    text: str
    voice: str = "en-US-AndrewMultilingualNeural"
    filename: str | None = None


class RenderIn(BaseModel):
    script: str
    audio_path: str
    bg_path: str = "/assets/bg/night1.mp4"
    output_name: str = "doc_output.mp4"
    resolution: str = "1080x1920"
    subtitle_position: str = "center"


def _safe_name(name: str, fallback_ext: str) -> str:
    name = name.strip().replace("\\", "_").replace("/", "_")
    if not name:
        name = f"file_{uuid.uuid4().hex}{fallback_ext}"
    if not os.path.splitext(name)[1]:
        name += fallback_ext
    return name


def _seconds_to_srt_time(total_seconds: float) -> str:
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    seconds = int(total_seconds % 60)
    millis = int((total_seconds - int(total_seconds)) * 1000)
    return f"{hours:02}:{minutes:02}:{seconds:02},{millis:03}"


def _chunk_script(script: str, words_per_chunk: int = 8) -> list[str]:
    words = re.findall(r"\S+", script)
    if not words:
        return [""]
    return [" ".join(words[i : i + words_per_chunk]) for i in range(0, len(words), words_per_chunk)]


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/tts-save")
async def tts_save(req: TTSIn) -> dict[str, str | bool]:
    filename = _safe_name(req.filename or f"monologue_{uuid.uuid4().hex}.mp3", ".mp3")
    output_path = OUTPUT_DIR / filename

    communicate = edge_tts.Communicate(req.text, req.voice)
    await communicate.save(str(output_path))

    return {
        "ok": True,
        "filename": filename,
        "saved_to_container": str(output_path),
        "saved_to_host": f"./output/{filename}",
    }


@app.post("/render-vertical")
async def render_vertical(req: RenderIn) -> dict[str, str | bool]:
    audio_path = Path(req.audio_path)
    if not audio_path.exists():
        return {"ok": False, "error": f"Audio not found: {audio_path}"}

    bg_path = Path(req.bg_path)
    if not bg_path.exists():
        return {"ok": False, "error": f"Background video not found: {bg_path}"}

    output_name = _safe_name(req.output_name, ".mp4")
    output_path = OUTPUT_DIR / output_name

    # Build lightweight SRT from already-generated script (no extra LLM/transcription call)
    chunks = _chunk_script(req.script, words_per_chunk=8)

    # Use ffprobe to estimate subtitle timing using audio duration
    duration_cmd = f"ffprobe -v error -show_entries format=duration -of default=nk=1:nw=1 '{audio_path}'"
    duration_raw = os.popen(duration_cmd).read().strip()
    duration = float(duration_raw) if duration_raw else 60.0
    seconds_per_chunk = max(duration / max(len(chunks), 1), 0.6)

    srt_path = OUTPUT_DIR / f"{Path(output_name).stem}.srt"
    lines: list[str] = []
    current = 0.0
    for idx, text in enumerate(chunks, start=1):
        start = current
        end = min(duration, current + seconds_per_chunk)
        lines.append(str(idx))
        lines.append(f"{_seconds_to_srt_time(start)} --> {_seconds_to_srt_time(end)}")
        lines.append(text)
        lines.append("")
        current = end
    srt_path.write_text("\n".join(lines), encoding="utf-8")

    subtitle_alignment = "5" if req.subtitle_position.lower() == "center" else "2"

    filter_chain = (
        f"scale={req.resolution}:force_original_aspect_ratio=increase,"
        f"crop={req.resolution},"
        f"subtitles={srt_path}:"
        "force_style='"
        f"Alignment={subtitle_alignment},"
        "FontName=Arial,"
        "FontSize=16,"
        "PrimaryColour=&H00FFFFFF&,"
        "OutlineColour=&H00000000&,"
        "BorderStyle=3,Outline=2,Shadow=0"
        "'"
    )

    ffmpeg_cmd = (
        f"ffmpeg -y -stream_loop -1 -i '{bg_path}' -i '{audio_path}' "
        f"-vf \"{filter_chain}\" "
        "-c:v libx264 -preset medium -crf 22 "
        "-c:a aac -b:a 192k -shortest "
        f"'{output_path}'"
    )
    code = os.system(ffmpeg_cmd)
    if code != 0:
        return {"ok": False, "error": "ffmpeg render failed"}

    return {
        "ok": True,
        "output_name": output_name,
        "video_path": str(output_path),
        "subtitle_path": str(srt_path),
        "saved_to_host": f"./output/{output_name}",
    }
