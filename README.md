# Quick Local Computer Agent Demo

This repository now includes a very small Playwright script for the use case:

- use your own browser session
- no API
- simple enough to test quickly
- manual login for your own account

## Files

- `quick_agent.py`: runs a simple browser automation plan
- `plan.example.json`: sample JSON plan you can copy and edit
- `main.py`: existing Advent of Code script left unchanged

## Quick start

1. Install Playwright:

   ```bash
   pip install playwright
   python -m playwright install chromium
   ```

2. Run the default demo:

   ```bash
   python quick_agent.py --keep-open
   ```

   It will:
   - open ChatGPT in a normal Chromium window
   - wait for you to log in manually
   - continue after you press Enter in the terminal

3. Run your own plan:

   ```bash
   cp plan.example.json my-plan.json
   python quick_agent.py --plan my-plan.json --keep-open
   ```

## Supported step types

Each plan file is a JSON array of steps.

### Open a page

```json
{ "action": "goto", "url": "https://example.com" }
```

### Click something

```json
{ "action": "click", "selector": "button" }
```

### Fill an input instantly

```json
{ "action": "fill", "selector": "textarea", "text": "hello" }
```

### Type like a person

```json
{ "action": "type", "selector": "textarea", "text": "hello", "delay_ms": 80 }
```

### Wait for an element

```json
{ "action": "wait_for", "selector": "text=Profile" }
```

### Sleep a little

```json
{ "action": "sleep", "ms": 1500 }
```

### Stop and let you take over

```json
{ "action": "pause" }
```

### Print a note in the terminal

```json
{ "action": "note", "message": "Check the page before continuing." }
```

## Why this is useful for a quick test

This is not a full AI agent. It is a tiny local browser automation runner.

That makes it good for a fast reality check:

- you can see whether browser automation is enough for your workflow
- you can use your real account manually
- you do not need to build an API-based system first

If this feels promising, the next step would be adding saved login state, better selectors, retries, or a caption-generation layer.


## n8n + Docker video pipeline

A full start-to-finish guide (including Docker, n8n flow, TTS, and vertical video render) is available at:

- `docs/n8n_ai_video_factory_guide.md`
