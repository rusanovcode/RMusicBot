import os
import json
import base64
import requests
from telegram import Update, InlineQueryResultCachedAudio
from telegram.ext import Application, CommandHandler, InlineQueryHandler, MessageHandler, filters, ContextTypes
from uuid import uuid4

# Конфигурация GitHub для автосохранения
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()
REPO_RAW = os.environ.get("GITHUB_REPO", "").strip("/")
GITHUB_REPO = f"/{REPO_RAW}" if REPO_RAW else ""
FILE_PATH = "playlist.json"

def load_tracks():
    url = f"https://github.com{GITHUB_REPO}/contents/{FILE_PATH}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
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

# Загружаем треки при старте
try:
    TRACKS, FILE_SHA = load_tracks()
except:
    TRACKS, FILE_SHA = [], None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎵 *RMusicBot готов к работе!*\n\n"
        "Бот работает в **Инлайн-режиме**.\n"
        "Чтобы поделиться музыкой, перейдите в любой чат, введите `@имя_вашего_бота` и выберите нужный трек из списка.",
        parse_mode="Markdown"
    )

# АВТОДОБАВЛЕНИЕ: Бот слушает новые аудиофайлы (в личке и в группе)
async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global TRACKS, FILE_SHA

    audio = update.message.audio
    # Сохраняем уникальный внутренний ID файла в Telegram
    file_id = audio.file_id  

    title = audio.title if audio.title else audio.file_name
    performer = audio.performer if audio.performer else "Неизвестный исполнитель"
    full_title = f"{performer} — {title}"

    # Синхронизируем базу перед записью нового трека
    updated_tracks, updated_sha = load_tracks()
    TRACKS = updated_tracks if updated_tracks else []
    FILE_SHA = updated_sha
    
    # Очищаем дефолтную заглушку, если она была в базе
    if len(TRACKS) == 1 and "Плейлист пуст" in TRACKS[0].get("title", ""):
        TRACKS = []
        
    TRACKS.append({"title": full_title, "file_id": file_id})
    save_tracks(TRACKS, FILE_SHA)
    
    await update.message.reply_text(f"✅ Трек успешно добавлен в плеер:\n*{full_title}*", parse_mode="Markdown")

# ИНЛАЙН РЕЖИМ: Поиск и отправка треков с кнопкой PLAY
async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global TRACKS, FILE_SHA
    query = update.inline_query.query.lower()
    
    # Пытаемся получить свежий список треков из GitHub
    updated_tracks, _ = load_tracks()
    if updated_tracks:
        TRACKS = updated_tracks

    results = []
    for track in TRACKS:
        if "file_id" not in track:
            continue
            
        # Фильтруем треки, если пользователь начал вводить название
        if not query or query in track['title'].lower():
            results.append(
                InlineQueryResultCachedAudio(
                    id=str(uuid4()),
                    audio_file_id=track['file_id'],  # Telegram сам превратит это в плеер с Play/Pause!
                    caption=f"🎵 Отправлено через @{context.bot.username}"
                )
            )
            
    await update.inline_query.answer(results[:50], cache_time=1)

def main():
    token = os.environ.get("BOT_TOKEN")
    app = Application.builder().token(token).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(InlineQueryHandler(inline_query))
    app.add_handler(MessageHandler(filters.AUDIO, handle_audio))
    
    port = int(os.environ.get("PORT", 8443))
    app.run_webhook(
        listen="0.0.0.0", 
        port=port, 
        url_path=token, 
        webhook_url=f"https://{os.environ.get('RENDER_EXTERNAL_HOSTNAME')}/{token}"
    )

if __name__ == '__main__':
    main()
