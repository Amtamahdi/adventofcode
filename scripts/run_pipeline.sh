#!/usr/bin/env bash
set -euo pipefail

python3 /workspace/scripts/fetch_trends.py
python3 /workspace/scripts/generate_script.py
python3 /workspace/scripts/make_tts.py --text /workspace/data/final_script.txt --out /workspace/data/voice.mp3 --voice en-US-AndrewMultilingualNeural
python3 /workspace/scripts/make_srt.py
bash /workspace/scripts/render_video.sh
