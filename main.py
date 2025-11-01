import logging
import os
import time
import asyncio
import sqlite3
import secrets
import string
from threading import Lock

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters,
    CallbackContext, CallbackQueryHandler
)

# ================== CONFIG ==================
BOT_TOKEN = "8207745136:AAEJ0MJNTS40yxBvYLmLbTRzjtO5QGJ7JkA"
ADMIN_USER_ID = 8275649347

MAIN_CHANNEL_ID = -1002628211220
MAIN_CHANNEL_LINK = "https://t.me/+YEObPfKXsK1hNjU9"
CHAT_GC = "@hazyGC"
BACKUP1 = "@pytimebruh"
BACKUP2 = "@hazypy"

BOT_USERNAME = "HazyFileRoBot"

# ================== LOGGING ==================
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ================== DATABASE ==================
db_lock = Lock()

def init_db():
    with db_lock:
        if os.path.exists('file_links.db'):
            try:
                with sqlite3.connect('file_links.db') as conn:
                    cursor = conn.execute("PRAGMA table_info(file_links)")
                    columns = [row[1] for row in cursor.fetchall()]
                    if set(columns) != {'file_id', 'file_type', 'start_param', 'upload_time'}:
                        os.remove('file_links.db')
                        logger.info("🔄 Recreating DB due to schema mismatch")
            except Exception as e:
                logger.error(f"DB validation error: {e}")
                if os.path.exists('file_links.db'):
                    os.remove('file_links.db')

        with sqlite3.connect('file_links.db') as conn:
            conn.execute('''CREATE TABLE IF NOT EXISTS file_links
                         (file_id TEXT PRIMARY KEY,
                          file_type TEXT,
                          start_param TEXT UNIQUE,
                          upload_time REAL)''')
            conn.execute('''CREATE TABLE IF NOT EXISTS users
                         (user_id INTEGER PRIMARY KEY,
                          banned INTEGER DEFAULT 0)''')
        logger.info("✅ Database ready")

def save_user(user_id, banned=0):
    with db_lock:
        with sqlite3.connect('file_links.db') as conn:
            conn.execute("INSERT OR IGNORE INTO users (user_id, banned) VALUES (?, ?)", (user_id, banned))

def is_user_banned(user_id):
    with db_lock:
        with sqlite3.connect('file_links.db') as conn:
            row = conn.execute("SELECT banned FROM users WHERE user_id = ?", (user_id,)).fetchone()
            return bool(row and row[0] == 1)

def generate_start_param():
    return ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(12))

def save_file_link(file_id, file_type, start_param):
    now = time.time()
    with db_lock:
        with sqlite3.connect('file_links.db') as conn:
            conn.execute(
                "INSERT OR REPLACE INTO file_links (file_id, file_type, start_param, upload_time) VALUES (?, ?, ?, ?)",
                (file_id, file_type, start_param, now)
            )

def get_file_info(start_param):
    now = time.time()
    expiry = 300 * 3600  # 300 hours in seconds
    with db_lock:
        with sqlite3.connect('file_links.db') as conn:
            row = conn.execute(
                "SELECT file_id, file_type, upload_time FROM file_links WHERE start_param = ?", (start_param,)
            ).fetchone()
            if row:
                file_id, file_type, upload_time = row
                if now - upload_time > expiry:
                    conn.execute("DELETE FROM file_links WHERE start_param = ?", (start_param,))
                    return None
                return (file_id, file_type)
            return None

def get_all_users(include_banned=False):
    with db_lock:
        with sqlite3.connect('file_links.db') as conn:
            if include_banned:
                return [row[0] for row in conn.execute("SELECT user_id FROM users").fetchall()]
            else:
                return [row[0] for row in conn.execute("SELECT user_id FROM users WHERE banned = 0").fetchall()]

def is_admin(user_id):
    return user_id == ADMIN_USER_ID

# ================== SMART CHANNEL CHECK ==================
async def get_unjoined_channels(user_id: int, context: CallbackContext):
    channels = [
        (MAIN_CHANNEL_ID, "🔒 Main Channel", MAIN_CHANNEL_LINK),
        (CHAT_GC, "👥 Chat GC", "https://t.me/hazyGC"),
        (BACKUP1, "📡 Backup 1", "https://t.me/pytimebruh"),
        (BACKUP2, "📡 Backup 2", "https://t.me/hazypy"),
    ]
    unjoined = []
    for ch_id, name, link in channels:
        try:
            member = await context.bot.get_chat_member(ch_id, user_id)
            if member.status in ('left', 'kicked', 'banned'):
                unjoined.append((name, link))
        except Exception:
            unjoined.append((name, link))
    return unjoined

# ================== HANDLERS ==================
async def start(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if is_user_banned(user_id):
        await update.message.reply_text("❌ You are banned from using this bot.")
        return
    save_user(user_id)

    if not context.args:
        if is_admin(user_id):
            await update.message.reply_text(
                "👑 *Admin Panel*\n\n📤 Send any file to generate a secure shareable link.",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                "🔐 *Restricted Access*\n\n"
                "This bot delivers files via admin-generated links only.\n"
                "You cannot use it freely.",
                parse_mode='Markdown'
            )
        return

    start_param = context.args[0]
    file_info = get_file_info(start_param)
    if not file_info:
        await update.message.reply_text("❌ Invalid or expired link.")
        return

    unjoined = await get_unjoined_channels(user_id, context)
    if unjoined:
        keyboard = [[InlineKeyboardButton(name, url=link)] for name, link in unjoined]
        keyboard.append([InlineKeyboardButton("✅ Verify Access", callback_data=f"verify_{start_param}")])
        await update.message.reply_text(
            "🔐 *Join the following to access this file:*",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return

    file_id, file_type = file_info
    send_method = {
        'photo': update.message.reply_photo,
        'video': update.message.reply_video,
        'document': update.message.reply_document,
        'audio': update.message.reply_audio,
        'voice': update.message.reply_voice,
    }.get(file_type, update.message.reply_document)

    try:
        await send_method(file_id)
    except Exception as e:
        logger.error(f"File delivery error: {e}")
        await update.message.reply_text("❌ File unavailable.")

async def handle_verification(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if is_user_banned(user_id):
        await query.message.edit_text("❌ You are banned.")
        return

    start_param = query.data.split('_', 1)[1]
    file_info = get_file_info(start_param)
    if not file_info:
        await query.edit_message_text("❌ Link expired or invalid.")
        return

    unjoined = await get_unjoined_channels(user_id, context)
    if unjoined:
        keyboard = [[InlineKeyboardButton(name, url=link)] for name, link in unjoined]
        keyboard.append([InlineKeyboardButton("🔄 Retry", callback_data=f"verify_{start_param}")])
        await query.edit_message_text(
            "❌ *Not all channels joined.*\nJoin missing ones and retry:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return

    file_id, file_type = file_info
    send_method = {
        'photo': context.bot.send_photo,
        'video': context.bot.send_video,
        'document': context.bot.send_document,
        'audio': context.bot.send_audio,
        'voice': context.bot.send_voice,
    }.get(file_type, context.bot.send_document)

    try:
        await send_method(chat_id=user_id, document=file_id)
        await query.edit_message_text("✅ *File delivered!*", parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Callback send error: {e}")
        await query.edit_message_text("❌ Failed to send file.")

async def handle_file(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        try:
            await update.message.delete()
        except:
            pass
        return

    msg = update.message
    file_id = file_type = None

    if msg.document:
        file_id, file_type = msg.document.file_id, 'document'
    elif msg.photo:
        file_id, file_type = msg.photo[-1].file_id, 'photo'
    elif msg.video:
        file_id, file_type = msg.video.file_id, 'video'
    elif msg.audio:
        file_id, file_type = msg.audio.file_id, 'audio'
    elif msg.voice:
        file_id, file_type = msg.voice.file_id, 'voice'
    else:
        await msg.reply_text("⚠️ Unsupported file type.")
        return

    loading = await msg.reply_text("⏳ Processing...")
    param = generate_start_param()
    save_file_link(file_id, file_type, param)
    link = f"https://t.me/{BOT_USERNAME}?start={param}"

    await loading.edit_text(
        f"✅ *Secure Link Generated!*\n\n"
        f"🔗 `{link}`\n\n"
        f"📤 Share this link with users.",
        parse_mode='Markdown'
    )

# ================== ADMIN COMMANDS ==================
async def broadcast(update: Update, context: CallbackContext):
    if not is_admin(update.effective_user.id):
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("📤 Reply to a message with /broadcast")
        return

    users = get_all_users()
    if not users:
        await update.message.reply_text("📭 No active users.")
        return

    progress = await update.message.reply_text(f"📢 Broadcasting to {len(users)} users...")
    success = failed = 0
    reply = update.message.reply_to_message

    for i, uid in enumerate(users):
        try:
            if reply.text:
                await context.bot.send_message(uid, reply.text)
            elif reply.photo:
                await context.bot.send_photo(uid, reply.photo[-1].file_id, caption=reply.caption)
            elif reply.video:
                await context.bot.send_video(uid, reply.video.file_id, caption=reply.caption)
            elif reply.document:
                await context.bot.send_document(uid, reply.document.file_id, caption=reply.caption)
            elif reply.audio:
                await context.bot.send_audio(uid, reply.audio.file_id, caption=reply.caption)
            elif reply.voice:
                await context.bot.send_voice(uid, reply.voice.file_id, caption=reply.caption)
            success += 1
        except Exception as e:
            failed += 1
            logger.warning(f"Broadcast fail {uid}: {e}")
        if i % 20 == 0:
            await progress.edit_text(f"📢 {i}/{len(users)} • ✅ {success} • ❌ {failed}")
        await asyncio.sleep(0.05)

    await progress.edit_text(f"✅ Done!\n✅ {success} | ❌ {failed}")

async def stats(update: Update, context: CallbackContext):
    if not is_admin(update.effective_user.id):
        return
    with db_lock:
        with sqlite3.connect('file_links.db') as conn:
            files = conn.execute("SELECT COUNT(*) FROM file_links").fetchone()[0]
            users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            banned = conn.execute("SELECT COUNT(*) FROM users WHERE banned = 1").fetchone()[0]
    await update.message.reply_text(
        f"📊 *Stats*\n\n"
        f"👥 Total Users: {users}\n"
        f"🚫 Banned: {banned}\n"
        f"📁 Files: {files}",
        parse_mode='Markdown'
    )

async def ban_user(update: Update, context: CallbackContext):
    if not is_admin(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("UsageId: `/ban <user_id>`", parse_mode='Markdown')
        return
    try:
        uid = int(context.args[0])
        with db_lock:
            with sqlite3.connect('file_links.db') as conn:
                conn.execute("UPDATE users SET banned = 1 WHERE user_id = ?", (uid,))
        await update.message.reply_text(f"🚫 User `{uid}` banned.", parse_mode='Markdown')
    except ValueError:
        await update.message.reply_text("⚠️ Invalid user ID.")

async def unban_user(update: Update, context: CallbackContext):
    if not is_admin(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("UsageId: `/unban <user_id>`", parse_mode='Markdown')
        return
    try:
        uid = int(context.args[0])
        with db_lock:
            with sqlite3.connect('file_links.db') as conn:
                conn.execute("UPDATE users SET banned = 0 WHERE user_id = ?", (uid,))
        await update.message.reply_text(f"✅ User `{uid}` unbanned.", parse_mode='Markdown')
    except ValueError:
        await update.message.reply_text("⚠️ Invalid user ID.")

async def list_banned(update: Update, context: CallbackContext):
    if not is_admin(update.effective_user.id):
        return
    with db_lock:
        with sqlite3.connect('file_links.db') as conn:
            rows = conn.execute("SELECT user_id FROM users WHERE banned = 1").fetchall()
    if not rows:
        await update.message.reply_text("✅ No banned users.")
    else:
        banned_list = "\n".join([str(r[0]) for r in rows])
        await update.message.reply_text(f"🚫 Banned Users:\n```\n{banned_list}\n```", parse_mode='Markdown')

async def getid(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    await update.message.reply_text(f"🔖 Your ID: `{uid}`", parse_mode='Markdown')

# ================== BLOCK NON-LINK USERS ==================
async def block_non_admin(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if is_user_banned(user_id):
        await update.message.reply_text("❌ You are banned.")
        return
    if not is_admin(user_id):
        await update.message.reply_text(
            "🤖 This bot only works with admin-generated links.\n"
            "You cannot use it directly.",
            parse_mode='Markdown'
        )

# ================== HEALTH CHECK FOR RENDER ==================
from flask import Flask
import threading

app_web = Flask(__name__)

@app_web.route('/health')
def health():
    return {'status': 'alive', 'bot': BOT_USERNAME}, 200

def run_web():
    port = int(os.environ.get('PORT', 10000))
    app_web.run(host='0.0.0.0', port=port)

# Start health server in background
threading.Thread(target=run_web, daemon=True).start()

# ================== MAIN ==================
def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    # Core handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("ban", ban_user))
    app.add_handler(CommandHandler("unban", unban_user))
    app.add_handler(CommandHandler("list_banned", list_banned))
    app.add_handler(CommandHandler("getid", getid))
    app.add_handler(CallbackQueryHandler(handle_verification, pattern=r"^verify_"))
    app.add_handler(MessageHandler(
        filters.Document.ALL | filters.PHOTO | filters.VIDEO | filters.AUDIO | filters.VOICE,
        handle_file
    ))

    # Block all other messages
    app.add_handler(MessageHandler(filters.ALL, block_non_admin))

    logger.info("🚀 Bot + Health Server started")
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
