# ThreadMind

ThreadMind is an AI-powered chatbot that remembers conversations and maintains context across interactions. Built with FastAPI and Gemini, it is designed to evolve with persistent memory, vector search, RAG, and AI agent capabilities for more personalized and intelligent conversations.

## Features

- **Threads**: every chat is its own thread with full history, auto-generated titles, rename, delete and search.
- **Long-term memory**: after each reply ThreadMind extracts durable facts about you (name, preferences, projects) and uses them in every thread. View, add or forget memories from the Memory panel.
- **Streaming replies** with a stop button, regenerate, retry on errors, and copy buttons.
- **Markdown rendering** with syntax-highlighted code blocks and tables.
- Light/dark theme, mobile layout, export a chat as Markdown, `Ctrl+K` for a new chat.
- Everything is stored in SQLite (`backend/threadmind.db`). Chats from the old single-table schema are imported automatically.

## Getting started

```bash
cd backend
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env              # then put your Gemini API key in .env
uvicorn main:app --reload
```

Open http://localhost:8000. Get a Gemini API key at https://aistudio.google.com/apikey.

## API

All `/api` endpoints except `/api/health` need an `X-User-Id` header. The web UI generates one per browser.

| Method | Path | Description |
| --- | --- | --- |
| GET | `/api/health` | Server status and whether a Gemini key is configured |
| GET / POST | `/api/threads` | List or create threads |
| GET / PATCH / DELETE | `/api/threads/{id}` | Get a thread with its messages, rename, delete |
| POST | `/api/threads/{id}/messages` | Send `{"content": "..."}`; streams the reply as NDJSON |
| POST | `/api/threads/{id}/regenerate` | Regenerate the last reply (streams NDJSON) |
| GET / POST / DELETE | `/api/memories` | List, add `{"content": "..."}`, or clear memories |
| DELETE | `/api/memories/{id}` | Forget one memory |

Streamed events are one JSON object per line: `user`, `delta` (`text`), `done` (`message`, `thread`) or `error`.

## Tests

```bash
cd backend
pip install -r requirements-dev.txt
python -m pytest tests
```
