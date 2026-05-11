import hashlib
import re
import sqlite3
import time
from io import BytesIO
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

import qrcode
import streamlit as st

try:
    from streamlit_autorefresh import st_autorefresh
except Exception:
    st_autorefresh = None


# =========================================================
# KONFIGURASI
# =========================================================

SERVER_URL = "https://pushtotalk.streamlit.app"

BASE_DIR = Path("ptt_data")
AUDIO_DIR = BASE_DIR / "audio"  # hanya dipakai untuk migrasi dari versi lama
DB_PATH = BASE_DIR / "ptt.sqlite3"

TZ = ZoneInfo("Asia/Jakarta")

MAX_MESSAGES_PER_ROOM = 200
DEFAULT_ROOM = "umum"


# =========================================================
# DATABASE
# =========================================================

CREATE_MESSAGES_SQL = """
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    room TEXT NOT NULL,
    sender TEXT NOT NULL,
    note TEXT,
    mime_type TEXT NOT NULL,
    audio_blob BLOB NOT NULL,
    audio_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
)
"""

CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_messages_room_id
ON messages(room, id DESC)
"""


def get_conn():
    BASE_DIR.mkdir(exist_ok=True)
    AUDIO_DIR.mkdir(exist_ok=True)

    conn = sqlite3.connect(
        DB_PATH,
        timeout=30,
        check_same_thread=False
    )

    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=30000")

    # WAL bisa gagal pada beberapa environment read-only/tertentu,
    # jadi jangan biarkan app crash hanya karena PRAGMA.
    try:
        conn.execute("PRAGMA journal_mode=WAL")
    except sqlite3.OperationalError:
        pass

    try:
        conn.execute("PRAGMA synchronous=NORMAL")
    except sqlite3.OperationalError:
        pass

    return conn


def table_exists(conn, table_name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,)
    ).fetchone()
    return row is not None


def get_columns(conn, table_name: str) -> set:
    try:
        rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        return {row["name"] for row in rows}
    except Exception:
        return set()


def reset_messages_table(conn):
    conn.execute("DROP TABLE IF EXISTS messages")
    conn.execute(CREATE_MESSAGES_SQL)
    conn.execute(CREATE_INDEX_SQL)
    conn.commit()


def migrate_old_file_schema_to_blob(conn, old_columns: set):
    """
    Migrasi dari versi lama:
    - kolom lama: filename
    - audio tersimpan di ptt_data/audio/
    - kolom baru: audio_blob

    Jika file audio lama tidak ditemukan, pesannya dilewati.
    """
    conn.execute("DROP TABLE IF EXISTS messages_new")
    conn.execute("""
        CREATE TABLE messages_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room TEXT NOT NULL,
            sender TEXT NOT NULL,
            note TEXT,
            mime_type TEXT NOT NULL,
            audio_blob BLOB NOT NULL,
            audio_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    if "filename" in old_columns:
        try:
            old_rows = conn.execute("""
                SELECT room, sender, filename, mime_type, audio_hash, created_at, note
                FROM messages
                ORDER BY id ASC
            """).fetchall()

            for row in old_rows:
                audio_path = AUDIO_DIR / str(row["filename"])
                if not audio_path.exists():
                    continue

                audio_bytes = audio_path.read_bytes()
                if not audio_bytes:
                    continue

                audio_hash = row["audio_hash"] or hashlib.sha256(audio_bytes).hexdigest()

                conn.execute("""
                    INSERT INTO messages_new
                    (room, sender, note, mime_type, audio_blob, audio_hash, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    row["room"] or DEFAULT_ROOM,
                    row["sender"] or "User",
                    row["note"] or "",
                    row["mime_type"] or "audio/wav",
                    sqlite3.Binary(audio_bytes),
                    audio_hash,
                    row["created_at"] or datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")
                ))
        except Exception:
            # Kalau migrasi data lama gagal, tetap lanjut dengan tabel kosong.
            pass

    conn.execute("DROP TABLE IF EXISTS messages")
    conn.execute("ALTER TABLE messages_new RENAME TO messages")
    conn.execute(CREATE_INDEX_SQL)
    conn.commit()


def init_db():
    with get_conn() as conn:
        if not table_exists(conn, "messages"):
            conn.execute(CREATE_MESSAGES_SQL)
            conn.execute(CREATE_INDEX_SQL)
            conn.commit()
            return

        columns = get_columns(conn, "messages")
        required = {
            "id",
            "room",
            "sender",
            "note",
            "mime_type",
            "audio_blob",
            "audio_hash",
            "created_at",
        }

        # Jika sudah sesuai, cukup pastikan index ada.
        if required.issubset(columns):
            conn.execute(CREATE_INDEX_SQL)
            conn.commit()
            return

        # Jika masih schema lama berbasis filename, migrasi otomatis.
        if "filename" in columns and "audio_blob" not in columns:
            migrate_old_file_schema_to_blob(conn, columns)
            return

        # Jika schema rusak/tidak dikenal, buat ulang agar app tidak crash.
        reset_messages_table(conn)


def execute_with_retry(action, retries: int = 3, delay: float = 0.4):
    last_error = None

    for _ in range(retries):
        try:
            return action()
        except sqlite3.OperationalError as exc:
            last_error = exc
            msg = str(exc).lower()

            if "locked" in msg or "busy" in msg:
                time.sleep(delay)
                continue

            raise

    raise last_error


def save_message(room: str, sender: str, note: str, audio_bytes: bytes, mime_type: str):
    if not audio_bytes:
        return False, "Audio kosong. Silakan rekam ulang."

    audio_hash = hashlib.sha256(audio_bytes).hexdigest()
    created_at = datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")

    def action():
        with get_conn() as conn:
            conn.execute("""
                INSERT INTO messages
                (room, sender, note, mime_type, audio_blob, audio_hash, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                room,
                sender,
                note.strip(),
                mime_type or "audio/wav",
                sqlite3.Binary(audio_bytes),
                audio_hash,
                created_at
            ))

            conn.execute("""
                DELETE FROM messages
                WHERE room = ?
                AND id NOT IN (
                    SELECT id FROM messages
                    WHERE room = ?
                    ORDER BY id DESC
                    LIMIT ?
                )
            """, (room, room, MAX_MESSAGES_PER_ROOM))

            conn.commit()

    execute_with_retry(action)
    return True, "Pesan suara berhasil dikirim."


def get_messages(room: str, limit: int):
    def action():
        with get_conn() as conn:
            return conn.execute("""
                SELECT id, room, sender, note, mime_type, audio_blob, created_at
                FROM messages
                WHERE room = ?
                ORDER BY id DESC
                LIMIT ?
            """, (room, int(limit))).fetchall()

    try:
        return execute_with_retry(action)
    except sqlite3.OperationalError as exc:
        # Recovery otomatis jika database dari versi lama/korup masih menyebabkan error.
        with get_conn() as conn:
            columns = get_columns(conn, "messages")
            if "filename" in columns and "audio_blob" not in columns:
                migrate_old_file_schema_to_blob(conn, columns)
            else:
                reset_messages_table(conn)

        st.warning(
            "Database lama terdeteksi dan sudah diperbaiki otomatis. "
            "Silakan lanjut gunakan aplikasi."
        )
        return []


def delete_message(message_id: int, room: str):
    def action():
        with get_conn() as conn:
            conn.execute(
                "DELETE FROM messages WHERE id = ? AND room = ?",
                (message_id, room)
            )
            conn.commit()

    execute_with_retry(action)


def clear_room(room: str):
    def action():
        with get_conn() as conn:
            conn.execute("DELETE FROM messages WHERE room = ?", (room,))
            conn.commit()

    execute_with_retry(action)


# =========================================================
# UTILITAS
# =========================================================

def safe_slug(value: str, fallback: str = DEFAULT_ROOM) -> str:
    value = str(value or "").strip().lower()
    value = re.sub(r"[^a-z0-9_-]+", "-", value)
    value = value.strip("-")
    return value[:40] or fallback


def clean_name(value: str, fallback: str = "User") -> str:
    value = str(value or "").strip()
    value = re.sub(r"[<>]", "", value)
    return value[:30] or fallback


def get_query_room() -> str:
    try:
        value = st.query_params.get("room", DEFAULT_ROOM)
        if isinstance(value, list):
            value = value[0] if value else DEFAULT_ROOM
        return safe_slug(value)
    except Exception:
        return DEFAULT_ROOM


def set_query_room(room: str):
    try:
        if st.query_params.get("room") != room:
            st.query_params["room"] = room
    except Exception:
        pass


def make_room_url(room: str) -> str:
    return f"{SERVER_URL.rstrip('/')}/?room={room}"


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


def copy_button_html(text: str, label: str = "Salin Link"):
    safe_text = text.replace("\\", "\\\\").replace("`", "\\`")

    st.components.v1.html(
        f"""
        <button
            onclick="navigator.clipboard.writeText(`{safe_text}`).then(() => {{
                this.innerText='Link Disalin';
                setTimeout(() => this.innerText='{label}', 1200);
            }})"
            style="
                width:100%;
                padding:0.65rem 0.75rem;
                border-radius:0.5rem;
                border:1px solid #ddd;
                background:#fff;
                cursor:pointer;
                font-size:0.95rem;
            "
        >
            {label}
        </button>
        """,
        height=48
    )


# =========================================================
# APP
# =========================================================

st.set_page_config(
    page_title="PTT Sederhana",
    page_icon="🎙️",
    layout="centered"
)

init_db()

default_room = get_query_room()

st.title("🎙️ Push To Talk Sederhana")
st.caption("Rekam suara, kirim, lalu pengguna lain menerima setelah refresh/auto-refresh.")

with st.sidebar:
    st.header("Pengaturan")

    sender = clean_name(
        st.text_input("Nama pengguna", value="User")
    )

    room_input = st.text_input("Channel / Room", value=default_room)
    room = safe_slug(room_input)

    set_query_room(room)

    room_url = make_room_url(room)

    limit = st.slider(
        "Jumlah pesan tampil",
        min_value=5,
        max_value=100,
        value=30,
        step=5
    )

    auto_refresh = st.toggle(
        "Auto-refresh pesan",
        value=True,
        help="Aktifkan agar pesan baru muncul otomatis."
    )

    refresh_seconds = st.selectbox(
        "Interval auto-refresh",
        options=[3, 5, 10, 15, 30],
        index=1,
        disabled=not auto_refresh
    )

    st.divider()

    st.subheader("Bagikan Room")
    st.code(room_url, language="text")

    copy_button_html(room_url)

    st.link_button(
        "Buka Room Ini",
        room_url,
        use_container_width=True
    )

    st.image(
        make_qr_png(room_url),
        caption="Scan QR untuk masuk ke room ini",
        use_container_width=True
    )

    st.divider()

    with st.expander("Admin room"):
        st.warning("Tombol ini menghapus semua pesan pada room aktif.")
        if st.button("Hapus Semua Pesan Room Ini", type="secondary", use_container_width=True):
            clear_room(room)
            st.success("Semua pesan pada room ini sudah dihapus.")
            st.rerun()


if auto_refresh and st_autorefresh is not None:
    st_autorefresh(
        interval=refresh_seconds * 1000,
        key=f"ptt_refresh_{room}"
    )
elif auto_refresh and st_autorefresh is None:
    st.warning(
        "Auto-refresh belum aktif karena package streamlit-autorefresh belum terpasang. "
        "Pastikan requirements.txt sudah di-update."
    )

st.subheader(f"Channel: #{room}")

st.info(
    "Tekan tombol rekam, bicara, berhenti rekam, lalu klik **Kirim Pesan Suara**. "
    "Aplikasi ini bukan voice call real-time, tetapi voice message sederhana."
)

with st.form("send_voice_message", clear_on_submit=True):
    note = st.text_input(
        "Catatan opsional",
        placeholder="Contoh: info lapangan, urgent, koordinasi..."
    )

    audio_file = st.audio_input(
        "Rekam pesan suara",
        sample_rate=16000
    )

    submitted = st.form_submit_button(
        "Kirim Pesan Suara",
        type="primary",
        use_container_width=True
    )

if submitted:
    if audio_file is None:
        st.warning("Belum ada rekaman. Silakan rekam suara terlebih dahulu.")
    else:
        audio_bytes = audio_file.getvalue()
        mime_type = getattr(audio_file, "type", None) or "audio/wav"

        ok, message = save_message(
            room=room,
            sender=sender,
            note=note,
            audio_bytes=audio_bytes,
            mime_type=mime_type
        )

        if ok:
            st.success(message)
            st.rerun()
        else:
            st.error(message)


col_a, col_b = st.columns([1, 1])

with col_a:
    if st.button("Refresh Sekarang", use_container_width=True):
        st.rerun()

with col_b:
    st.write(f"Room aktif: `{room}`")

st.divider()
st.subheader("Pesan Terbaru")

messages = get_messages(room, limit=limit)

if not messages:
    st.write("Belum ada pesan di channel ini.")
else:
    for msg in messages:
        with st.container(border=True):
            top_left, top_right = st.columns([4, 1])

            with top_left:
                st.markdown(f"**{msg['sender']}**")
                st.caption(msg["created_at"])

            with top_right:
                delete_clicked = st.button(
                    "Hapus",
                    key=f"delete_{msg['id']}",
                    use_container_width=True
                )

            if delete_clicked:
                delete_message(msg["id"], room)
                st.rerun()

            if msg["note"]:
                st.write(msg["note"])

            st.audio(
                bytes(msg["audio_blob"]),
                format=msg["mime_type"] or "audio/wav"
            )

st.caption(
    "Catatan: pada Streamlit Community Cloud, penyimpanan lokal bisa reset saat aplikasi restart/redeploy. "
    "Untuk produksi permanen, gunakan database/storage eksternal."
)
