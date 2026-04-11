import asyncio
import argparse
import edge_tts

async def run(text_file, out_file, voice):
    text = open(text_file, "r", encoding="utf-8").read().strip()
    if not text:
        raise RuntimeError("Empty script text")
    communicate = edge_tts.Communicate(text=text, voice=voice)
    await communicate.save(out_file)

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--text", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--voice", default="en-US-AndrewMultilingualNeural")
    a = p.parse_args()
    asyncio.run(run(a.text, a.out, a.voice))
    print("TTS saved:", a.out)
