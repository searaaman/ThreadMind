import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()

from fastapi import Depends, FastAPI, Header, HTTPException  # noqa: E402
from fastapi.responses import StreamingResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

import database as db  # noqa: E402
from llm import MODEL, GeminiLLM  # noqa: E402

log = logging.getLogger("threadmind")

DEFAULT_TITLE = "New chat"
MAX_MEMORIES = 100

_llm = GeminiLLM()
_background_tasks = set()


def get_llm():
    return _llm


@asynccontextmanager
async def lifespan(app):
    db.init_db()
    yield


app = FastAPI(title="ThreadMind", lifespan=lifespan)


def current_user(x_user_id: str = Header(..., min_length=1, max_length=128)):
    return x_user_id.strip()


class ThreadCreate(BaseModel):
    title: str = Field(DEFAULT_TITLE, min_length=1, max_length=200)


class ThreadRename(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)


class MessageCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=20000)


class MemoryCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=500)


def require_thread(user_id, thread_id):
    thread = db.get_thread(user_id, thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    return thread


def event(payload):
    return json.dumps(payload) + "\n"


def fallback_title(message):
    title = " ".join(message.split())
    return title if len(title) <= 50 else title[:47].rstrip() + "..."


async def remember(llm, user_id, user_message, assistant_message):
    try:
        known = [m["content"] for m in db.list_memories(user_id)]
        if len(known) >= MAX_MEMORIES:
            return
        for fact in await llm.extract_memories(known, user_message, assistant_message):
            if fact not in known:
                db.add_memory(user_id, fact)
    except Exception:
        log.exception("Memory extraction failed")


async def reply_stream(llm, user_id, thread):
    """Stream the assistant reply for the thread's current history as NDJSON events."""
    thread_id = thread["id"]
    history = db.get_messages(thread_id)
    memories = [m["content"] for m in db.list_memories(user_id)]
    parts = []

    try:
        async for text in llm.stream_reply(history, memories):
            parts.append(text)
            yield event({"type": "delta", "text": text})
    except (asyncio.CancelledError, GeneratorExit):
        # Client hit "stop" and disconnected: keep what was generated so far.
        if parts:
            db.save_message(thread_id, "assistant", "".join(parts))
        raise
    except Exception as exc:
        log.exception("Reply generation failed")
        if parts:
            db.save_message(thread_id, "assistant", "".join(parts))
        yield event({"type": "error", "error": str(exc) or "Generation failed"})
        return

    reply = "".join(parts)
    message = db.save_message(thread_id, "assistant", reply)

    user_message = next((m["content"] for m in reversed(history) if m["role"] == "user"), "")
    if thread["title"] == DEFAULT_TITLE and user_message:
        try:
            title = await llm.generate_title(user_message) or fallback_title(user_message)
        except Exception:
            title = fallback_title(user_message)
        db.rename_thread(user_id, thread_id, title[:200])

    yield event({"type": "done", "message": message, "thread": db.get_thread(user_id, thread_id)})

    task = asyncio.create_task(remember(llm, user_id, user_message, reply))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


@app.get("/api/health")
def health(llm: GeminiLLM = Depends(get_llm)):
    return {"status": "ok", "model": MODEL, "llm_configured": llm.configured}


@app.get("/api/threads")
def list_threads(user_id: str = Depends(current_user)):
    return db.list_threads(user_id)


@app.post("/api/threads", status_code=201)
def create_thread(body: ThreadCreate = ThreadCreate(), user_id: str = Depends(current_user)):
    return db.create_thread(user_id, body.title.strip() or DEFAULT_TITLE)


@app.get("/api/threads/{thread_id}")
def get_thread(thread_id: int, user_id: str = Depends(current_user)):
    thread = require_thread(user_id, thread_id)
    return {**thread, "messages": db.get_messages(thread_id)}


@app.patch("/api/threads/{thread_id}")
def rename_thread(thread_id: int, body: ThreadRename, user_id: str = Depends(current_user)):
    require_thread(user_id, thread_id)
    return db.rename_thread(user_id, thread_id, body.title.strip())


@app.delete("/api/threads/{thread_id}", status_code=204)
def delete_thread(thread_id: int, user_id: str = Depends(current_user)):
    if not db.delete_thread(user_id, thread_id):
        raise HTTPException(status_code=404, detail="Thread not found")


@app.post("/api/threads/{thread_id}/messages")
def send_message(
    thread_id: int,
    body: MessageCreate,
    user_id: str = Depends(current_user),
    llm: GeminiLLM = Depends(get_llm),
):
    thread = require_thread(user_id, thread_id)
    content = body.content.strip()
    if not content:
        raise HTTPException(status_code=422, detail="Message is empty")
    user_message = db.save_message(thread_id, "user", content)

    async def stream():
        yield event({"type": "user", "message": user_message})
        async for chunk in reply_stream(llm, user_id, thread):
            yield chunk

    return StreamingResponse(stream(), media_type="application/x-ndjson")


@app.post("/api/threads/{thread_id}/regenerate")
def regenerate(
    thread_id: int,
    user_id: str = Depends(current_user),
    llm: GeminiLLM = Depends(get_llm),
):
    thread = require_thread(user_id, thread_id)
    db.delete_last_assistant_message(thread_id)
    messages = db.get_messages(thread_id)
    if not messages or messages[-1]["role"] != "user":
        raise HTTPException(status_code=400, detail="Nothing to regenerate")
    return StreamingResponse(reply_stream(llm, user_id, thread), media_type="application/x-ndjson")


@app.get("/api/memories")
def list_memories(user_id: str = Depends(current_user)):
    return db.list_memories(user_id)


@app.post("/api/memories", status_code=201)
def add_memory(body: MemoryCreate, user_id: str = Depends(current_user)):
    return db.add_memory(user_id, body.content.strip())


@app.delete("/api/memories/{memory_id}", status_code=204)
def delete_memory(memory_id: int, user_id: str = Depends(current_user)):
    if not db.delete_memory(user_id, memory_id):
        raise HTTPException(status_code=404, detail="Memory not found")


@app.delete("/api/memories", status_code=204)
def clear_memories(user_id: str = Depends(current_user)):
    db.clear_memories(user_id)


STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
