import os
import asyncio
import subprocess
import asyncpg
from quart import Quart, render_template, request, jsonify, redirect, url_for, session
from telethon import TelegramClient, events
from telethon.errors import SessionPasswordNeededError
from telethon.sessions.memory import MemorySession
from telethon.sessions import StringSession
from functools import wraps
import imageio_ffmpeg as ffmpeg

app = Quart(__name__)
app.secret_key = os.getenv("APP_SECRET", "supersecret")

WEB_PASSWORD = os.getenv("WEB_PASSWORD", "1234")
DATABASE_URL = os.getenv("DATABASE_URL")
PING_INTERVAL = int(os.getenv("PING_INTERVAL", 300))  # 5 menit

clients = {}
db_pool = None

# ===== AUTH =====
def login_required(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login_page"))
        return await func(*args, **kwargs)
    return wrapper


# ===== ROUTES =====
@app.route("/", methods=["GET", "POST"])
async def login_page():
    if request.method == "POST":
        form = await request.form
        if form.get("password") == WEB_PASSWORD:
            session["logged_in"] = True
            return redirect(url_for("connect_page"))
        return await render_template("login.html", error="Wrong password")
    return await render_template("login.html")


@app.route("/logout")
async def logout():
    session.pop("logged_in", None)
    return redirect(url_for("login_page"))


@app.route("/connect")
@login_required
async def connect_page():
    return await render_template("connect.html")


# ===== TELEGRAM CONNECT =====
@app.route("/api/connect", methods=["POST"])
@login_required
async def connect_telegram():
    form = await request.form
    api_id = int(form["api_id"])
    api_hash = form["api_hash"]
    phone = form["phone"]

    session_string = await load_session_from_db(phone)
    if session_string:
        client = TelegramClient(StringSession(session_string), api_id, api_hash)
    else:
        client = TelegramClient(StringSession(), api_id, api_hash)
    # sess = await load_session_from_db(phone)
    # session_obj = MemorySession()
    # if sess:
    #     session_obj._state = session_obj._unpack(sess)

    # client = TelegramClient(session_obj, api_id, api_hash)
    await client.connect()

    if await client.is_user_authorized():
        clients[phone] = client
        session_string = client.session.save()
        await save_session_to_db(phone, session_string)
        await setup_auto_round(client)
        return jsonify({"status": "connected"})

    await client.send_code_request(phone)
    clients[phone] = client
    return jsonify({"status": "otp_required"})


@app.route("/api/verify", methods=["POST"])
@login_required
async def verify_otp():
    form = await request.form
    phone, code = form["phone"], form["code"]
    client = clients.get(phone)
    if not client:
        return jsonify({"error": "client not found"})

    try:
        await client.sign_in(phone, code)
        session_string = client.session.save()
        print(session_string)
        await save_session_to_db(phone, session_string)
        await setup_auto_round(client)
        return jsonify({"status": "connected"})
    except SessionPasswordNeededError:
        return jsonify({"status": "password_required"})


@app.route("/api/password", methods=["POST"])
@login_required
async def send_password():
    form = await request.form
    phone, password = form["phone"], form["password"]
    client = clients.get(phone)
    if not client:
        return jsonify({"error": "client not found"})

    await client.sign_in(password=password)
    session_string = client.session.save()
    print(session_string)
    await save_session_to_db(phone, client)

    await setup_auto_round(client)
    return jsonify({"status": "connected"})


@app.route("/api/send_round", methods=["POST"])
@login_required
async def send_round():
    form = await request.form
    phone, to = form["phone"], form["to"]
    video = (await request.files)["video"]
    client = clients.get(phone)
    if not client:
        return jsonify({"error": "client not found"})

    temp = f"temp_{phone}.mp4"
    await video.save(temp)
    result = temp.replace(".mp4", "_round.mp4")

    cmd = [
        ffmpeg.get_ffmpeg_exe(),  # path ke ffmpeg binari
        "-y", "-i", temp,
        "-vf", "crop='min(iw,ih)':'min(iw,ih)',scale=640:640,setsar=1:1",
        "-c:a", "copy", result
    ]

    subprocess.run(cmd, check=True)

    await client.send_file(to, result, video_note=True)
    os.remove(temp)
    os.remove(result)
    return jsonify({"status": "round_sent"})


@app.route("/api/disconnect", methods=["POST"])
@login_required
async def disconnect_telegram():
    form = await request.form
    phone = form["phone"]
    client = clients.pop(phone, None)
    if client:
        try:
            await client.session.delete()
        except Exception:
            pass
        await client.disconnect()

    return jsonify({"status": "disconnected"})


@app.route("/api/status")
@login_required
async def status():
    active = []
    for phone, client in clients.items():
        try:
            me = await client.get_me()
            active.append({"phone": phone, "username": me.username})
        except Exception:
            continue
    return jsonify(active)


# ===== AUTO VIDEO-NOTE =====
async def setup_auto_round(client):
    """Setup event handler to auto-convert videos to round video notes."""
    @client.on(events.NewMessage(incoming=True))
    async def on_video(event):
        if not event.is_private or not event.video:
            return

        path = await event.download_media()
        out = path.replace(".mp4", "_round.mp4")

        cmd = [
            ffmpeg.get_ffmpeg_exe(),  # path ke ffmpeg binari
            "-y", "-i", path,
            "-vf", "crop='min(iw,ih)':'min(iw,ih)',scale=640:640,setsar=1:1",
            "-c:a", "copy", out
        ]

        subprocess.run(cmd, check=True)

        await client.send_file(event.chat_id, out, video_note=True)
        os.remove(path)
        os.remove(out)

    async def autosave_loop():
        while True:
            scrape = await client.get_me()
            await save_session_to_db(scrape.phone, client)
            await asyncio.sleep(30)

    asyncio.create_task(autosave_loop())

    # if not client.is_connected():
    #     await client.connect()

    me = await client.get_me()
    print(f"[Auto-Round Active] {me.username or me.phone}")
    asyncio.create_task(client.run_until_disconnected())


# ===== SESSION HELPER =====
async def save_session_to_db(phone: str, client):
    """
    Simpan session Telethon ke PostgreSQL.
    client: instance TelegramClient
    """
    if not hasattr(client, "session"):
        print(f"[WARN] Client for {phone} has no session, skip saving.")
        return

    # dapatkan session string
    try:
        if hasattr(client.session, "save"):
            session_str = client.session.save()
        else:
            print(f"[WARN] Session object for {phone} has no save() method, skip saving.")
            return
    except Exception as e:
        print(f"[ERROR] Failed to pack session for {phone}: {e}")
        return

    async with db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO telethon_sessions (phone, session_data, updated_at)
            VALUES ($1, $2, NOW())
            ON CONFLICT (phone)
            DO UPDATE SET session_data = EXCLUDED.session_data, updated_at = NOW();
        """, phone, session_str.encode('utf-8'))  # simpan sebagai BYTEA
    print(f"[DB] Session saved for {phone}")

async def load_session_from_db(phone):
    """Ambil session Telethon dari PostgreSQL."""
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT session_data FROM telethon_sessions WHERE phone=$1", phone)
        return row["session_data"].decode() if row else None

async def delete_session_from_db(phone):
    """Hapus session Telethon dari PostgreSQL."""
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM telethon_sessions WHERE phone=$1", phone)
    print(f"[DB] Session deleted for {phone}")

# ===== AUTO PING =====
async def auto_ping():
    """Supaya Railway container tetap hidup"""
    while True:
        try:
            url = os.getenv("APP_URL")  # set APP_URL di Railway ke URL aplikasi
            if url:
                async with aiohttp.ClientSession() as session_http:
                    async with session_http.get(url) as resp:
                        print(f"[Ping] Status: {resp.status}")
        except Exception as e:
            print(f"[Ping Error] {e}")
        await asyncio.sleep(PING_INTERVAL)

# ===== STARTUP DB =====
@app.before_serving
async def startup():
    global db_pool
    db_pool = await asyncpg.create_pool(DATABASE_URL)
    async with db_pool.acquire() as conn:
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS telethon_sessions (
            phone TEXT PRIMARY KEY,
            session_data BYTEA,
            updated_at TIMESTAMP DEFAULT NOW()
        );
        """)
    print("[DB] Connected and table ready")
    asyncio.create_task(auto_ping())

if __name__ == "__main__":
    asyncio.run(app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080))))
