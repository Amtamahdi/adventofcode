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

try:
    import ctranslate2
except Exception:  # pragma: no cover
    ctranslate2 = None

app = FastAPI(title="YouTube Transcript Worker")

OUTPUT_DIR = Path("/output/transcripts")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
JOBS_DIR = Path("/output/transcript_jobs")
JOBS_DIR.mkdir(parents=True, exist_ok=True)

WHISPER_MODEL_SIZE = os.getenv("YT_WHISPER_MODEL_SIZE", "large-v3")
MIN_CAPTION_WORDS = int(os.getenv("YT_CAPTION_MIN_WORDS", "120"))
MIN_TRANSCRIPT_WORDS = int(os.getenv("YT_TRANSCRIPT_MIN_WORDS", "80"))
STT_BACKEND = os.getenv("YT_STT_BACKEND", "auto").strip().lower()
OV_MODEL_ID = os.getenv("YT_OV_MODEL_ID", "OpenVINO/whisper-large-v3-int8-ov").strip()
OV_DEVICE = os.getenv("YT_OV_DEVICE", "auto").strip().upper()
YT_COOKIES_FILE = os.getenv("YT_COOKIES_FILE", "").strip()

WHISPER: WhisperModel | None = None
OV_PIPELINE: Any | None = None
YT_API = YouTubeTranscriptApi()


class TranscriptIn(BaseModel):
    youtube_url: str
    filename: str | None = None
    language: str | None = None
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
        device, compute_type = _resolve_whisper_runtime()
        WHISPER = WhisperModel(
            WHISPER_MODEL_SIZE,
            device=device,
            compute_type=compute_type,
        )
    return WHISPER


def _has_intel_gpu_runtime() -> bool:
    return Path("/dev/dxg").exists() and Path("/usr/lib/wsl/lib").exists()


def _resolve_stt_backend() -> str:
    if STT_BACKEND in {"openvino", "whisper"}:
        return STT_BACKEND
    return "openvino" if _has_intel_gpu_runtime() else "whisper"


def _resolve_openvino_device() -> str:
    if OV_DEVICE in {"CPU", "GPU", "AUTO"}:
        if OV_DEVICE == "AUTO":
            return "GPU" if _has_intel_gpu_runtime() else "CPU"
        return OV_DEVICE
    return "GPU" if _has_intel_gpu_runtime() else "CPU"


def _resolve_whisper_runtime() -> tuple[str, str]:
    requested_device = os.getenv("YT_WHISPER_DEVICE", "auto").strip().lower()
    requested_compute = os.getenv("YT_WHISPER_COMPUTE", "auto").strip().lower()

    has_cuda = False
    if ctranslate2 is not None:
        try:
            has_cuda = ctranslate2.get_cuda_device_count() > 0
        except Exception:
            has_cuda = False

    device = requested_device
    if device == "auto":
        device = "cuda" if has_cuda else "cpu"

    compute_type = requested_compute
    if compute_type == "auto":
        compute_type = "float16" if device == "cuda" else "int8"

    return device, compute_type


def _count_words(text: str | None) -> int:
    if not text:
        return 0
    return len(re.findall(r"\b\w+\b", text))


def _has_valid_cookies_file(path_str: str) -> bool:
    if not path_str:
        return False

    path = Path(path_str)
    if not path.exists() or path.stat().st_size == 0:
        return False

    try:
        first_line = path.read_text(encoding="utf-8", errors="ignore").splitlines()[0].strip()
    except Exception:
        return False

    return first_line.startswith("# Netscape HTTP Cookie File")


def _get_openvino_pipeline() -> Any:
    global OV_PIPELINE
    if OV_PIPELINE is None:
        from optimum.intel.openvino import OVModelForSpeechSeq2Seq
        from transformers import AutoProcessor, pipeline

        ov_device = _resolve_openvino_device()
        processor = AutoProcessor.from_pretrained(OV_MODEL_ID)
        model = OVModelForSpeechSeq2Seq.from_pretrained(OV_MODEL_ID, device=ov_device)
        OV_PIPELINE = pipeline(
            "automatic-speech-recognition",
            model=model,
            tokenizer=processor.tokenizer,
            feature_extractor=processor.feature_extractor,
        )
    return OV_PIPELINE


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
    try:
        fetched = YT_API.fetch(
            video_id,
            languages=[language] if language else None,
            preserve_formatting=False,
        )
    except Exception:
        return None

    formatter = TextFormatter()
    return formatter.format_transcript(fetched).strip()


def _is_youtube_download_blocked(message: str) -> bool:
    lowered = message.lower()
    return (
        "http error 429" in lowered
        or "too many requests" in lowered
        or "sign in to confirm you" in lowered
        or "not a bot" in lowered
    )


def _download_audio(youtube_url: str, workdir: Path) -> Path:
    output_template = str(workdir / "audio.%(ext)s")
    clean_url = _canonical_youtube_url(youtube_url)
    cmd = [
        "yt-dlp",
        "--js-runtimes",
        "node",
        "--remote-components",
        "ejs:github",
        "--extractor-args",
        "youtube:player_client=web",
        "--retries",
        "5",
        "--retry-sleep",
        "exp=1:10",
        "--sleep-requests",
        "1",
        "--no-playlist",
        "--extract-audio",
        "--audio-format",
        "mp3",
        "--audio-quality",
        "0",
        "--output",
        output_template,
    ]
    if _has_valid_cookies_file(YT_COOKIES_FILE):
        cookie_copy = workdir / "cookies.txt"
        cookie_copy.write_text(
            Path(YT_COOKIES_FILE).read_text(encoding="utf-8", errors="ignore"),
            encoding="utf-8",
        )
        cmd.extend(["--cookies", str(cookie_copy)])
    cmd.append(clean_url)
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        message = (proc.stderr or proc.stdout or "yt-dlp failed").strip()
        if _is_youtube_download_blocked(message):
            raise RuntimeError(
                "YouTube blocked direct audio download (429 / anti-bot check). "
                "Leave force_transcribe disabled so captions can be used when available, "
                "or provide a valid YouTube cookies file at /run/secrets/youtube-cookies.txt."
            )
        raise RuntimeError(message)

    matches = list(workdir.glob("audio.*"))
    if not matches:
        raise RuntimeError("Audio download succeeded but no audio file was found")
    return matches[0]


def _transcribe_audio_with_whisper(audio_path: Path, language: str | None) -> tuple[str, dict[str, Any]]:
    whisper = _get_whisper()
    attempts = [
        {"beam_size": 5, "best_of": 5, "temperature": 0.0, "vad_filter": True},
        {"beam_size": 5, "best_of": 5, "temperature": 0.0, "vad_filter": False},
    ]

    for options in attempts:
        segments, _ = whisper.transcribe(
            str(audio_path),
            language=language or None,
            **options,
        )
        chunks = [segment.text.strip() for segment in segments if segment.text.strip()]
        transcript = "\n".join(chunks).strip()
        if transcript:
            device, compute_type = _resolve_whisper_runtime()
            return transcript, {
                "stt_backend": "whisper",
                "stt_model": WHISPER_MODEL_SIZE,
                "stt_device": device,
                "stt_compute_type": compute_type,
            }

    device, compute_type = _resolve_whisper_runtime()
    return "", {
        "stt_backend": "whisper",
        "stt_model": WHISPER_MODEL_SIZE,
        "stt_device": device,
        "stt_compute_type": compute_type,
    }


def _transcribe_audio_with_openvino(audio_path: Path, language: str | None) -> tuple[str, dict[str, Any]]:
    asr = _get_openvino_pipeline()
    generate_kwargs: dict[str, Any] = {"task": "transcribe"}
    if language:
        generate_kwargs["language"] = language

    result = asr(
        str(audio_path),
        chunk_length_s=30,
        batch_size=1,
        generate_kwargs=generate_kwargs,
    )
    text = ""
    if isinstance(result, dict):
        text = str(result.get("text", "")).strip()
    elif isinstance(result, str):
        text = result.strip()

    return text, {
        "stt_backend": "openvino",
        "stt_model": OV_MODEL_ID,
        "stt_device": _resolve_openvino_device(),
        "stt_compute_type": "openvino",
    }


def _transcribe_audio(audio_path: Path, language: str | None) -> tuple[str, dict[str, Any]]:
    backend = _resolve_stt_backend()
    if backend == "openvino":
        try:
            return _transcribe_audio_with_openvino(audio_path, language)
        except Exception:
            if STT_BACKEND == "openvino":
                raise
    return _transcribe_audio_with_whisper(audio_path, language)


def _generate_transcript(req: TranscriptIn) -> dict[str, Any]:
    video_id = _extract_video_id(req.youtube_url)
    filename = _safe_name(req.filename, f"{video_id}_{uuid.uuid4().hex[:8]}")

    transcript_text: str | None = None
    method = "transcribed"
    caption_word_count = 0

    if not req.force_transcribe:
        transcript_text = _fetch_youtube_transcript(
            video_id,
            req.language,
            req.prefer_generated_captions,
        )
        caption_word_count = _count_words(transcript_text)
        if transcript_text and caption_word_count >= MIN_CAPTION_WORDS:
            method = "captions"
        else:
            transcript_text = None

    if not transcript_text:
        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                audio_path = _download_audio(req.youtube_url, Path(tmp_dir))
                transcript_text, stt_info = _transcribe_audio(audio_path, req.language)
        except RuntimeError as exc:
            # If YouTube blocks direct audio extraction, salvage the run by falling
            # back to captions even when the request preferred forced transcription.
            if _is_youtube_download_blocked(str(exc)):
                transcript_text = _fetch_youtube_transcript(video_id, req.language, True)
                caption_word_count = _count_words(transcript_text)
                if transcript_text and caption_word_count >= MIN_TRANSCRIPT_WORDS:
                    method = "captions_fallback_after_block"
                    stt_info = {
                        "stt_backend": "captions",
                        "stt_model": "youtube-captions",
                        "stt_device": None,
                        "stt_compute_type": None,
                    }
                else:
                    raise
            else:
                raise
    else:
        stt_info = {
            "stt_backend": "captions",
            "stt_model": "youtube-captions",
            "stt_device": None,
            "stt_compute_type": None,
        }

    transcript_word_count = _count_words(transcript_text)

    if not transcript_text:
        raise RuntimeError("Transcript could not be fetched or generated")
    if transcript_word_count < MIN_TRANSCRIPT_WORDS:
        raise RuntimeError(
            f"Transcript looks incomplete ({transcript_word_count} words). "
            "Try again with a clearer source video or a larger model/runtime."
        )

    output_path = _write_transcript(transcript_text, filename)
    return {
        "ok": True,
        "method": method,
        "video_id": video_id,
        "transcript_path": str(output_path),
        "saved_to_host": f"./output/transcripts/{output_path.name}",
        "filename": output_path.name,
        "word_count": transcript_word_count,
        "caption_word_count": caption_word_count,
        "whisper_model": WHISPER_MODEL_SIZE,
        "whisper_device": stt_info.get("stt_device"),
        "whisper_compute_type": stt_info.get("stt_compute_type"),
        "stt_backend": stt_info.get("stt_backend"),
        "stt_model": stt_info.get("stt_model"),
        "stt_device": stt_info.get("stt_device"),
        "stt_compute_type": stt_info.get("stt_compute_type"),
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
