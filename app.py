# import os
# from quart import Quart, render_template, request, jsonify, redirect, url_for, session
# from telethon import TelegramClient, events
# from telethon.errors import SessionPasswordNeededError
# import subprocess
# from functools import wraps
# import asyncio

# app = Quart(__name__)
# app.secret_key = os.getenv("APP_SECRET", "supersecret")

# os.makedirs("sessions", exist_ok=True)
# clients = {}
# WEB_PASSWORD = os.getenv("WEB_PASSWORD", "1234")

# # ===== LOGIN PROTECTION =====
# def login_required(func):
#     @wraps(func)
#     async def wrapper(*args, **kwargs):
#         if not session.get("logged_in"):
#             return redirect(url_for("login_page"))
#         return await func(*args, **kwargs)
#     return wrapper


# # ===== AUTH SYSTEM =====
# @app.route("/", methods=["GET", "POST"])
# async def login_page():
#     if request.method == "POST":
#         form = await request.form
#         password = form.get("password")
#         if password == WEB_PASSWORD:
#             session["logged_in"] = True
#             return redirect(url_for("connect_page"))
#         return await render_template("login.html", error="Wrong password.")
#     return await render_template("login.html")


# @app.route("/logout")
# async def logout():
#     session.pop("logged_in", None)
#     return redirect(url_for("login_page"))


# # ===== CONNECT PAGE =====
# @app.route("/connect")
# @login_required
# async def connect_page():
#     if not session.get("logged_in"):
#         return redirect(url_for("login_page"))
#     return await render_template("connect.html")


# # ===== TELEGRAM CONNECT =====
# @app.route("/api/connect", methods=["POST"])
# @login_required
# async def connect_telegram():
#     form = await request.form
#     api_id = form["api_id"]
#     api_hash = form["api_hash"]
#     phone = form["phone"]
#     session_name = f"sessions/{phone.replace('+', '')}"

#     client = TelegramClient(session_name, api_id, api_hash)
#     await client.connect()

#     # kalau sudah login, langsung pakai
#     if await client.is_user_authorized():
#         clients[phone] = client
#         await setup_auto_round(client)
#         return jsonify({"status": "connected"})

#     await client.send_code_request(phone)
#     clients[phone] = client
#     return jsonify({"status": "otp_required"})


# @app.route("/api/verify", methods=["POST"])
# @login_required
# async def verify_otp():
#     form = await request.form
#     phone = form["phone"]
#     code = form["code"]

#     client = clients.get(phone)
#     if not client:
#         return jsonify({"error": "client not found"})

#     try:
#         await client.sign_in(phone, code)
#         await setup_auto_round(client)
#         return jsonify({"status": "connected"})
#     except SessionPasswordNeededError:
#         return jsonify({"status": "password_required"})


# @app.route("/api/password", methods=["POST"])
# @login_required
# async def send_password():
#     form = await request.form
#     phone = form["phone"]
#     password = form["password"]

#     client = clients.get(phone)
#     if not client:
#         return jsonify({"error": "client not found"})

#     await client.sign_in(password=password)
#     await setup_auto_round(client)
#     return jsonify({"status": "connected"})


# @app.route("/api/send_round", methods=["POST"])
# @login_required
# async def send_round():
#     form = await request.form
#     phone = form["phone"]
#     to = form["to"]
#     video = (await request.files)["video"]

#     client = clients.get(phone)
#     if not client:
#         return jsonify({"error": "client not found"})

#     temp_path = f"temp_{phone}.mp4"
#     await video.save(temp_path)
#     result_path = temp_path.replace(".mp4", "_round.mp4")
#     # Pastikan video menjadi square (1:1)
#     subprocess.run([
#         "ffmpeg", "-y",
#         "-i", temp_path,
#         "-vf", "crop='min(iw,ih)':'min(iw,ih)',scale=640:640,setsar=1:1",
#         "-c:a", "copy",
#         result_path
#     ], check=True)
#     await client.send_file(to, result_path, video_note=True)
#     os.remove(result_path)

#     return jsonify({"status": "round_sent"})


# @app.route("/api/disconnect", methods=["POST"])
# @login_required
# async def disconnect_telegram():
#     form = await request.form
#     phone = form["phone"]

#     client = clients.pop(phone, None)
#     session_path = f"sessions/{phone.replace('+', '')}.session"

#     if client:
#         await client.disconnect()
#     if os.path.exists(session_path):
#         os.remove(session_path)

#     return jsonify({"status": "disconnected"})
    
# @app.route("/api/status")
# @login_required
# async def status():
#     active = []
#     for phone, client in clients.items():
#         try:
#             me = await client.get_me()
#             active.append({"phone": phone, "username": me.username})
#         except Exception:
#             continue
#     return jsonify(active)


# # ===== SETUP AUTO ROUND BOT =====
# async def setup_auto_round(client: TelegramClient):
#     """Jika seseorang kirim video ke akun ini, balas sebagai video note"""
#     @client.on(events.NewMessage(incoming=True))
#     async def handle_video(event):
#         if not event.is_private:
#             return
#         if event.video:
#             try:
#                 video_path = await event.download_media()
#                 output_path = video_path.replace(".mp4", "_round.mp4")
#                 # Pastikan video menjadi square (1:1)
#                 subprocess.run([
#                     "ffmpeg", "-y",
#                     "-i", video_path,
#                     "-vf", "crop='min(iw,ih)':'min(iw,ih)',scale=640:640,setsar=1:1",
#                     "-c:a", "copy",
#                     output_path
#                 ], check=True)
#                 await client.send_file(event.chat_id, output_path, video_note=True)
#                 os.remove(output_path)
#             except Exception as e:
#                 print("Auto-round error:", e)

#     if not client.is_connected():
#         await client.connect()

#     me = await client.get_me()
#     print(f"[Auto-Round] Active for {me.username or me.phone}")
    
#     asyncio.create_task(client.run_until_disconnected())

# # ===== RUN =====
# if __name__ == "__main__":
#     app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
import os
import asyncio
from quart import Quart, render_template, request, jsonify, redirect, url_for, session
from telethon import TelegramClient, events
from telethon.errors import SessionPasswordNeededError
import subprocess
from functools import wraps

app = Quart(__name__)
app.secret_key = os.getenv("APP_SECRET", "supersecret")

os.makedirs("sessions", exist_ok=True)
clients = {}
WEB_PASSWORD = os.getenv("WEB_PASSWORD", "1234")

# ===== LOGIN PROTECTION =====
def login_required(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login_page"))
        return await func(*args, **kwargs)
    return wrapper


# ===== LOGIN PAGE =====
@app.route("/", methods=["GET", "POST"])
async def login_page():
    if request.method == "POST":
        form = await request.form
        password = form.get("password")
        if password == WEB_PASSWORD:
            session["logged_in"] = True
            return redirect(url_for("connect_page"))
        return await render_template("login.html", error="Wrong password.")
    return await render_template("login.html")


@app.route("/logout")
async def logout():
    session.pop("logged_in", None)
    return redirect(url_for("login_page"))


# ===== CONNECT PAGE =====
@app.route("/connect")
@login_required
async def connect_page():
    return await render_template("connect.html")


# ===== TELEGRAM CONNECT =====
@app.route("/api/connect", methods=["POST"])
@login_required
async def connect_telegram():
    form = await request.form
    api_id = form["api_id"]
    api_hash = form["api_hash"]
    phone = form["phone"]
    session_name = f"sessions/{phone.replace('+', '')}"

    client = TelegramClient(session_name, api_id, api_hash)
    await client.connect()

    if await client.is_user_authorized():
        clients[phone] = client
        await setup_auto_round(client)
        return jsonify({"status": "connected"})

    await client.send_code_request(phone)
    clients[phone] = client
    return jsonify({"status": "otp_required"})


@app.route("/api/verify", methods=["POST"])
@login_required
async def verify_otp():
    form = await request.form
    phone = form["phone"]
    code = form["code"]

    client = clients.get(phone)
    if not client:
        return jsonify({"error": "client not found"})

    try:
        await client.sign_in(phone, code)
        await setup_auto_round(client)
        return jsonify({"status": "connected"})
    except SessionPasswordNeededError:
        return jsonify({"status": "password_required"})


@app.route("/api/password", methods=["POST"])
@login_required
async def send_password():
    form = await request.form
    phone = form["phone"]
    password = form["password"]

    client = clients.get(phone)
    if not client:
        return jsonify({"error": "client not found"})

    await client.sign_in(password=password)
    await setup_auto_round(client)
    return jsonify({"status": "connected"})


@app.route("/api/send_round", methods=["POST"])
@login_required
async def send_round():
    form = await request.form
    phone = form["phone"]
    to = form["to"]
    video = (await request.files)["video"]

    client = clients.get(phone)
    if not client:
        return jsonify({"error": "client not found"})

    temp_path = f"temp_{phone}.mp4"
    await video.save(temp_path)
    result_path = temp_path.replace(".mp4", "_round.mp4")

    subprocess.run([
        "ffmpeg", "-y",
        "-i", temp_path,
        "-vf", "crop='min(iw,ih)':'min(iw,ih)',scale=640:640,setsar=1:1",
        "-c:a", "copy",
        result_path
    ], check=True)

    await client.send_file(to, result_path, video_note=True)
    os.remove(result_path)
    os.remove(temp_path)
    return jsonify({"status": "round_sent"})


@app.route("/api/disconnect", methods=["POST"])
@login_required
async def disconnect_telegram():
    form = await request.form
    phone = form["phone"]

    client = clients.pop(phone, None)
    session_path = f"sessions/{phone.replace('+', '')}.session"

    if client:
        await client.disconnect()
    if os.path.exists(session_path):
        os.remove(session_path)

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

# ===== AUTO-ROUND SYSTEM =====
async def setup_auto_round(client: TelegramClient):
    @client.on(events.NewMessage(incoming=True))
    async def handle_video(event):
        if not event.is_private:
            return
        if event.video:
            try:
                video_path = await event.download_media()
                output_path = video_path.replace(".mp4", "_round.mp4")
                subprocess.run([
                    "ffmpeg", "-y",
                    "-i", video_path,
                    "-vf", "crop='min(iw,ih)':'min(iw,ih)',scale=640:640,setsar=1:1",
                    "-c:a", "copy",
                    output_path
                ], check=True)
                await client.send_file(event.chat_id, output_path, video_note=True)
                os.remove(output_path)
                os.remove(video_path)
            except Exception as e:
                print("Auto-round error:", e)

    if not client.is_connected():
        await client.connect()

    me = await client.get_me()
    print(f"[Auto-Round Active] {me.username or me.phone}")

    asyncio.create_task(client.run_until_disconnected())
# ===== RUN SERVER =====
if __name__ == "__main__":
    asyncio.run(app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080))))
