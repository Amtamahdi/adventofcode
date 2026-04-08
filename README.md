# AI Video Factory (Local, n8n + Ollama + TTS Worker)

Ce projet permet de générer localement des vidéos verticales (format mobile) à partir de tendances, avec narration TTS, sous-titres et rendu vidéo via FFmpeg.

## Stack

- **n8n**: orchestration visuelle du workflow
- **Ollama**: génération texte locale (LLM)
- **tts-worker (FastAPI)**: génération audio et rendu vidéo
- **FFmpeg**: composition vidéo + sous-titres

## Structure du repo

```text
.
├── docker-compose.yml
├── docs/
│   └── n8n_ai_video_factory_guide.md
├── tts-worker/
│   ├── Dockerfile
│   └── app.py
├── assets/
│   └── bg/
│       └── night1.mp4
├── output/
└── n8n/
```

## Démarrage rapide

```bash
# Depuis la racine du projet
docker compose up -d --build

# (Optionnel) pull d'un modèle léger
docker exec ollama ollama pull qwen2.5:1.5b
```

UI:
- n8n: http://localhost:5678
- tts-worker health: http://localhost:8000/health

Stop:

```bash
docker compose down
```

## Workflow n8n (résumé)

1. Récupération tendances
2. Génération multi-drafts
3. Sélection (judge)
4. TTS depuis `{{$json.script}}`
5. Rendu vertical via `/render-vertical`

Le guide complet est ici:
- `docs/n8n_ai_video_factory_guide.md`

## Fichiers générés

Dans `./output`:
- `monologue_*.mp3`
- `doc_*.srt`
- `doc_*.mp4`

## Mettre ce repo en privé sur GitHub

Je ne peux pas modifier directement la visibilité de ton dépôt GitHub depuis ici, mais tu peux le faire en 1 minute:

1. Ouvre ton repo sur GitHub
2. `Settings` → `General`
3. Descends à `Danger Zone`
4. Clique **Change repository visibility**
5. Sélectionne **Make private**
6. Confirme le nom du repo

Alternative via GitHub CLI:

```bash
gh repo edit --visibility private
```

(Exécute la commande depuis le repo local, après `gh auth login`.)
