import hashlib
import os
import re
import secrets
import sqlite3
import time
from io import BytesIO
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

import qrcode
import streamlit as st
import streamlit.components.v1 as components

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

# HANYA SIMPAN 5 PESAN TERBARU PER ROOM
MAX_MESSAGES_PER_ROOM = 5

PUBLIC_ROOMS = {
    "umum": "Room 1 - Umum",
    "lapangan": "Room 2 - Lapangan",
    "tim-1": "Room 3 - Tim 1",
    "tim-2": "Room 4 - Tim 2",
    "darurat": "Room 5 - Darurat",
}

DEFAULT_ROOM = "umum"


def get_admin_password() -> str:
    """
    Password admin:
    1. Streamlit Secrets: ADMIN_PASSWORD
    2. Environment variable: ADMIN_PASSWORD
    3. Default bawaan: admin12345
    """
    try:
        if "ADMIN_PASSWORD" in st.secrets:
            return str(st.secrets["ADMIN_PASSWORD"])
    except Exception:
        pass

    return os.getenv("ADMIN_PASSWORD", "admin12345")


# =========================================================
# UTILITAS DASAR
# =========================================================

def safe_slug(value: str, fallback: str = DEFAULT_ROOM) -> str:
    value = str(value or "").strip().lower()
    value = re.sub(r"[^a-z0-9_-]+", "-", value)
    value = value.strip("-")
    return value[:40] or fallback


def clean_label(value: str, fallback: str) -> str:
    value = str(value or "").strip()
    value = re.sub(r"[<>]", "", value)
    return value[:60] or fallback


def clean_name(value: str, fallback: str = "User") -> str:
    value = str(value or "").strip()
    value = re.sub(r"[<>]", "", value)
    return value[:30] or fallback


def now_jakarta() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")


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

CREATE_SECRET_ROOMS_SQL = """
CREATE TABLE IF NOT EXISTS secret_rooms (
    slug TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT
)
"""

CREATE_AUTO_USERS_SQL = """
CREATE TABLE IF NOT EXISTS auto_users (
    alias TEXT PRIMARY KEY,
    created_at TEXT NOT NULL
)
"""

CREATE_MESSAGES_INDEX_SQL = """
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

    try:
        conn.execute("PRAGMA journal_mode=WAL")
    except sqlite3.OperationalError:
        pass

    try:
        conn.execute("PRAGMA synchronous=NORMAL")
    except sqlite3.OperationalError:
        pass

    return conn


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


def ensure_secret_rooms_schema(conn):
    conn.execute(CREATE_SECRET_ROOMS_SQL)
    columns = get_columns(conn, "secret_rooms")

    if "updated_at" not in columns:
        conn.execute("ALTER TABLE secret_rooms ADD COLUMN updated_at TEXT")

    conn.commit()


def reset_messages_table(conn):
    conn.execute("DROP TABLE IF EXISTS messages")
    conn.execute(CREATE_MESSAGES_SQL)
    conn.execute(CREATE_MESSAGES_INDEX_SQL)
    conn.commit()


def register_secret_room_if_missing(conn, slug: str):
    slug = safe_slug(slug, fallback="")
    if not slug or slug in PUBLIC_ROOMS:
        return

    conn.execute("""
        INSERT OR IGNORE INTO secret_rooms (slug, label, created_at, updated_at)
        VALUES (?, ?, ?, ?)
    """, (
        slug,
        f"Secret Room - {slug}",
        now_jakarta(),
        now_jakarta()
    ))


def normalize_room_for_migration(conn, room_value: str) -> str:
    slug = safe_slug(room_value, fallback=DEFAULT_ROOM)

    if slug in PUBLIC_ROOMS:
        return slug

    register_secret_room_if_missing(conn, slug)
    return slug


def migrate_old_file_schema_to_blob(conn, old_columns: set):
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
                old_room = normalize_room_for_migration(conn, row["room"] or DEFAULT_ROOM)
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
                    old_room,
                    row["sender"] or "User",
                    row["note"] or "",
                    row["mime_type"] or "audio/wav",
                    sqlite3.Binary(audio_bytes),
                    audio_hash,
                    row["created_at"] or now_jakarta()
                ))
        except Exception:
            pass

    conn.execute("DROP TABLE IF EXISTS messages")
    conn.execute("ALTER TABLE messages_new RENAME TO messages")
    conn.execute(CREATE_MESSAGES_INDEX_SQL)
    conn.commit()


def trim_room_messages(conn, room: str):
    room = safe_slug(room)
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


def trim_all_rooms():
    def action():
        with get_conn() as conn:
            room_rows = conn.execute("SELECT DISTINCT room FROM messages").fetchall()

            for row in room_rows:
                trim_room_messages(conn, row["room"])

            conn.commit()

    execute_with_retry(action)


def init_db():
    with get_conn() as conn:
        ensure_secret_rooms_schema(conn)
        conn.execute(CREATE_AUTO_USERS_SQL)
        conn.commit()

        if not table_exists(conn, "messages"):
            conn.execute(CREATE_MESSAGES_SQL)
            conn.execute(CREATE_MESSAGES_INDEX_SQL)
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

        if required.issubset(columns):
            conn.execute(CREATE_MESSAGES_INDEX_SQL)
            conn.commit()
            return

        if "filename" in columns and "audio_blob" not in columns:
            migrate_old_file_schema_to_blob(conn, columns)
            return

        reset_messages_table(conn)


# =========================================================
# SECRET ROOM
# =========================================================

def get_secret_rooms():
    def action():
        with get_conn() as conn:
            ensure_secret_rooms_schema(conn)
            return conn.execute("""
                SELECT
                    sr.slug,
                    sr.label,
                    sr.created_at,
                    sr.updated_at,
                    COALESCE(COUNT(m.id), 0) AS message_count
                FROM secret_rooms sr
                LEFT JOIN messages m ON m.room = sr.slug
                GROUP BY sr.slug, sr.label, sr.created_at, sr.updated_at
                ORDER BY sr.created_at DESC, sr.slug ASC
            """).fetchall()

    return execute_with_retry(action)


def secret_room_exists(slug: str) -> bool:
    slug = safe_slug(slug, fallback="")

    if not slug:
        return False

    def action():
        with get_conn() as conn:
            ensure_secret_rooms_schema(conn)
            row = conn.execute(
                "SELECT slug FROM secret_rooms WHERE slug = ?",
                (slug,)
            ).fetchone()
            return row is not None

    return execute_with_retry(action)


def get_secret_room_label(slug: str) -> str:
    slug = safe_slug(slug)

    def action():
        with get_conn() as conn:
            ensure_secret_rooms_schema(conn)
            row = conn.execute(
                "SELECT label FROM secret_rooms WHERE slug = ?",
                (slug,)
            ).fetchone()
            return row["label"] if row else f"Secret Room - {slug}"

    return execute_with_retry(action)


def create_secret_room(name: str, label: str = ""):
    slug = safe_slug(name, fallback="")

    if not slug:
        return False, "Nama secret room tidak boleh kosong."

    if slug in PUBLIC_ROOMS:
        return False, "Nama tersebut sudah dipakai oleh room publik. Gunakan nama lain."

    display_label = clean_label(label, fallback=f"Secret Room - {slug}")

    def action():
        with get_conn() as conn:
            ensure_secret_rooms_schema(conn)
            existing = conn.execute(
                "SELECT slug FROM secret_rooms WHERE slug = ?",
                (slug,)
            ).fetchone()

            if existing:
                return False, "Secret room sudah ada."

            conn.execute("""
                INSERT INTO secret_rooms (slug, label, created_at, updated_at)
                VALUES (?, ?, ?, ?)
            """, (slug, display_label, now_jakarta(), now_jakarta()))
            conn.commit()

            return True, f"Secret room `{slug}` berhasil dibuat."

    return execute_with_retry(action)


def update_secret_room(old_slug: str, new_slug: str, new_label: str, move_messages: bool = True):
    old_slug = safe_slug(old_slug, fallback="")
    new_slug = safe_slug(new_slug, fallback="")
    new_label = clean_label(new_label, fallback=f"Secret Room - {new_slug}")

    if not old_slug:
        return False, "Secret room lama tidak valid."

    if not new_slug:
        return False, "Kode secret room baru tidak boleh kosong."

    if old_slug in PUBLIC_ROOMS or new_slug in PUBLIC_ROOMS:
        return False, "Kode secret room tidak boleh sama dengan room publik."

    def action():
        with get_conn() as conn:
            ensure_secret_rooms_schema(conn)

            existing_old = conn.execute(
                "SELECT slug FROM secret_rooms WHERE slug = ?",
                (old_slug,)
            ).fetchone()

            if not existing_old:
                return False, "Secret room tidak ditemukan."

            if new_slug != old_slug:
                existing_new = conn.execute(
                    "SELECT slug FROM secret_rooms WHERE slug = ?",
                    (new_slug,)
                ).fetchone()

                if existing_new:
                    return False, "Kode secret room baru sudah dipakai."

                conn.execute("""
                    UPDATE secret_rooms
                    SET slug = ?, label = ?, updated_at = ?
                    WHERE slug = ?
                """, (new_slug, new_label, now_jakarta(), old_slug))

                if move_messages:
                    conn.execute(
                        "UPDATE messages SET room = ? WHERE room = ?",
                        (new_slug, old_slug)
                    )
            else:
                conn.execute("""
                    UPDATE secret_rooms
                    SET label = ?, updated_at = ?
                    WHERE slug = ?
                """, (new_label, now_jakarta(), old_slug))

            trim_room_messages(conn, new_slug)
            conn.commit()

            return True, f"Secret room `{old_slug}` berhasil diperbarui menjadi `{new_slug}`."

    return execute_with_retry(action)


def delete_secret_room(slug: str, delete_messages: bool = True):
    slug = safe_slug(slug, fallback="")

    if not slug:
        return False, "Secret room tidak valid."

    if slug in PUBLIC_ROOMS:
        return False, "Room publik tidak dapat dihapus dari menu secret room."

    def action():
        with get_conn() as conn:
            ensure_secret_rooms_schema(conn)
            conn.execute("DELETE FROM secret_rooms WHERE slug = ?", (slug,))

            if delete_messages:
                conn.execute("DELETE FROM messages WHERE room = ?", (slug,))

            conn.commit()
            return True, f"Secret room `{slug}` sudah dihapus."

    return execute_with_retry(action)


def is_valid_room(slug: str) -> bool:
    slug = safe_slug(slug, fallback="")
    return slug in PUBLIC_ROOMS or secret_room_exists(slug)


def get_room_label(slug: str) -> str:
    slug = safe_slug(slug)

    if slug in PUBLIC_ROOMS:
        return PUBLIC_ROOMS[slug]

    if secret_room_exists(slug):
        return get_secret_room_label(slug)

    return f"Room tidak ditemukan: {slug}"


# =========================================================
# PESAN AUDIO
# =========================================================

def save_message(room: str, sender: str, note: str, audio_bytes: bytes, mime_type: str):
    room = safe_slug(room)

    if not is_valid_room(room):
        return False, "Room tidak ditemukan. Pastikan nama secret room benar."

    if not audio_bytes:
        return False, "Audio kosong. Silakan rekam ulang."

    audio_hash = hashlib.sha256(audio_bytes).hexdigest()
    created_at = now_jakarta()

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

            # Setelah pesan baru masuk, langsung hapus pesan lama.
            # Yang disimpan hanya 5 pesan terbaru pada room tersebut.
            trim_room_messages(conn, room)

            conn.commit()

    execute_with_retry(action)
    return True, "Pesan suara berhasil dikirim. Pesan lama otomatis dibatasi maksimal 5 pesan."


def get_messages(room: str, limit: int):
    room = safe_slug(room)

    if not is_valid_room(room):
        return []

    def action():
        with get_conn() as conn:
            # Pastikan saat halaman dibuka pun jumlah pesan tetap maksimal 5.
            trim_room_messages(conn, room)
            conn.commit()

            return conn.execute("""
                SELECT id, room, sender, note, mime_type, audio_blob, created_at
                FROM messages
                WHERE room = ?
                ORDER BY id DESC
                LIMIT ?
            """, (room, min(int(limit), MAX_MESSAGES_PER_ROOM))).fetchall()

    try:
        return execute_with_retry(action)
    except sqlite3.OperationalError:
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
    room = safe_slug(room)

    def action():
        with get_conn() as conn:
            conn.execute(
                "DELETE FROM messages WHERE id = ? AND room = ?",
                (message_id, room)
            )
            conn.commit()

    execute_with_retry(action)


def clear_room(room: str):
    room = safe_slug(room)

    def action():
        with get_conn() as conn:
            conn.execute("DELETE FROM messages WHERE room = ?", (room,))
            conn.commit()

    execute_with_retry(action)


def clear_all_rooms():
    def action():
        with get_conn() as conn:
            conn.execute("DELETE FROM messages")
            conn.commit()

    execute_with_retry(action)



# =========================================================
# NAMA PENGGUNA OTOMATIS
# =========================================================

def alias_exists(alias: str) -> bool:
    alias = clean_name(alias, fallback="")

    if not alias:
        return False

    def action():
        with get_conn() as conn:
            conn.execute(CREATE_AUTO_USERS_SQL)

            row_auto = conn.execute(
                "SELECT alias FROM auto_users WHERE alias = ?",
                (alias,)
            ).fetchone()

            if row_auto:
                return True

            row_message = conn.execute(
                "SELECT sender FROM messages WHERE sender = ? LIMIT 1",
                (alias,)
            ).fetchone()

            return row_message is not None

    return execute_with_retry(action)


def create_unique_auto_username() -> str:
    """
    Membuat nama otomatis yang unik.
    Disimpan di SQLite agar tidak sama dengan nama otomatis lain
    dan tidak sama dengan nama yang pernah muncul di pesan.
    """
    def action():
        with get_conn() as conn:
            conn.execute(CREATE_AUTO_USERS_SQL)

            for _ in range(100):
                candidate = f"User-{secrets.token_hex(3).upper()}"

                row_auto = conn.execute(
                    "SELECT alias FROM auto_users WHERE alias = ?",
                    (candidate,)
                ).fetchone()

                row_message = conn.execute(
                    "SELECT sender FROM messages WHERE sender = ? LIMIT 1",
                    (candidate,)
                ).fetchone()

                if row_auto is None and row_message is None:
                    conn.execute(
                        "INSERT INTO auto_users (alias, created_at) VALUES (?, ?)",
                        (candidate, now_jakarta())
                    )
                    conn.commit()
                    return candidate

            # Fallback sangat jarang terjadi, tetapi tetap dibuat aman.
            candidate = f"User-{int(time.time())}-{secrets.token_hex(2).upper()}"
            conn.execute(
                "INSERT OR IGNORE INTO auto_users (alias, created_at) VALUES (?, ?)",
                (candidate, now_jakarta())
            )
            conn.commit()
            return candidate

    return execute_with_retry(action)


def get_sender_name_from_input(raw_name: str) -> str:
    """
    Jika nama dikosongkan, sistem memberi nama otomatis unik.
    Nama otomatis disimpan di session_state agar tidak berubah saat refresh.
    """
    raw_name = str(raw_name or "").strip()

    if raw_name:
        return clean_name(raw_name)

    if "auto_username" not in st.session_state:
        st.session_state["auto_username"] = create_unique_auto_username()

    return st.session_state["auto_username"]



# =========================================================
# URL, QR, ADMIN
# =========================================================

def get_query_room_raw() -> str:
    try:
        value = st.query_params.get("room", DEFAULT_ROOM)
        if isinstance(value, list):
            value = value[0] if value else DEFAULT_ROOM
        return safe_slug(value)
    except Exception:
        return DEFAULT_ROOM


def set_query_room(room: str):
    room = safe_slug(room)
    try:
        if st.query_params.get("room") != room:
            st.query_params["room"] = room
    except Exception:
        pass


def make_room_url(room: str) -> str:
    room = safe_slug(room)
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

    components.html(
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


def is_admin_authenticated() -> bool:
    return bool(st.session_state.get("admin_authenticated", False))


def check_admin_password(input_password: str) -> bool:
    return input_password == get_admin_password()


# =========================================================
# APP
# =========================================================

st.set_page_config(
    page_title="PTT Sederhana",
    page_icon="🎙️",
    layout="centered"
)

init_db()
trim_all_rooms()

query_room = get_query_room_raw()
query_is_public = query_room in PUBLIC_ROOMS
query_is_secret = (not query_is_public) and secret_room_exists(query_room)

st.title("🎙️ Push To Talk Sederhana")
st.caption("Rekam suara, kirim, lalu pengguna lain menerima setelah refresh/auto-refresh.")

with st.sidebar:
    st.header("Pengaturan")

    sender_input = st.text_input(
        "Nama pengguna",
        value="",
        placeholder="Kosongkan untuk nama otomatis unik"
    )

    sender = get_sender_name_from_input(sender_input)

    if not sender_input.strip():
        st.caption(f"Nama otomatis Anda: `{sender}`")

    st.divider()
    st.subheader("Masuk Room")

    default_mode_index = 1 if query_is_secret else 0
    room_mode = st.radio(
        "Jenis room",
        options=["Room Publik", "Secret Room"],
        index=default_mode_index,
        horizontal=False
    )

    room = DEFAULT_ROOM
    active_room_valid = True

    if room_mode == "Room Publik":
        public_keys = list(PUBLIC_ROOMS.keys())
        public_default = query_room if query_room in PUBLIC_ROOMS else DEFAULT_ROOM
        public_index = public_keys.index(public_default)

        selected_public_room = st.selectbox(
            "Pilih room publik",
            options=public_keys,
            index=public_index,
            format_func=lambda key: PUBLIC_ROOMS[key]
        )

        room = selected_public_room
        active_room_valid = True
        set_query_room(room)

    else:
        default_secret_value = query_room if query_room not in PUBLIC_ROOMS else ""
        secret_input = st.text_input(
            "Masukkan nama/kode secret room",
            value=default_secret_value,
            placeholder="Contoh: operasi-alpha"
        )

        room = safe_slug(secret_input, fallback="")
        active_room_valid = bool(room) and secret_room_exists(room)

        if room:
            set_query_room(room)

        if not room:
            st.info("Masukkan nama secret room yang diberikan admin.")
        elif not active_room_valid:
            st.error("Secret room tidak ditemukan. Periksa kembali nama/kode room.")
        else:
            st.success("Secret room ditemukan.")

    st.divider()

    # Pesan tetap maksimal 5. Slider hanya untuk tampilan, dibatasi 5.
    limit = st.slider(
        "Jumlah pesan tampil",
        min_value=1,
        max_value=MAX_MESSAGES_PER_ROOM,
        value=MAX_MESSAGES_PER_ROOM,
        step=1,
        help="Sistem hanya menyimpan maksimal 5 pesan terbaru per room."
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

    st.subheader("Room Publik")
    for key, label in PUBLIC_ROOMS.items():
        st.write(f"- `{key}` — {label}")

    st.divider()

    if active_room_valid:
        room_url = make_room_url(room)

        st.subheader("Bagikan Room Aktif")
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
    else:
        st.subheader("Bagikan Room Aktif")
        st.caption("Link dan QR muncul setelah room valid.")

    st.divider()

    with st.expander("Admin room"):
        if not is_admin_authenticated():
            admin_password_input = st.text_input(
                "Password admin",
                type="password",
                placeholder="Masukkan password admin"
            )

            if st.button("Masuk Admin", use_container_width=True):
                if check_admin_password(admin_password_input):
                    st.session_state["admin_authenticated"] = True
                    st.success("Admin berhasil masuk.")
                    st.rerun()
                else:
                    st.error("Password admin salah.")
        else:
            st.success("Mode admin aktif.")

            if st.button("Keluar Admin", use_container_width=True):
                st.session_state["admin_authenticated"] = False
                st.rerun()

            st.divider()
            st.subheader("Buat Secret Room")

            with st.form("create_secret_room_form", clear_on_submit=True):
                new_secret_name = st.text_input(
                    "Nama/kode secret room baru",
                    placeholder="Contoh: operasi-alpha"
                )

                new_secret_label = st.text_input(
                    "Nama tampilan opsional",
                    placeholder="Contoh: Operasi Alpha"
                )

                create_submitted = st.form_submit_button(
                    "Buat Secret Room",
                    type="primary",
                    use_container_width=True
                )

            if create_submitted:
                ok, msg = create_secret_room(new_secret_name, new_secret_label)
                if ok:
                    st.success(msg)
                    st.info("Bagikan kode secret room kepada user yang boleh masuk.")
                    st.rerun()
                else:
                    st.error(msg)

            st.divider()
            st.subheader("List Semua Secret Room")

            secret_rooms = get_secret_rooms()

            if not secret_rooms:
                st.caption("Belum ada secret room.")
            else:
                for sr in secret_rooms:
                    sr_slug = sr["slug"]
                    sr_url = make_room_url(sr_slug)
                    message_count = int(sr["message_count"] or 0)

                    with st.container(border=True):
                        st.markdown(f"**{sr['label']}**")
                        st.write(f"Kode: `{sr_slug}`")
                        st.caption(f"Dibuat: {sr['created_at']}")
                        if sr["updated_at"]:
                            st.caption(f"Update terakhir: {sr['updated_at']}")
                        st.caption(f"Jumlah pesan tersimpan: {message_count}/{MAX_MESSAGES_PER_ROOM}")

                        st.code(sr_url, language="text")

                        with st.form(f"edit_secret_room_{sr_slug}"):
                            edited_slug = st.text_input(
                                "Ubah kode secret room",
                                value=sr_slug,
                                key=f"edit_slug_{sr_slug}"
                            )

                            edited_label = st.text_input(
                                "Ubah nama tampilan",
                                value=sr["label"],
                                key=f"edit_label_{sr_slug}"
                            )

                            move_messages = st.checkbox(
                                "Pindahkan pesan lama ke kode room baru",
                                value=True,
                                key=f"move_messages_{sr_slug}"
                            )

                            edit_submitted = st.form_submit_button(
                                "Simpan Perubahan",
                                use_container_width=True
                            )

                        if edit_submitted:
                            ok, msg = update_secret_room(
                                old_slug=sr_slug,
                                new_slug=edited_slug,
                                new_label=edited_label,
                                move_messages=move_messages
                            )

                            if ok:
                                st.success(msg)
                                st.rerun()
                            else:
                                st.error(msg)

                        delete_sr_messages = st.checkbox(
                            "Hapus juga semua pesan room ini",
                            value=True,
                            key=f"delete_secret_messages_{sr_slug}"
                        )

                        if st.button(
                            "Hapus Secret Room",
                            key=f"delete_secret_room_{sr_slug}",
                            type="secondary",
                            use_container_width=True
                        ):
                            ok, msg = delete_secret_room(
                                sr_slug,
                                delete_messages=delete_sr_messages
                            )
                            if ok:
                                st.success(msg)
                                st.rerun()
                            else:
                                st.error(msg)

            st.divider()
            st.subheader("Hapus Pesan")

            if active_room_valid:
                if st.button("Hapus Semua Pesan Room Aktif", type="secondary", use_container_width=True):
                    clear_room(room)
                    st.success(f"Semua pesan pada {get_room_label(room)} sudah dihapus.")
                    st.rerun()
            else:
                st.caption("Pilih room yang valid untuk menghapus pesan room aktif.")

            confirm_all = st.checkbox("Saya paham: hapus semua pesan di semua room")
            if confirm_all:
                if st.button("Hapus Semua Pesan Semua Room", type="secondary", use_container_width=True):
                    clear_all_rooms()
                    st.success("Semua pesan di semua room sudah dihapus.")
                    st.rerun()


if active_room_valid and auto_refresh and st_autorefresh is not None:
    st_autorefresh(
        interval=refresh_seconds * 1000,
        key=f"ptt_refresh_{room}"
    )
elif auto_refresh and st_autorefresh is None:
    st.warning(
        "Auto-refresh belum aktif karena package streamlit-autorefresh belum terpasang. "
        "Pastikan requirements.txt sudah di-update."
    )

if not active_room_valid:
    st.subheader("Secret Room")
    st.error("Room belum valid. Masukkan nama/kode secret room yang benar di sidebar.")
    st.stop()

st.subheader(get_room_label(room))
st.caption(f"Kode room: `{room}`")

if room in PUBLIC_ROOMS:
    st.info("Anda sedang berada di room publik.")
else:
    st.success("Anda sedang berada di secret room. Hanya user yang tahu kode room ini yang dapat masuk.")

st.info(
    f"Tekan tombol rekam, bicara, berhenti rekam, lalu klik **Kirim Pesan Suara**. "
    f"Sistem hanya menyimpan **{MAX_MESSAGES_PER_ROOM} pesan terbaru** per room. "
    f"Pesan paling lama akan otomatis terhapus saat ada pesan baru."
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
    st.caption(f"Nama otomatis Anda: `{sender}`")

st.divider()
st.subheader(f"Pesan Terbaru Maksimal {MAX_MESSAGES_PER_ROOM}")

messages = get_messages(room, limit=limit)

if not messages:
    st.write("Belum ada pesan di room ini.")
else:
    for msg in messages:
        with st.container(border=True):
            top_left, top_right = st.columns([4, 1])

            with top_left:
                st.markdown(f"**{msg['sender']}**")
                st.caption(msg["created_at"])

            with top_right:
                if is_admin_authenticated():
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
    "Catatan: Room umum dapat dilihat dan didengar pesannya oleh siapapun yang masuk, jika membutuhkan link private silahkan hubungi admin. "
    "Created by : Galuh Adi Insani"
)
