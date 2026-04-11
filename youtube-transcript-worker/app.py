from __future__ import annotations

import os
import re
import subprocess
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from fastapi import BackgroundTasks, FastAPI
from faster_whisper import WhisperModel
from pydantic import BaseModel
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import TextFormatter

app = FastAPI(title="YouTube Transcript Worker")

OUTPUT_DIR = Path("/output/transcripts")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
JOBS_DIR = Path("/output/transcript_jobs")
JOBS_DIR.mkdir(parents=True, exist_ok=True)

WHISPER_MODEL_SIZE = os.getenv("YT_WHISPER_MODEL_SIZE", "tiny")
WHISPER_DEVICE = os.getenv("YT_WHISPER_DEVICE", "cpu")
WHISPER_COMPUTE = os.getenv("YT_WHISPER_COMPUTE", "int8")

WHISPER: WhisperModel | None = None


class TranscriptIn(BaseModel):
    youtube_url: str
    filename: str | None = None
    language: str | None = "en"
    prefer_generated_captions: bool = True
    force_transcribe: bool = False
    return_text: bool = False


class TranscriptJobStatus(BaseModel):
    job_id: str
    status: str
    created_at: str
    updated_at: str
    youtube_url: str
    filename: str | None = None
    result: dict[str, Any] | None = None
    error: str | None = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _job_path(job_id: str) -> Path:
    return JOBS_DIR / f"{job_id}.json"


def _write_job(job: TranscriptJobStatus) -> None:
    _job_path(job.job_id).write_text(job.model_dump_json(indent=2), encoding="utf-8")


def _read_job(job_id: str) -> TranscriptJobStatus | None:
    path = _job_path(job_id)
    if not path.exists():
        return None
    return TranscriptJobStatus.model_validate_json(path.read_text(encoding="utf-8"))


def _get_whisper() -> WhisperModel:
    global WHISPER
    if WHISPER is None:
        WHISPER = WhisperModel(
            WHISPER_MODEL_SIZE,
            device=WHISPER_DEVICE,
            compute_type=WHISPER_COMPUTE,
        )
    return WHISPER


def _safe_name(name: str | None, fallback_stem: str) -> str:
    if name:
        cleaned = re.sub(r"[^\w.\-]+", "_", name.strip())
        if cleaned.endswith(".txt"):
            return cleaned
        if "." not in Path(cleaned).name:
            return f"{cleaned}.txt"
        return cleaned
    return f"{fallback_stem}.txt"


def _extract_video_id(url: str) -> str:
    parsed = urlparse(url.strip())
    host = parsed.netloc.lower()

    if "youtu.be" in host:
        video_id = parsed.path.strip("/")
        if video_id:
            return video_id

    if "youtube.com" in host:
        if parsed.path == "/watch":
            video_id = parse_qs(parsed.query).get("v", [""])[0]
            if video_id:
                return video_id
        if parsed.path.startswith("/shorts/") or parsed.path.startswith("/embed/"):
            parts = [part for part in parsed.path.split("/") if part]
            if len(parts) >= 2:
                return parts[1]

    raise ValueError("Unsupported or invalid YouTube URL")


def _canonical_youtube_url(url: str) -> str:
    video_id = _extract_video_id(url)
    return f"https://www.youtube.com/watch?v={video_id}"


def _write_transcript(text: str, filename: str) -> Path:
    output_path = OUTPUT_DIR / filename
    output_path.write_text(text.strip() + "\n", encoding="utf-8")
    return output_path


def _fetch_youtube_transcript(video_id: str, language: str | None, prefer_generated: bool) -> str | None:
    languages = [language] if language else None

    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
    except Exception:
        return None

    transcript = None
    try:
        if languages:
            transcript = transcript_list.find_transcript(languages)
        else:
            transcript = next(iter(transcript_list), None)
    except Exception:
        transcript = None

    if transcript is None and prefer_generated:
        try:
            if languages:
                transcript = transcript_list.find_generated_transcript(languages)
        except Exception:
            transcript = None

    if transcript is None:
        try:
            transcript = next(iter(transcript_list), None)
        except Exception:
            transcript = None

    if transcript is None:
        return None

    formatter = TextFormatter()
    fetched = transcript.fetch()
    return formatter.format_transcript(fetched).strip()


def _download_audio(youtube_url: str, workdir: Path) -> Path:
    output_template = str(workdir / "audio.%(ext)s")
    clean_url = _canonical_youtube_url(youtube_url)
    cmd = [
        "yt-dlp",
        "--js-runtimes",
        "node",
        "--remote-components",
        "ejs:github",
        "--no-playlist",
        "--extract-audio",
        "--audio-format",
        "mp3",
        "--audio-quality",
        "0",
        "--output",
        output_template,
        clean_url,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "yt-dlp failed").strip())

    matches = list(workdir.glob("audio.*"))
    if not matches:
        raise RuntimeError("Audio download succeeded but no audio file was found")
    return matches[0]


def _transcribe_audio(audio_path: Path, language: str | None) -> str:
    whisper = _get_whisper()
    segments, _ = whisper.transcribe(
        str(audio_path),
        beam_size=5,
        vad_filter=True,
        language=language or None,
    )
    chunks = [segment.text.strip() for segment in segments if segment.text.strip()]
    return "\n".join(chunks).strip()


def _generate_transcript(req: TranscriptIn) -> dict[str, Any]:
    video_id = _extract_video_id(req.youtube_url)
    filename = _safe_name(req.filename, f"{video_id}_{uuid.uuid4().hex[:8]}")

    transcript_text: str | None = None
    method = "transcribed"

    if not req.force_transcribe:
        transcript_text = _fetch_youtube_transcript(
            video_id,
            req.language,
            req.prefer_generated_captions,
        )
        if transcript_text:
            method = "captions"

    if not transcript_text:
        with tempfile.TemporaryDirectory() as tmp_dir:
            audio_path = _download_audio(req.youtube_url, Path(tmp_dir))
            transcript_text = _transcribe_audio(audio_path, req.language)

    if not transcript_text:
        raise RuntimeError("Transcript could not be fetched or generated")

    output_path = _write_transcript(transcript_text, filename)
    return {
        "ok": True,
        "method": method,
        "video_id": video_id,
        "transcript_path": str(output_path),
        "saved_to_host": f"./output/transcripts/{output_path.name}",
        "filename": output_path.name,
        "transcript_text": transcript_text if req.return_text else None,
    }


def _run_job(job_id: str, req: TranscriptIn) -> None:
    job = _read_job(job_id)
    if job is None:
        return

    job.status = "running"
    job.updated_at = _now_iso()
    _write_job(job)

    try:
        job.result = _generate_transcript(req)
        job.status = "completed"
        job.error = None
    except Exception as exc:
        job.status = "failed"
        job.error = str(exc)
        job.result = None

    job.updated_at = _now_iso()
    _write_job(job)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/youtube-transcript")
async def youtube_transcript(req: TranscriptIn) -> dict[str, Any]:
    try:
        return _generate_transcript(req)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@app.post("/youtube-transcript-jobs")
async def create_youtube_transcript_job(
    req: TranscriptIn,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    job_id = uuid.uuid4().hex
    now = _now_iso()
    job = TranscriptJobStatus(
        job_id=job_id,
        status="queued",
        created_at=now,
        updated_at=now,
        youtube_url=req.youtube_url,
        filename=req.filename,
        result=None,
        error=None,
    )
    _write_job(job)
    background_tasks.add_task(_run_job, job_id, req)
    return {
        "ok": True,
        "job_id": job_id,
        "status": job.status,
        "status_url": f"/youtube-transcript-jobs/{job_id}",
    }


@app.get("/youtube-transcript-jobs/{job_id}")
async def get_youtube_transcript_job(job_id: str) -> dict[str, Any]:
    job = _read_job(job_id)
    if job is None:
        return {"ok": False, "error": f"Job not found: {job_id}"}
    return {"ok": True, **job.model_dump()}
