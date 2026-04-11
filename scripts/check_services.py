from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request


CHECKS = [
    ("n8n", "http://localhost:5678/healthz"),
    ("tts-worker", "http://localhost:8000/health"),
]


def fetch_json(url: str) -> tuple[bool, str]:
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            payload = response.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as exc:
        return False, f"{type(exc.reason).__name__ if getattr(exc, 'reason', None) else 'URLError'}: {exc.reason}"
    except Exception as exc:  # pragma: no cover
        return False, str(exc)

    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return True, payload.strip()

    return True, json.dumps(data, ensure_ascii=False)


def main() -> int:
    failed = False

    for name, url in CHECKS:
        ok, detail = fetch_json(url)
        status = "OK" if ok else "FAIL"
        print(f"[{status}] {name}: {detail}")
        if not ok:
            failed = True

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
