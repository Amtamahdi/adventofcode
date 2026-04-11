#!/usr/bin/env bash
set -euo pipefail

AUDIO="/workspace/data/voice.mp3"
SRT="/workspace/data/subtitles.srt"
TITLE_FILE="/workspace/data/video_title.txt"
OUT="/workspace/output/video_$(date +%F_%H%M%S).mp4"

TITLE=$(cat "$TITLE_FILE" | tr "'" " " | head -c 120)

DUR=$(ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 "$AUDIO")
DUR_INT=$(python3 - <<PY
import math
print(max(1, math.ceil(float("$DUR"))))
PY
)

ffmpeg -y \
  -f lavfi -i "color=c=black:s=1920x1080:r=30:d=${DUR_INT}" \
  -i "$AUDIO" \
  -vf "drawtext=text='${TITLE}':fontcolor=white:fontsize=54:x=(w-text_w)/2:y=(h-text_h)/2-220,subtitles=${SRT}:force_style='Alignment=5,FontName=Arial,FontSize=26,PrimaryColour=&H00FFFFFF&,OutlineColour=&H00000000&,BorderStyle=3,Outline=1,MarginV=50'" \
  -c:v libx264 -preset veryfast -crf 23 \
  -c:a aac -b:a 192k \
  -shortest "$OUT"

echo "VIDEO_READY=$OUT"
