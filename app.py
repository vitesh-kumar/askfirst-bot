"""
Streamlit frontend for the mini AI chat app.
Run:  streamlit run app.py
"""

import os
import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

API_BASE = os.getenv("API_BASE", "http://localhost:8000")

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="ThreadMind",
    page_icon="🧵",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────

st.markdown(
    """
    <style>
    /* ---- global ---- */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap');

    html, body, [data-testid="stAppViewContainer"] {
        background: #0d0f14;
        color: #e2e5ed;
        font-family: 'Inter', sans-serif;
    }

    /* ---- sidebar ---- */
    [data-testid="stSidebar"] {
        background: #13161e !important;
        border-right: 1px solid #1f2330;
    }
    [data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3, [data-testid="stSidebar"] label {
        color: #e2e5ed !important;
    }

    /* ---- thread buttons ---- */
    .thread-btn {
        display: block;
        width: 100%;
        padding: 9px 14px;
        margin-bottom: 4px;
        border-radius: 8px;
        border: 1px solid transparent;
        background: transparent;
        color: #9ba3b8;
        font-size: 13px;
        text-align: left;
        cursor: pointer;
        transition: background 0.15s, color 0.15s;
        font-family: 'Inter', sans-serif;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    .thread-btn:hover { background: #1c2030; color: #e2e5ed; }
    .thread-btn.active {
        background: #1e2540;
        border-color: #3d52a0;
        color: #c5cfff;
        font-weight: 500;
    }

    /* ---- chat bubbles ---- */
    .bubble-wrapper { display: flex; margin-bottom: 18px; gap: 12px; }
    .bubble-wrapper.user  { flex-direction: row-reverse; }
    .bubble-wrapper.assistant { flex-direction: row; }

    .avatar {
        width: 34px; height: 34px; border-radius: 50%;
        display: flex; align-items: center; justify-content: center;
        font-size: 15px; flex-shrink: 0;
    }
    .avatar.user      { background: #3d52a0; }
    .avatar.assistant { background: #1f2330; border: 1px solid #2d3347; }

    .bubble {
        max-width: 72%;
        padding: 11px 16px;
        border-radius: 14px;
        font-size: 14px;
        line-height: 1.6;
        white-space: pre-wrap;
        word-wrap: break-word;
    }
    .bubble.user {
        background: #2a3660;
        border-bottom-right-radius: 4px;
        color: #dde3ff;
    }
    .bubble.assistant {
        background: #16192400;
        border: 1px solid #1f2330;
        border-bottom-left-radius: 4px;
        color: #d4d8e8;
        font-family: 'Inter', sans-serif;
    }

    /* ---- input area ---- */
    .stTextInput > div > div > input,
    .stTextArea textarea {
        background: #13161e !important;
        border: 1px solid #1f2330 !important;
        border-radius: 10px !important;
        color: #e2e5ed !important;
        font-family: 'Inter', sans-serif !important;
        font-size: 14px !important;
    }

    /* ---- buttons ---- */
    .stButton > button {
        background: #1e2540 !important;
        color: #c5cfff !important;
        border: 1px solid #3d52a0 !important;
        border-radius: 8px !important;
        font-family: 'Inter', sans-serif !important;
        font-size: 13px !important;
        font-weight: 500 !important;
        transition: background 0.15s !important;
    }
    .stButton > button:hover {
        background: #26306a !important;
    }

    /* primary send button */
    [data-testid="stFormSubmitButton"] > button {
        background: #3d52a0 !important;
        border-color: #3d52a0 !important;
        color: #fff !important;
        font-size: 15px !important;
        padding: 4px 20px !important;
    }
    [data-testid="stFormSubmitButton"] > button:hover {
        background: #4e65c8 !important;
    }

    /* ---- header ---- */
    .chat-header {
        display: flex; align-items: center; gap: 10px;
        padding: 12px 0 18px;
        border-bottom: 1px solid #1f2330;
        margin-bottom: 20px;
    }
    .chat-header .thread-icon { font-size: 20px; }
    .chat-header .thread-name {
        font-size: 16px; font-weight: 600; color: #e2e5ed;
        flex: 1;
    }
    .chat-header .memory-badge {
        font-size: 11px; color: #6b7aa1;
        background: #13161e; border: 1px solid #1f2330;
        border-radius: 20px; padding: 3px 10px;
    }

    /* ---- empty state ---- */
    .empty-state {
        display: flex; flex-direction: column;
        align-items: center; justify-content: center;
        height: 60vh; gap: 12px; color: #4a5068;
    }
    .empty-state .icon { font-size: 48px; }
    .empty-state p { font-size: 14px; }

    div[data-testid="stMarkdownContainer"] p { color: inherit; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Helpers ───────────────────────────────────────────────────────────────────

def api(method: str, path: str, **kwargs):
    try:
        r = getattr(requests, method)(f"{API_BASE}{path}", timeout=60, **kwargs)
        r.raise_for_status()
        return r.json() if r.content else None
    except requests.exceptions.ConnectionError:
        st.error("Cannot reach the API server. Is `uvicorn main:app` running?")
        st.stop()
    except requests.HTTPError as e:
        st.error(f"API error {e.response.status_code}: {e.response.text}")
        return None


def load_threads():
    return api("get", "/threads") or []


def render_bubble(role: str, content: str):
    avatar = "👤" if role == "user" else "🤖"
    st.markdown(
        f"""
        <div class="bubble-wrapper {role}">
            <div class="avatar {role}">{avatar}</div>
            <div class="bubble {role}">{content}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ── Session state ─────────────────────────────────────────────────────────────

if "active_thread" not in st.session_state:
    st.session_state.active_thread = None
if "messages_cache" not in st.session_state:
    st.session_state.messages_cache = {}
if "threads" not in st.session_state:
    st.session_state.threads = load_threads()
if "rename_mode" not in st.session_state:
    st.session_state.rename_mode = None


def refresh_threads():
    st.session_state.threads = load_threads()


# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## 🧵 ThreadMind")
    st.markdown("<hr style='border-color:#1f2330;margin:8px 0 16px'>", unsafe_allow_html=True)

    if st.button("＋  New thread", use_container_width=True):
        t = api("post", "/threads", json={"title": "New Thread"})
        if t:
            refresh_threads()
            st.session_state.active_thread = t["id"]
            st.session_state.messages_cache.pop(t["id"], None)
            st.rerun()

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    for thread in st.session_state.threads:
        tid = thread["id"]
        is_active = tid == st.session_state.active_thread
        cls = "thread-btn active" if is_active else "thread-btn"
        title = thread["title"] or "Untitled"
        short = title[:34] + "…" if len(title) > 34 else title

        col1, col2 = st.columns([5, 1])
        with col1:
            if st.button(short, key=f"t_{tid}", use_container_width=True):
                st.session_state.active_thread = tid
                st.session_state.rename_mode = None
                st.rerun()
        with col2:
            if st.button("⋯", key=f"m_{tid}"):
                st.session_state.rename_mode = tid if st.session_state.rename_mode != tid else None
                st.rerun()

        if st.session_state.rename_mode == tid:
            new_title = st.text_input("Rename", value=thread["title"], key=f"ri_{tid}", label_visibility="collapsed")
            c1, c2 = st.columns(2)
            with c1:
                if st.button("Save", key=f"rs_{tid}"):
                    api("patch", f"/threads/{tid}", json={"title": new_title})
                    refresh_threads()
                    st.session_state.rename_mode = None
                    st.rerun()
            with c2:
                if st.button("Delete", key=f"rd_{tid}"):
                    api("delete", f"/threads/{tid}")
                    if st.session_state.active_thread == tid:
                        st.session_state.active_thread = None
                    st.session_state.messages_cache.pop(tid, None)
                    refresh_threads()
                    st.session_state.rename_mode = None
                    st.rerun()

    st.markdown("<hr style='border-color:#1f2330;margin:16px 0 10px'>", unsafe_allow_html=True)

    # Provider badge
    health = api("get", "/health")
    provider = health.get("provider", "?").upper() if health else "?"
    st.markdown(
        f"<p style='font-size:11px;color:#4a5068;text-align:center'>Provider: {provider}</p>",
        unsafe_allow_html=True,
    )

# ── Main panel

if st.session_state.active_thread is None:
    st.markdown(
        """
        <div class="empty-state">
            <div class="icon">🧵</div>
            <p>Select a thread or create a new one to start chatting.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
else:
    tid = st.session_state.active_thread
    thread_info = next((t for t in st.session_state.threads if t["id"] == tid), {})
    title = thread_info.get("title", "Thread")
    memory_count = int(os.getenv("MEMORY_MESSAGES", "10"))

    st.markdown(
        f"""
        <div class="chat-header">
            <span class="thread-icon">💬</span>
            <span class="thread-name">{title}</span>
            <span class="memory-badge">🧠 Universal memory: last {memory_count} msgs</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Load & cache messages
    if tid not in st.session_state.messages_cache:
        msgs = api("get", f"/threads/{tid}/messages") or []
        st.session_state.messages_cache[tid] = msgs

    messages = st.session_state.messages_cache[tid]

    # Chat history
    chat_area = st.container()
    with chat_area:
        if not messages:
            st.markdown(
                "<p style='color:#4a5068;font-size:13px;margin-top:40px;text-align:center'>"
                "Send a message to begin this thread.</p>",
                unsafe_allow_html=True,
            )
        for m in messages:
            render_bubble(m["role"], m["content"])

    # Input form
    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
    with st.form("chat_form", clear_on_submit=True):
        col_input, col_btn = st.columns([8, 1])
        with col_input:
            user_input = st.text_input(
                "Message",
                placeholder="Type a message…",
                label_visibility="collapsed",
            )
        with col_btn:
            submitted = st.form_submit_button("↑")

    if submitted and user_input.strip():
        with st.spinner("Thinking…"):
            result = api("post", "/chat", json={"thread_id": tid, "message": user_input.strip()})
        if result:
            # Refresh messages and thread list (title may have changed)
            st.session_state.messages_cache.pop(tid, None)
            refresh_threads()
            st.rerun()
