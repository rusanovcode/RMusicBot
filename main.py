import os
import json
import base64
import requests
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import Update, InlineQueryResultCachedAudio
from telegram.ext import Application, CommandHandler, InlineQueryHandler, MessageHandler, filters, ContextTypes
from uuid import uuid4

# Конфигурация GitHub для автосохранения
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()
REPO_RAW = os.environ.get("GITHUB_REPO", "").strip("/")
GITHUB_REPO = f"/{REPO_RAW}" if REPO_RAW else ""
FILE_PATH = "playlist.json"

def load_tracks():
    # Защита от кэширования серверов GitHub через таймштамп
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
            return json.loads(file_content), content['sha']
    except Exception as e:
        print(f"Ошибка загрузки плейлиста: {e}")
    return [], None

def save_tracks(tracks, sha=None):
    url = f"https://github.com{GITHUB_REPO}/contents/{FILE_PATH}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    data = {
        "message": "Update playlist via Telegram Bot",
        "content": base64.b64encode(json.dumps(tracks, ensure_ascii=False, indent=4).encode('utf-8')).decode('utf-8')
    }
    if sha:
        data["sha"] = sha
    try:
        requests.put(url, headers=headers, json=data)
    except Exception as e:
        print(f"Ошибка сохранения плейлиста: {e}")

# Переменные кэша в оперативной памяти бота
TRACKS = []
FILE_SHA = None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎵 *RMusicBot готов к работе!*\n\n"
        "Бот работает в **Инлайн-режиме**.\n"
        "Чтобы запустить плеер и слушать музыку, перейдите в любой чат, введите в поле ввода `@имя_вашего_бота` и выберите трек из появившегося списка.",
        parse_mode="Markdown"
    )

# ИНЛАЙН РЕЖИМ: Отображение настоящих треков со встроенным плеером Telegram
async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global TRACKS, FILE_SHA
    
    # Принудительно обновляем список треков из GitHub при каждом вызове инлайна
    updated_tracks, updated_sha = load_tracks()
    if updated_tracks:
        TRACKS, FILE_SHA = updated_tracks, updated_sha

    query = update.inline_query.query.lower()
    results = []

    # Если база пуста, выводим заглушку
    if not TRACKS:
        return

    for track in TRACKS:
        if "file_id" not in track or not track["file_id"]:
            continue
            
        # Фильтруем треки по поисковому запросу пользователя (если он что-то ввел)
        if not query or query in track['title'].lower():
            results.append(
                InlineQueryResultCachedAudio(
                    id=str(uuid4()),
                    audio_file_id=track['file_id'],  # Telegram сам создаст плеер с кнопками Play/Pause/Листанием!
                    caption=f"🎵 Слушает через @{context.bot.username}"
                )
            )
            
    # cache_time=0 отключает внутреннее кэширование Telegram, чтобы новые песни появлялись мгновенно
    await update.inline_query.answer(results[:50], cache_time=0, is_personal=True)

# АВТОДОБАВЛЕНИЕ: Бот слушает новые аудиофайлы из лички и групп
async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global TRACKS, FILE_SHA

    audio = update.message.audio
    if not audio:
        return
        
    file_id = audio.file_id  
    title = audio.title if audio.title else audio.file_name
    performer = audio.performer if audio.performer else "Неизвестный исполнитель"
    full_title = f"{performer} — {title}"

    # Синхронизируем базу данных перед записью нового трека
    updated_tracks, updated_sha = load_tracks()
    TRACKS = updated_tracks if updated_tracks else []
    FILE_SHA = updated_sha
    
    # Если база состояла из дефолтной заглушки — очищаем её
    if len(TRACKS) == 1 and "Плейлист пуст" in TRACKS[0].get("title", ""):
        TRACKS = []
        
    TRACKS.append({"title": full_title, "file_id": file_id})
    save_tracks(TRACKS, FILE_SHA)
    
    await update.message.reply_text(f"✅ Трек успешно добавлен в базу плеера:\n*{full_title}*", parse_mode="Markdown")

# Легковесный фоновый веб-сервер для закрытия Port Binding на Render
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
    app.add_handler(InlineQueryHandler(inline_query))
    app.add_handler(MessageHandler(filters.AUDIO, handle_audio))
    
    print("Бот успешно запущен в режиме нативного аудио-плеера.")
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
