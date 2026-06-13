"""
FastAPI backend — thread management + LLM chat with universal memory.
Supports OpenAI, Gemini, or Groq via a single PROVIDER env var.
"""

import os
from contextlib import asynccontextmanager
from typing import Optional

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import Message, Thread, get_db, init_db

load_dotenv()

# ── LLM provider bootstrap ──────────────────────────────────────────────────

PROVIDER = os.getenv("PROVIDER", "groq").lower()
LLM_MODEL = os.getenv("LLM_MODEL", "")
MEMORY_MESSAGES = int(os.getenv("MEMORY_MESSAGES", "10"))  # cross-thread memory window


def _get_client():
    """Return (client, model_name) for the configured provider."""
    if PROVIDER == "openai":
        from openai import OpenAI
        model = LLM_MODEL or "gpt-4o-mini"
        return OpenAI(api_key=os.getenv("OPENAI_API_KEY")), model

    if PROVIDER == "gemini":
        from openai import OpenAI  # Gemini exposes an OpenAI-compat endpoint
        model = LLM_MODEL or "gemini-2.0-flash"
        return OpenAI(
            api_key=os.getenv("GEMINI_API_KEY"),
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        ), model

    # default → groq
    from groq import Groq
    model = LLM_MODEL or "llama-3.3-70b-versatile"
    return Groq(api_key=os.getenv("GROQ_API_KEY")), model


# ── App lifecycle ────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Mini AI Chat", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Schemas ──────────────────────────────────────────────────────────────────

class ThreadCreate(BaseModel):
    title: Optional[str] = "New Thread"


class ThreadRename(BaseModel):
    title: str


class ChatRequest(BaseModel):
    thread_id: int
    message: str


# ── Thread endpoints ─────────────────────────────────────────────────────────

@app.get("/threads")
def list_threads(db: Session = Depends(get_db)):
    threads = db.query(Thread).order_by(Thread.created_at.desc()).all()
    return [
        {"id": t.id, "title": t.title, "created_at": t.created_at.isoformat()}
        for t in threads
    ]


@app.post("/threads", status_code=201)
def create_thread(body: ThreadCreate, db: Session = Depends(get_db)):
    thread = Thread(title=body.title or "New Thread")
    db.add(thread)
    db.commit()
    db.refresh(thread)
    return {"id": thread.id, "title": thread.title, "created_at": thread.created_at.isoformat()}


@app.patch("/threads/{thread_id}")
def rename_thread(thread_id: int, body: ThreadRename, db: Session = Depends(get_db)):
    thread = db.get(Thread, thread_id)
    if not thread:
        raise HTTPException(404, "Thread not found")
    thread.title = body.title
    db.commit()
    return {"id": thread.id, "title": thread.title}


@app.delete("/threads/{thread_id}", status_code=204)
def delete_thread(thread_id: int, db: Session = Depends(get_db)):
    thread = db.get(Thread, thread_id)
    if not thread:
        raise HTTPException(404, "Thread not found")
    db.delete(thread)
    db.commit()


# ── Message endpoints ────────────────────────────────────────────────────────

@app.get("/threads/{thread_id}/messages")
def get_messages(thread_id: int, db: Session = Depends(get_db)):
    thread = db.get(Thread, thread_id)
    if not thread:
        raise HTTPException(404, "Thread not found")
    return [
        {
            "id": m.id,
            "role": m.role,
            "content": m.content,
            "created_at": m.created_at.isoformat(),
        }
        for m in thread.messages
    ]


# ── Chat endpoint ────────────────────────────────────────────────────────────

def _build_universal_memory(current_thread_id: int, db: Session) -> list[dict]:
    """
    Pull the last MEMORY_MESSAGES messages across ALL threads (excluding
    the current one) and wrap them in a <memory> block for the system prompt.
    """
    rows = (
        db.query(Message)
        .filter(Message.thread_id != current_thread_id)
        .order_by(Message.created_at.desc())
        .limit(MEMORY_MESSAGES)
        .all()
    )
    if not rows:
        return []

    rows.reverse()
    lines = ["<past_conversations>"]
    for m in rows:
        lines.append(f"  [{m.role.upper()}] {m.content}")
    lines.append("</past_conversations>")
    return [{"role": "system", "content": "\n".join(lines)}]


SYSTEM_PROMPT = (
    "You are a helpful, concise AI assistant. "
    "When <past_conversations> context is provided, use it to remember "
    "facts and preferences the user has shared in previous threads, "
    "but do not explicitly mention the tags."
)


@app.post("/chat")
def chat(body: ChatRequest, db: Session = Depends(get_db)):
    thread = db.get(Thread, body.thread_id)
    if not thread:
        raise HTTPException(404, "Thread not found")

    # Persist user message
    user_msg = Message(thread_id=body.thread_id, role="user", content=body.message)
    db.add(user_msg)
    db.commit()

    # Auto-title thread from first message
    if len(thread.messages) == 1:
        thread.title = body.message[:60] + ("…" if len(body.message) > 60 else "")
        db.commit()

    # Build message list for LLM
    memory_context = _build_universal_memory(body.thread_id, db)
    history = [
        {"role": m.role, "content": m.content}
        for m in thread.messages
    ]
    llm_messages = [{"role": "system", "content": SYSTEM_PROMPT}] + memory_context + history

    # Call LLM
    try:
        client, model = _get_client()
        response = client.chat.completions.create(
            model=model,
            messages=llm_messages,
            max_tokens=1024,
            temperature=0.7,
        )
        reply = response.choices[0].message.content
    except Exception as exc:
        raise HTTPException(500, f"LLM error: {exc}") from exc

    # Persist assistant reply
    assistant_msg = Message(thread_id=body.thread_id, role="assistant", content=reply)
    db.add(assistant_msg)
    db.commit()

    return {
        "reply": reply,
        "thread_title": thread.title,
        "message_id": assistant_msg.id,
    }


# ── Health ───────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "provider": PROVIDER}
