import json
import requests

OLLAMA = "http://ollama:11434/api/chat"
IN_FILE = "/workspace/data/trends.json"
OUT_JSON = "/workspace/data/final_script.json"
OUT_TXT = "/workspace/data/final_script.txt"
OUT_TITLE = "/workspace/data/video_title.txt"

WRITER_MODEL = "qwen2.5:3b"
JUDGE_MODEL = "llama3.2:3b"

def ollama_chat(model, system, user):
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user}
        ],
        "stream": False
    }
    r = requests.post(OLLAMA, json=payload, timeout=240)
    r.raise_for_status()
    return r.json()["message"]["content"]

def main():
    data = json.load(open(IN_FILE, "r", encoding="utf-8"))
    trend = data["trends"][0]
    topic = trend["title"]

    base_system = (
        "You are an expert viral content scriptwriter. "
        "Output plain text only, no markdown. "
        "Write for a 10-minute monologue (about 1400-1700 words), clear and engaging."
    )

    prompts = {
        "A": f"Create a high-retention explainer monologue about: {topic}. Include a strong hook and smooth transitions.",
        "B": f"Create a storytelling-style monologue about: {topic}. Make it emotional but factual.",
        "C": f"Create a debate-style monologue about: {topic}. Show opposing views, then conclude clearly."
    }

    candidates = {}
    for k, p in prompts.items():
        txt = ollama_chat(WRITER_MODEL, base_system, p)
        candidates[k] = txt.strip()

    judge_system = (
        "You are a strict content judge. Choose the best script for audience retention and clarity. "
        "Respond in JSON only with keys winner, reason, scores."
    )
    judge_user = (
        "Topic: " + topic + "\n\n"
        + "Candidate A:\n" + candidates["A"] + "\n\n"
        + "Candidate B:\n" + candidates["B"] + "\n\n"
        + "Candidate C:\n" + candidates["C"] + "\n\n"
        + "Return JSON like: "
        + '{"winner":"A|B|C","reason":"...","scores":{"A":0,"B":0,"C":0}}'
    )

    judge_raw = ollama_chat(JUDGE_MODEL, judge_system, judge_user)

    # Best effort parse
    winner = "A"
    reason = "Default winner"
    scores = {"A": 0, "B": 0, "C": 0}
    try:
        j = json.loads(judge_raw)
        winner = j.get("winner", "A")
        reason = j.get("reason", reason)
        scores = j.get("scores", scores)
    except Exception:
        # fallback heuristic by length
        lens = {k: len(v) for k, v in candidates.items()}
        winner = max(lens, key=lens.get)
        reason = "Fallback length heuristic"

    final = candidates.get(winner, candidates["A"]).strip()

    result = {
        "topic": topic,
        "source_url": trend.get("url", ""),
        "winner": winner,
        "reason": reason,
        "scores": scores,
        "script": final
    }

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    with open(OUT_TXT, "w", encoding="utf-8") as f:
        f.write(final)

    with open(OUT_TITLE, "w", encoding="utf-8") as f:
        f.write(topic[:120])

    print("Wrote final script:", OUT_TXT)

if __name__ == "__main__":
    main()
