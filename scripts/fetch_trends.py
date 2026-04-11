import json
import requests
from datetime import datetime, timezone

OUT = "/workspace/data/trends.json"

def get_reddit():
    url = "https://www.reddit.com/r/all/hot.json?limit=20"
    headers = {"User-Agent": "ai-video-factory/1.0"}
    data = requests.get(url, headers=headers, timeout=20).json()
    trends = []
    for c in data.get("data", {}).get("children", []):
        d = c.get("data", {})
        title = d.get("title", "").strip()
        if not title:
            continue
        trends.append({
            "source": "reddit",
            "title": title,
            "url": "https://reddit.com" + d.get("permalink", ""),
            "score": float(d.get("ups", 0)),
            "text": d.get("selftext", "")[:1200]
        })
    return trends

def get_hn():
    trends = []
    top = requests.get("https://hacker-news.firebaseio.com/v0/topstories.json", timeout=20).json()[:30]
    for i in top[:20]:
        item = requests.get(f"https://hacker-news.firebaseio.com/v0/item/{i}.json", timeout=20).json()
        if not item:
            continue
        title = (item.get("title") or "").strip()
        if not title:
            continue
        trends.append({
            "source": "hackernews",
            "title": title,
            "url": item.get("url", f"https://news.ycombinator.com/item?id={i}"),
            "score": float(item.get("score", 0)),
            "text": ""
        })
    return trends

def dedupe(items):
    seen = set()
    out = []
    for x in items:
        k = x["title"].lower().strip()
        if k in seen:
            continue
        seen.add(k)
        out.append(x)
    return out

def main():
    items = []
    try:
        items.extend(get_reddit())
    except Exception as e:
        print("reddit failed:", e)

    try:
        items.extend(get_hn())
    except Exception as e:
        print("hn failed:", e)

    if not items:
        items = [{
            "source":"fallback",
            "title":"AI software architecture trends",
            "url":"https://example.com",
            "score":1.0,
            "text":"Fallback topic because sources failed."
        }]

    items = dedupe(items)
    items.sort(key=lambda x: x["score"], reverse=True)
    top = items[:5]

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "trends": top
    }

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"Wrote {len(top)} trends to {OUT}")

if __name__ == "__main__":
    main()
