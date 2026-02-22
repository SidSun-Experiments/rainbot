
import logging
import os
import asyncio
import json
import subprocess
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, CallbackQueryHandler, filters

# Configuration
TOKEN = os.environ.get("TELEGRAM_TOKEN")
ALLOWED_USER_IDS = os.environ.get("ALLOWED_USER_IDS", "")
# Snap mpv can't write to /tmp easily, use home dir
MPV_SOCKET = "/home/sids/rainbot_mpv_socket"
YTDLP_PATH = "/home/sids/stacks/rainbot/yt-dlp"
DOWNLOAD_DIR = "downloads"

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.WARNING
)

# Ensure download directory exists
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

async def check_allowed(update: Update):
    if not ALLOWED_USER_IDS:
        return True # Allow all if not configured

    allowed_ids = [int(x.strip()) for x in ALLOWED_USER_IDS.split(",") if x.strip()]
    user_id = update.effective_user.id
    if user_id not in allowed_ids:
        # Check if callback_query exists (for button clicks)
        if update.callback_query:
            await update.callback_query.answer("🚫 Unauthorized", show_alert=True)
        else:
            await update.message.reply_text("🚫 You are not authorized to use this bot.")
        return False
    return True

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_allowed(update): return
    await context.bot.send_message(
        chat_id=update.effective_chat.id, 
        text="🌧️ Rainbot Online!\n\nSend me a YouTube link to play audio.\nUse /help to see controls.\nUse /list to see your library."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_allowed(update): return
    help_text = """
🎧 **Rainbot Controls**

/play - Resume playback
/pause - Pause playback
/volup [amount] - Increase volume (default 10)
/voldown [amount] - Decrease volume (default 10)
/list - List downloaded files to play
/update - Update yt-dlp to latest version
/help - Show this help message

Send a **YouTube URL** to download and play.
"""
    await update.message.reply_markdown(help_text)

async def send_mpv_command(command_list):
    """Sends a JSON command to the mpv IPC socket."""
    if not os.path.exists(MPV_SOCKET):
        return False, "MPV is not running."

    try:
        reader, writer = await asyncio.open_unix_connection(path=MPV_SOCKET)
        payload = json.dumps({"command": command_list}) + "\n"
        writer.write(payload.encode())
        await writer.drain()

        # Read response (optional, but good to check)
        data = await reader.readline()
        writer.close()
        await writer.wait_closed()

        return True, data.decode().strip()
    except Exception as e:
        return False, str(e)

async def play_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_allowed(update): return
    success, msg = await send_mpv_command(["set_property", "pause", False])
    if success:
        await update.message.reply_text("▶️ Resumed.")
    else:
        await update.message.reply_text(f"❌ Error: {msg}")

async def pause_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_allowed(update): return
    success, msg = await send_mpv_command(["set_property", "pause", True])
    if success:
        await update.message.reply_text("⏸️ Paused.")
    else:
        await update.message.reply_text(f"❌ Error: {msg}")

async def change_volume(update: Update, context: ContextTypes.DEFAULT_TYPE, amount: int):
    if not await check_allowed(update): return

    # Check if user provided a specific amount
    if context.args:
        try:
            amount = int(context.args[0])
            # If command is voldown, invert user input if they gave a positive number
            if "voldown" in update.message.text and amount > 0:
                amount = -amount
            # If command is volup, ensure positive
            if "volup" in update.message.text:
                amount = abs(amount)
        except ValueError:
            await update.message.reply_text("Usage: /volup [amount] or /voldown [amount]")
            return

    success, msg = await send_mpv_command(["add", "volume", amount])
    if success:
         # Get new volume to show user
        _, vol_resp = await send_mpv_command(["get_property", "volume"])
        try:
            vol_data = json.loads(vol_resp)
            new_vol = vol_data.get("data", "unknown")
        except:
            new_vol = "?"

        direction = "Cw" if amount > 0 else "Qw"
        await update.message.reply_text(f"{direction} Volume: {new_vol}%")
    else:
        await update.message.reply_text(f"❌ Error: {msg}")

async def volup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await change_volume(update, context, 10)

async def voldown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await change_volume(update, context, -10)

async def play_file(filename, reply_func):
    """Refactored logic to play a file using mpv."""
    if not os.path.exists(filename):
         await reply_func("❌ Error: File not found.")
         return

    # Kill existing mpv if running (rudimentary)
    ipc_success, _ = await send_mpv_command(["loadfile", filename, "replace"])

    if ipc_success:
        # Ensure it loops if reusing the instance
        await send_mpv_command(["set_property", "loop-file", "inf"])
        # Ensure it unpauses if it was paused
        await send_mpv_command(["set_property", "pause", False])
    else:
        # Start new MPV instance
        mpv_cmd = [
            "mpv",
            f"--input-ipc-server={MPV_SOCKET}",
            "--no-terminal",
            "--loop=inf",
            filename
        ]

        # We start it as a subprocess but don't wait for it
        subprocess = await asyncio.create_subprocess_exec(
            *mpv_cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

    await reply_func(f"🎶 Playing: {os.path.basename(filename)}")

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_allowed(update): return

    url = update.message.text.strip()
    if "youtube.com" not in url and "youtu.be" not in url:
        await update.message.reply_text("That doesn't look like a YouTube link.")
        return

    await update.message.reply_text("⏳ Downloading audio... please wait.")

    cmd = [
        YTDLP_PATH,
        "-x", "--audio-format", "mp3",
        "-o", f"{DOWNLOAD_DIR}/%(title)s [%(id)s].%(ext)s",
        "--no-playlist",
        "--print", "after_move:filepath", 
        "--no-simulate",
        url
    ]

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        error_msg = stderr.decode().strip()
        short_err = error_msg.split('\n')[-1] if error_msg else "Unknown error"
        await update.message.reply_text(f"❌ Download failed:\n{short_err}")
        return

    lines = stdout.decode().strip().split('\n')
    filename = lines[-1].strip() if lines else ""

    if not os.path.exists(filename):
        # Fallback
        files = [os.path.join(DOWNLOAD_DIR, f) for f in os.listdir(DOWNLOAD_DIR) if f.endswith('.mp3')]
        if not files:
             await update.message.reply_text("❌ Error: Could not locate downloaded file.")
             return
        filename = max(files, key=os.path.getctime)

    await update.message.reply_text(f"✅ Downloaded: {os.path.basename(filename)}")
    await play_file(filename, update.message.reply_text)

async def update_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_allowed(update): return

    current_version = "Unknown"
    if os.path.exists(YTDLP_PATH):
        try:
            curr_ver_cmd = [YTDLP_PATH, "--version"]
            curr_ver_proc = await asyncio.create_subprocess_exec(
                *curr_ver_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            stdout, _ = await curr_ver_proc.communicate()
            if curr_ver_proc.returncode == 0:
                current_version = stdout.decode().strip()
        except Exception:
            pass

    await update.message.reply_text("⏳ Downloading latest yt-dlp...")

    cmd = [
        "curl", "-L",
        "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp_linux",
        "-o", f"{YTDLP_PATH}.tmp"
    ]

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    _, stderr = await process.communicate()

    if process.returncode != 0:
        error_msg = stderr.decode().strip()
        short_err = error_msg.split('\n')[-1] if error_msg else "Unknown error"
        await update.message.reply_text(f"❌ Update failed:\n{short_err}")
        return

    try:
        os.chmod(f"{YTDLP_PATH}.tmp", 0o755)

        # Try getting version of new file
        new_ver_cmd = [f"{YTDLP_PATH}.tmp", "--version"]
        new_ver_proc = await asyncio.create_subprocess_exec(
            *new_ver_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        stdout, _ = await new_ver_proc.communicate()
        new_version = stdout.decode().strip() if new_ver_proc.returncode == 0 else "Unknown"

        if new_version == current_version and current_version != "Unknown":
            os.remove(f"{YTDLP_PATH}.tmp")
            await update.message.reply_text(f"✅ yt-dlp is already up-to-date (version: {current_version})")
        else:
            os.replace(f"{YTDLP_PATH}.tmp", YTDLP_PATH)
            if current_version == "Unknown":
                await update.message.reply_text(f"✅ yt-dlp installed: {new_version}")
            else:
                await update.message.reply_text(f"✅ yt-dlp updated: {current_version} ➡️ {new_version}")

    except Exception as e:
        if os.path.exists(f"{YTDLP_PATH}.tmp"):
            os.remove(f"{YTDLP_PATH}.tmp")
        await update.message.reply_text(f"❌ Error setting up yt-dlp: {e}")

async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_allowed(update): return

    files = [f for f in os.listdir(DOWNLOAD_DIR) if f.endswith('.mp3')]
    if not files:
        await update.message.reply_text("📂 No files found.")
        return

    # Sort by modification time (newest first)
    files.sort(key=lambda x: os.path.getmtime(os.path.join(DOWNLOAD_DIR, x)), reverse=True)

    # Limit to top 20 to avoid large messages
    files = files[:20]

    keyboard = []
    for idx, f_name in enumerate(files):
        # Use index in callback to avoid length limits
        keyboard.append([InlineKeyboardButton(f_name, callback_data=f"play:{idx}")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("📂 **Your Library**:", reply_markup=reply_markup)

async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_allowed(update): return

    query = update.callback_query
    await query.answer()

    data = query.data
    if data.startswith("play:"):
        try:
            idx = int(data.split(":")[1])
            files = [f for f in os.listdir(DOWNLOAD_DIR) if f.endswith('.mp3')]
            files.sort(key=lambda x: os.path.getmtime(os.path.join(DOWNLOAD_DIR, x)), reverse=True)

            if 0 <= idx < len(files):
                filename = os.path.join(DOWNLOAD_DIR, files[idx])
                await play_file(filename, query.edit_message_text)
            else:
                await query.edit_message_text("❌ File not found (list might be outdated).")
        except Exception as e:
            await query.edit_message_text(f"❌ Error: {str(e)}")

if __name__ == '__main__':
    if not TOKEN:
        print("Error: TELEGRAM_TOKEN env var not set.")
        exit(1)

    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('help', help_command))
    application.add_handler(CommandHandler('play', play_command))
    application.add_handler(CommandHandler('pause', pause_command))
    application.add_handler(CommandHandler('volup', volup_command))
    application.add_handler(CommandHandler('voldown', voldown_command))
    application.add_handler(CommandHandler('list', list_command))
    application.add_handler(CommandHandler('update', update_command))
    application.add_handler(CallbackQueryHandler(button_click))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_url))

    print("Bot started...")
    application.run_polling()
