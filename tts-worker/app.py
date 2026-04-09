from __future__ import annotations

import os
import re
import subprocess
import uuid
from pathlib import Path
from typing import Any

import edge_tts
from fastapi import FastAPI
from faster_whisper import WhisperModel
from pydantic import BaseModel

app = FastAPI(title="n8n TTS/Video Helper")

OUTPUT_DIR = Path("/output")
ASSETS_DIR = Path("/assets")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
ASSETS_DIR.mkdir(parents=True, exist_ok=True)

WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "tiny")
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cpu")
WHISPER_COMPUTE = os.getenv("WHISPER_COMPUTE", "int8")
MAX_WORDS_PER_PHRASE = int(os.getenv("MAX_WORDS_PER_PHRASE", "6"))

WHISPER: WhisperModel | None = None


class TTSIn(BaseModel):
    text: str
    voice: str = "en-US-AndrewMultilingualNeural"
    filename: str | None = None


class AlignIn(BaseModel):
    audio_path: str
    ass_name: str | None = None


class RenderIn(BaseModel):
    audio_path: str
    ass_path: str
    bg_path: str = "/assets/bg/night1.mp4"
    output_name: str = "doc_output.mp4"
    resolution: str = "1080x1920"


def _safe_name(name: str, fallback_ext: str) -> str:
    name = name.strip().replace("\\", "_").replace("/", "_")
    if not name:
        name = f"file_{uuid.uuid4().hex}{fallback_ext}"
    if not os.path.splitext(name)[1]:
        name += fallback_ext
    return name


def _sec_to_ass_time(t: float) -> str:
    t = max(0.0, t)
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t % 60
    return f"{h}:{m:02}:{s:05.2f}"


def _parse_resolution(res: str) -> tuple[str, str]:
    if "x" in res.lower():
        w, h = res.lower().split("x", 1)
        return w.strip() or "1080", h.strip() or "1920"
    return "1080", "1920"


def _normalize_word(w: str) -> str:
    return re.sub(r"\s+", " ", w).strip()


def _get_whisper() -> WhisperModel:
    global WHISPER
    if WHISPER is None:
        WHISPER = WhisperModel(
            WHISPER_MODEL_SIZE,
            device=WHISPER_DEVICE,
            compute_type=WHISPER_COMPUTE,
        )
    return WHISPER


def _build_ass_karaoke(words: list[dict[str, float | str]], ass_path: Path) -> None:
    """
    TikTok-like captions:
    - words pop one-by-one
    - keep adding words until phrase length limit
    - clear and start next phrase
    """
    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: K,Inter,72,&H00FFFFFF,&H0000D7FF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,3,1,2,80,80,260,1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""
    lines = [header]

    if not words:
        ass_path.write_text("\n".join(lines), encoding="utf-8")
        return

    step = max(1, MAX_WORDS_PER_PHRASE)
    for i in range(0, len(words), step):
        chunk = words[i : i + step]
        for active_idx, active in enumerate(chunk):
            start = float(active["start"])
            end = float(active["end"])
            if end <= start:
                end = start + 0.12

            rendered: list[str] = []
            for idx, w in enumerate(chunk):
                text = str(w["text"]).strip()
                if not text:
                    continue
                if idx == active_idx:
                    rendered.append(r"{\c&H00D7FF&\b1}" + text + r"{\c&H00FFFFFF&}")
                else:
                    rendered.append(text)

            if not rendered:
                continue
            line = " ".join(rendered)
            lines.append(
                f"Dialogue: 0,{_sec_to_ass_time(start)},{_sec_to_ass_time(end)},K,,0,0,0,,{line}"
            )

    ass_path.write_text("\n".join(lines), encoding="utf-8")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/tts-save")
async def tts_save(req: TTSIn) -> dict[str, Any]:
    filename = _safe_name(req.filename or f"monologue_{uuid.uuid4().hex}.mp3", ".mp3")
    output_path = OUTPUT_DIR / filename

    communicate = edge_tts.Communicate(req.text, req.voice, rate="+0%")
    await communicate.save(str(output_path))

    return {
        "ok": True,
        "filename": filename,
        "saved_to_container": str(output_path),
        "saved_to_host": f"./output/{filename}",
    }


@app.post("/align-words")
async def align_words(req: AlignIn) -> dict[str, Any]:
    audio_path = Path(req.audio_path)
    if not audio_path.exists():
        return {"ok": False, "error": f"Audio not found: {audio_path}"}

    ass_name = _safe_name(req.ass_name or f"{audio_path.stem}.ass", ".ass")
    ass_path = OUTPUT_DIR / ass_name

    whisper = _get_whisper()
    segments, info = whisper.transcribe(
        str(audio_path),
        beam_size=5,
        word_timestamps=True,
        vad_filter=True,
    )

    words: list[dict[str, float | str]] = []
    for seg in segments:
        for w in seg.words or []:
            if w.start is None or w.end is None:
                continue
            text = _normalize_word(w.word or "")
            if not text:
                continue
            words.append({"start": float(w.start), "end": float(w.end), "text": text})

    _build_ass_karaoke(words, ass_path)

    return {
        "ok": True,
        "language": info.language,
        "ass_to_container": str(ass_path),
        "ass_to_host": f"./output/{ass_path.name}",
        "word_count": len(words),
    }


@app.post("/render-vertical")
async def render_vertical(req: RenderIn) -> dict[str, Any]:
    audio_path = Path(req.audio_path)
    if not audio_path.exists():
        return {"ok": False, "error": f"Audio not found: {audio_path}"}

    ass_path = Path(req.ass_path)
    if not ass_path.exists():
        return {"ok": False, "error": f"ASS not found: {ass_path}"}

    bg_path = Path(req.bg_path)
    if not bg_path.exists():
        return {"ok": False, "error": f"Background video not found: {bg_path}"}

    output_name = _safe_name(req.output_name, ".mp4")
    output_path = OUTPUT_DIR / output_name
    w, h = _parse_resolution(req.resolution)

    ass_for_ffmpeg = (
        str(ass_path)
        .replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace(",", "\\,")
    )

    vf = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},ass='{ass_for_ffmpeg}'"

    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-stream_loop",
        "-1",
        "-i",
        str(bg_path),
        "-i",
        str(audio_path),
        "-vf",
        vf,
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "22",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-shortest",
        str(output_path),
    ]

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        return {
            "ok": False,
            "error": "ffmpeg render failed",
            "ffmpeg_stderr": (proc.stderr or "")[-4000:],
            "ffmpeg_stdout": (proc.stdout or "")[-1000:],
            "cmd": " ".join(cmd),
        }

    return {
        "ok": True,
        "output_name": output_name,
        "video_path": str(output_path),
        "saved_to_host": f"./output/{output_name}",
    }
