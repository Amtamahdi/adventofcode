import re
import subprocess
from pathlib import Path

SCRIPT = Path("/workspace/data/final_script.txt")
AUDIO = Path("/workspace/data/voice.mp3")
SRT = Path("/workspace/data/subtitles.srt")

def get_duration_sec(path):
    cmd = [
        "ffprobe","-v","error","-show_entries","format=duration",
        "-of","default=noprint_wrappers=1:nokey=1",str(path)
    ]
    out = subprocess.check_output(cmd).decode().strip()
    return float(out)

def fmt(t):
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = int(t % 60)
    ms = int((t - int(t)) * 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"

def chunk_text(text, chunk_words=10):
    words = re.findall(r"\S+", text)
    chunks = []
    for i in range(0, len(words), chunk_words):
        chunks.append(" ".join(words[i:i+chunk_words]))
    return chunks

def main():
    text = SCRIPT.read_text(encoding="utf-8").strip()
    duration = get_duration_sec(AUDIO)
    chunks = chunk_text(text, 10)
    if not chunks:
        chunks = [" "]
    per = duration / len(chunks)

    lines = []
    t = 0.0
    for idx, c in enumerate(chunks, start=1):
        start = t
        end = min(duration, t + per)
        lines.append(str(idx))
        lines.append(f"{fmt(start)} --> {fmt(end)}")
        lines.append(c)
        lines.append("")
        t = end

    SRT.write_text("\n".join(lines), encoding="utf-8")
    print("SRT saved:", SRT)

if __name__ == "__main__":
    main()
