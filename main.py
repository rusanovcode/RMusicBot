import os
import json
import base64
import requests
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import Update, BotCommand, InlineQueryResultCachedAudio
from telegram.ext import Application, CommandHandler, InlineQueryHandler, MessageHandler, filters, ContextTypes
from uuid import uuid4

# Конфигурация GitHub для автосохранения
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()
REPO_RAW = os.environ.get("GITHUB_REPO", "").strip("/")
GITHUB_REPO = f"/{REPO_RAW}" if REPO_RAW else ""
FILE_PATH = "playlist.json"

LOCAL_TRACKS_CACHE = []

def load_tracks():
    global LOCAL_TRACKS_CACHE
    url = f"https://github.com{GITHUB_REPO}/contents/{FILE_PATH}?t={int(time.time())}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Cache-Control": "no-cache, no-store, must-revalidate"
    }
    try:
        res = requests.get(url, headers=headers)
        if res.status_code == 200:
            content = res.json()
            file_content = base64.b64decode(content['content']).decode('utf-8')
            loaded = json.loads(file_content)
            if isinstance(loaded, list):
                LOCAL_TRACKS_CACHE = loaded
            return LOCAL_TRACKS_CACHE, content['sha']
    except Exception as e:
        print(f"Ошибка загрузки плейлиста: {e}")
    return LOCAL_TRACKS_CACHE, None

def save_tracks(tracks, sha=None):
    if not sha:
        _, sha = load_tracks()
        
    url = f"https://github.com{GITHUB_REPO}/contents/{FILE_PATH}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    data = {
        "message": "Update playlist via Telegram Bot",
        "content": base64.b64encode(json.dumps(tracks, ensure_ascii=False, indent=4).encode('utf-8')).decode('utf-8')
    }
    if sha:
        data["sha"] = sha
        
    try:
        res = requests.put(url, headers=headers, json=data)
        if res.status_code in [200, 201]:
            print("База данных успешно синхронизирована с GitHub!")
            return True
        else:
            print(f"GitHub вернул ошибку: {res.status_code} - {res.text}")
    except Exception as e:
        print(f"Критическая ошибка сохранения на GitHub: {e}")
    return False

# Первичная загрузка треков при старте
try:
    load_tracks()
except:
    pass

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎵 *RMusicBot готов к работе!*\n\n"
        "Бот работает в **Инлайн-режиме**.\n"
        "Чтобы слушать музыку, введите в поле ввода любого чата `@имя_вашего_бота`.\n\n"
        "🛠 *Команды для управления (в личке бота):*\n"
        "• Отправьте `.mp3`, чтобы добавить песню.\n"
        "• Напишите `/list`, чтобы увидеть список песен и их номера.\n"
        "• Напишите `/delete НомерПесни` (например, `/delete 3`), чтобы удалить трек из базы.",
        parse_mode="Markdown"
    )

# КВЕРИ-ИНЛАЙН: Вывод нативного плейлиста
async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global LOCAL_TRACKS_CACHE
    
    updated_tracks, _ = load_tracks()
    if updated_tracks:
        LOCAL_TRACKS_CACHE = updated_tracks

    query = update.inline_query.query.lower()
    results = []

    for track in reversed(LOCAL_TRACKS_CACHE):
        if "file_id" not in track or not track["file_id"]:
            continue
            
        if not query or query in track['title'].lower():
            results.append(
                InlineQueryResultCachedAudio(
                    id=str(uuid4()),
                    audio_file_id=track['file_id'],
                    caption=f"🎵 Музыкальный плеер @{context.bot.username}"
                )
            )
            
    await update.inline_query.answer(results[:50], cache_time=0, is_personal=True)

# АВТОДОБАВЛЕНИЕ: Перехват музыки
async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global LOCAL_TRACKS_CACHE
    
    message = update.message if update.message else update.channel_post
    if not message or not message.audio:
        return
        
    audio = message.audio
    file_id = audio.file_id  
    title = audio.title if audio.title else audio.file_name
    performer = audio.performer if audio.performer else "Неизвестный исполнитель"
    full_title = f"{performer} — {title}"

    updated_tracks, updated_sha = load_tracks()
    if updated_tracks:
        LOCAL_TRACKS_CACHE = updated_tracks
    
    if any(t.get('file_id') == file_id for t in LOCAL_TRACKS_CACHE):
        return

    LOCAL_TRACKS_CACHE.append({"title": full_title, "file_id": file_id})
    save_tracks(LOCAL_TRACKS_CACHE, updated_sha)
    
    if update.message:
        await update.message.reply_text(f"✅ Трек успешно добавлен в базу плейлера:\n*{full_title}*", parse_mode="Markdown")

# АДМИН-КОМАНДА: Просмотр списка с индексами
async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global LOCAL_TRACKS_CACHE
    updated_tracks, _ = load_tracks()
    if updated_tracks:
        LOCAL_TRACKS_CACHE = updated_tracks

    if not LOCAL_TRACKS_CACHE:
        await update.message.reply_text("📋 Плейлист пуст.")
        return

    text = "📋 *Список песен в базе (с номерами для удаления):*\n\n"
    for i, t in enumerate(LOCAL_TRACKS_CACHE):
        text += f"`{i+1}`. {t['title']}\n"
    
    await update.message.reply_text(text, parse_mode="Markdown")

# АДМИН-КОМАНДА: Удаление песни по её номеру
async def delete_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global LOCAL_TRACKS_CACHE
    
    if not context.args:
        await update.message.reply_text("⚠️ Укажите номер песни для удаления.\nПример: `/delete 2`", parse_mode="Markdown")
        return

    try:
        idx = int(context.args[0]) - 1
        updated_tracks, updated_sha = load_tracks()
        if updated_tracks:
            LOCAL_TRACKS_CACHE = updated_tracks

        if idx < 0 or idx >= len(LOCAL_TRACKS_CACHE):
            await update.message.reply_text("❌ Песни с таким номером нет в списке. Используйте `/list` чтобы проверить номера.")
            return

        removed = LOCAL_TRACKS_CACHE.pop(idx)
        save_tracks(LOCAL_TRACKS_CACHE, updated_sha)
        
        await update.message.reply_text(f"🗑 *Трек успешно удален из плейлиста:* \n_{removed['title']}_", parse_mode="Markdown")
    except (ValueError, IndexError):
        await update.message.reply_text("⚠️ Номер песни должен быть числом. Пример: `/delete 1`")

# Функция автоматической регистрации меню команд в интерфейсе Telegram
async def set_bot_commands(application: Application):
    commands = [
        BotCommand("start", "Запустить бота и показать инструкцию"),
        BotCommand("list", "Показать весь список песен с номерами"),
        BotCommand("delete", "Удалить песню по её номеру (Пример: /delete 1)")
    ]
    await application.bot.set_my_commands(commands)
    print("Подсказки команд успешно зарегистрированы в Telegram!")

class RenderHealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK")
    def log_message(self, format, *args):
        pass

def start_health_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), RenderHealthHandler)
    server.serve_forever()

def main():
    threading.Thread(target=start_health_server, daemon=True).start()

    token = os.environ.get("BOT_TOKEN")
    app = Application.builder().token(token).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("list", list_command))
    app.add_handler(CommandHandler("delete", delete_command))
    app.add_handler(InlineQueryHandler(inline_query))
    
    app.add_handler(MessageHandler(filters.AUDIO, handle_audio))
    app.add_handler(MessageHandler(filters.UpdateType.CHANNEL_POST & filters.AUDIO, handle_audio))
    
    # Регистрация команд при инициализации бота
    app.post_init = set_bot_commands
    
    print("Бот успешно запущен.")
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
