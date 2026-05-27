import os
import json
import base64
import requests
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, InlineQueryHandler, MessageHandler, filters, ContextTypes
from uuid import uuid4

# Конфигурация GitHub для автосохранения
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()
REPO_RAW = os.environ.get("GITHUB_REPO", "").strip("/")
GITHUB_REPO = f"/{REPO_RAW}" if REPO_RAW else ""
FILE_PATH = "playlist.json"

def load_tracks():
    # Добавляем случайный параметр против кэширования со стороны серверов GitHub
    url = f"https://github.com{GITHUB_REPO}/contents/{FILE_PATH}?t={int(time.time())}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Cache-Control": "no-cache"
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
        res = requests.put(url, headers=headers, json=data)
        return res.status_code in [200, 201]
    except Exception as e:
        print(f"Ошибка сохранения плейлиста: {e}")
    return False

# Загружаем треки при старте
try:
    TRACKS, FILE_SHA = load_tracks()
except:
    TRACKS, FILE_SHA = [], None

if not TRACKS:
    TRACKS = [{"title": "Плейлист пуст. Отправьте мне mp3 файлы в группу или личку!", "file_id": ""}]

def get_player_data(idx: int):
    global TRACKS
    if not TRACKS:
        TRACKS = [{"title": "Плейлист пуст. Отправьте мне mp3 файлы в группу или личку!", "file_id": ""}]
        
    idx = idx % len(TRACKS)
    track = TRACKS[idx]
    
    text = f"🎵 *МУЗЫКАЛЬНЫЙ ПЛЕЕР*\n\n📌 Название: {track['title']}\n\n_Всего песен в базе: {len(TRACKS)}_"
    
    keyboard = [
        [
            InlineKeyboardButton("◀️ Назад", callback_data=f"play_{(idx - 1) % len(TRACKS)}"),
            InlineKeyboardButton("▶️ Вперед", callback_data=f"play_{(idx + 1) % len(TRACKS)}")
        ],
        [
            InlineKeyboardButton("🎵 Воспроизвести этот трек", callback_data=f"send_{idx}")
        ],
        [InlineKeyboardButton("📋 Список песен", callback_data="show_list")]
    ]
    return text, InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text, reply_markup = get_player_data(0)
    await update.message.reply_text(text=text, reply_markup=reply_markup, parse_mode="Markdown")

async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global TRACKS, FILE_SHA
    updated_tracks, updated_sha = load_tracks()
    if updated_tracks:
        TRACKS, FILE_SHA = updated_tracks, updated_sha

    text, reply_markup = get_player_data(0)
    
    results = [
        InlineQueryResultArticle(
            id=str(uuid4()), 
            title="🎵 Открыть музыкальный плеер", 
            input_message_content=InputTextMessageContent(message_text=text, parse_mode="Markdown"), 
            reply_markup=reply_markup
        )
    ]
    await update.inline_query.answer(results, cache_time=0, is_personal=True)

# АВТОДОБАВЛЕНИЕ: Бот слушает новые аудиофайлы
async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global TRACKS, FILE_SHA

    audio = update.message.audio
    if not audio:
        return
        
    file_id = audio.file_id  
    title = audio.title if audio.title else audio.file_name
    performer = audio.performer if audio.performer else "Неизвестный исполнитель"
    full_title = f"{performer} — {title}"

    # Принудительно засыпаем на полсекунды для избежания конфликта параллельных запросов к GitHub
    time.sleep(0.5)
    updated_tracks, updated_sha = load_tracks()
    TRACKS = updated_tracks if updated_tracks else []
    FILE_SHA = updated_sha
    
    if len(TRACKS) == 1 and "Плейлист пуст" in TRACKS[0]["title"]:
        TRACKS = []
        
    TRACKS.append({"title": full_title, "file_id": file_id})
    save_tracks(TRACKS, FILE_SHA)
    
    await update.message.reply_text(f"✅ Трек успешно добавлен в плеер:\n*{full_title}*", parse_mode="Markdown")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    global TRACKS
    updated_tracks, _ = load_tracks()
    if updated_tracks:
        TRACKS = updated_tracks

    if query.data.startswith("play_"):
        idx = int(query.data.split("_")[1])
        text, reply_markup = get_player_data(idx)
        await query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode="Markdown")
        
    elif query.data.startswith("send_"):
        idx = int(query.data.split("_")[1])
        if idx < len(TRACKS) and "file_id" in TRACKS[idx] and TRACKS[idx]["file_id"]:
            # ЖЕСТКОЕ ИСПРАВЛЕНИЕ: Отправка аудио работает как для обычных чатов, так и для инлайн-сообщений
            if query.message:
                await context.bot.send_audio(chat_id=query.message.chat_id, audio=TRACKS[idx]["file_id"])
            elif query.inline_message_id:
                # Если вызвано из инлайн режима, отправляем в личку нажавшему пользователю или в чат вызова
                await context.bot.send_audio(chat_id=query.from_user.id, audio=TRACKS[idx]["file_id"])
            
    elif query.data == "show_list":
        list_text = "📋 *Список доступных песен:*\n\n" + "\n".join([f"{i+1}. {t['title']}" for i, t in enumerate(TRACKS)])
        keyboard = [[InlineKeyboardButton("⬅️ Вернуться в плеер", callback_data="play_0")]]
        await query.edit_message_text(text=list_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

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
    app.add_handler(CallbackQueryHandler(button_handler))
    
    # Исправленный фильтр: принимает аудио файлы в личке и любых группах
    app.add_handler(MessageHandler(filters.AUDIO & (~filters.COMMAND), handle_audio))
    
    print("Бот успешно запущен.")
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
