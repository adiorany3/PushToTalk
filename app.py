import hashlib
import re
import sqlite3
from io import BytesIO
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

import qrcode
import streamlit as st


# =========================
# KONFIGURASI DASAR
# =========================

SERVER_URL = "https://pushtotalk.streamlit.app/"

BASE_DIR = Path("ptt_data")
AUDIO_DIR = BASE_DIR / "audio"
DB_PATH = BASE_DIR / "ptt.sqlite3"
TZ = ZoneInfo("Asia/Jakarta")


# =========================
# FUNGSI BANTUAN
# =========================

def init_storage():
    BASE_DIR.mkdir(exist_ok=True)
    AUDIO_DIR.mkdir(exist_ok=True)

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                room TEXT NOT NULL,
                sender TEXT NOT NULL,
                filename TEXT NOT NULL,
                mime_type TEXT NOT NULL,
                audio_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                note TEXT,
                UNIQUE(room, audio_hash)
            )
        """)
        conn.commit()


def safe_slug(value: str, fallback: str = "umum") -> str:
    value = (value or "").strip().lower()
    value = re.sub(r"[^a-z0-9_-]+", "-", value)
    value = value.strip("-")
    return value[:40] or fallback


def clean_name(value: str, fallback: str = "Anonim") -> str:
    value = (value or "").strip()
    value = re.sub(r"[<>]", "", value)
    return value[:30] or fallback


def now_jakarta() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")


def make_room_url(room: str) -> str:
    base_url = SERVER_URL.rstrip("/")
    return f"{base_url}/?room={room}"


def make_qr_png(data: str) -> bytes:
    qr = qrcode.QRCode(
        version=None,
        box_size=8,
        border=2
    )
    qr.add_data(data)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


def save_message(room: str, sender: str, audio_bytes: bytes, mime_type: str, note: str = ""):
    audio_hash = hashlib.sha256(audio_bytes).hexdigest()
    timestamp = datetime.now(TZ).strftime("%Y%m%d_%H%M%S")
    filename = f"{room}_{timestamp}_{audio_hash[:12]}.wav"
    audio_path = AUDIO_DIR / filename

    audio_path.write_bytes(audio_bytes)

    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("""
                INSERT INTO messages
                (room, sender, filename, mime_type, audio_hash, created_at, note)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                room,
                sender,
                filename,
                mime_type or "audio/wav",
                audio_hash,
                now_jakarta(),
                note.strip()
            ))
            conn.commit()

        return True, "Pesan suara berhasil dikirim."

    except sqlite3.IntegrityError:
        if audio_path.exists():
            audio_path.unlink()
        return False, "Pesan ini sudah pernah dikirim."


def get_messages(room: str, limit: int = 30):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT id, sender, filename, mime_type, created_at, note
            FROM messages
            WHERE room = ?
            ORDER BY id DESC
            LIMIT ?
        """, (room, limit)).fetchall()

    return rows


def clear_room(room: str):
    rows = get_messages(room, limit=10_000)

    for row in rows:
        audio_path = AUDIO_DIR / row["filename"]
        if audio_path.exists():
            audio_path.unlink()

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM messages WHERE room = ?", (room,))
        conn.commit()


# =========================
# APP STREAMLIT
# =========================

st.set_page_config(
    page_title="PTT Sederhana",
    page_icon="🎙️",
    layout="centered"
)

init_storage()

query_room = st.query_params.get("room", "umum")
default_room = safe_slug(query_room, fallback="umum")

st.title("🎙️ PTT Sederhana")
st.caption("Push-to-talk sederhana berbasis voice message. Tidak real-time, tetapi stabil dan mudah dipakai.")

with st.sidebar:
    st.header("Pengaturan")

    sender = clean_name(
        st.text_input("Nama pengguna", value="User")
    )

    room_input = st.text_input("Channel / Room", value=default_room)
    room = safe_slug(room_input, fallback="umum")

    if st.query_params.get("room") != room:
        st.query_params["room"] = room

    room_url = make_room_url(room)

    limit = st.slider(
        "Jumlah pesan ditampilkan",
        min_value=5,
        max_value=100,
        value=30,
        step=5
    )

    st.divider()

    st.subheader("Bagikan Room")
    st.write("Link room:")
    st.code(room_url, language="text")

    st.link_button(
        "Buka Room Ini",
        room_url,
        use_container_width=True
    )

    qr_png = make_qr_png(room_url)
    st.image(qr_png, caption="Scan QR untuk masuk ke room ini")

    st.caption("Gunakan link atau QR yang sama agar beberapa pengguna masuk ke channel yang sama.")

    st.divider()

    if st.checkbox("Tampilkan tombol hapus room"):
        if st.button("Hapus semua pesan di room ini", type="secondary"):
            clear_room(room)
            st.success("Semua pesan di room ini sudah dihapus.")
            st.rerun()


st.subheader(f"Channel: #{room}")

st.info(
    "Cara pakai: rekam suara, berhenti rekam, lalu klik tombol kirim. "
    "Pengguna lain dapat menekan tombol refresh untuk melihat pesan terbaru."
)

note = st.text_input(
    "Catatan singkat opsional",
    placeholder="Contoh: untuk tim umum, urgent, info lapangan..."
)

audio_file = st.audio_input(
    "Tekan untuk rekam pesan suara",
    sample_rate=16000
)

col1, col2 = st.columns([1, 1])

with col1:
    send_clicked = st.button(
        "Kirim Pesan Suara",
        type="primary",
        disabled=audio_file is None,
        use_container_width=True
    )

with col2:
    if st.button("Refresh Pesan", use_container_width=True):
        st.rerun()

if send_clicked and audio_file is not None:
    audio_bytes = audio_file.getvalue()
    mime_type = getattr(audio_file, "type", "audio/wav")

    ok, message = save_message(
        room=room,
        sender=sender,
        audio_bytes=audio_bytes,
        mime_type=mime_type,
        note=note
    )

    if ok:
        st.success(message)
        st.rerun()
    else:
        st.warning(message)


st.divider()
st.subheader("Pesan Terbaru")

messages = get_messages(room, limit=limit)

if not messages:
    st.write("Belum ada pesan di channel ini.")
else:
    for msg in messages:
        audio_path = AUDIO_DIR / msg["filename"]

        with st.container(border=True):
            st.markdown(f"**{msg['sender']}**")
            st.caption(msg["created_at"])

            if msg["note"]:
                st.write(msg["note"])

            if audio_path.exists():
                st.audio(
                    audio_path.read_bytes(),
                    format=msg["mime_type"] or "audio/wav"
                )
            else:
                st.warning("File audio tidak ditemukan.")
