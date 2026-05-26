import os
import json
import base64
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, InlineQueryHandler, MessageHandler, filters, ContextTypes
from uuid import uuid4

# Конфигурация GitHub для автосохранения
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()
REPO_RAW = os.environ.get("GITHUB_REPO", "").strip("/")
# Формируем правильный путь к репозиторию
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

if not TRACKS:
    TRACKS = [{"title": "Плейлист пуст. Отправьте мне mp3 файлы в вашу группу!", "url": "https://t.me"}]

def get_player_data(idx: int):
    global TRACKS
    if not TRACKS:
        TRACKS = [{"title": "Плейлист пуст. Отправьте мне mp3 файлы в вашу группу!", "url": "https://t.me"}]
        
    idx = idx % len(TRACKS)
    track = TRACKS[idx]
    text = f"🎵 *МУЗЫКАЛЬНЫЙ ПЛЕЕР*\n\n📌 Название: {track['title']}\n🔗 Ссылка: [Открыть трек]({track['url']})\n\n_Всего песен в базе: {len(TRACKS)}_"
    
    keyboard = [
        [
            InlineKeyboardButton("◀️ Назад", callback_data=f"play_{(idx - 1) % len(TRACKS)}"),
            InlineKeyboardButton("▶️ Вперед", callback_data=f"play_{(idx + 1) % len(TRACKS)}")
        ],
        [InlineKeyboardButton("📋 Список песен", callback_data="show_list")]
    ]
    return text, InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text, reply_markup = get_player_data(0)
    await update.message.reply_text(text=text, reply_markup=reply_markup, parse_mode="Markdown")

async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global TRACKS, FILE_SHA
    # Перед открытием инлайна пытаемся получить актуальные треки из GitHub
    updated_tracks, updated_sha = load_tracks()
    if updated_tracks:
        TRACKS, FILE_SHA = updated_tracks, updated_sha

    text, reply_markup = get_player_data(0)
    
    results = [
        InlineQueryResultArticle(
            id=str(uuid4()), 
            title="🎵 Запустить аудио плеер", 
            input_message_content=InputTextMessageContent(message_text=text, parse_mode="Markdown"), 
            reply_markup=reply_markup
        )
    ]
    await update.inline_query.answer(results, cache_time=1)

# АВТОДОБАВЛЕНИЕ: Бот слушает новые аудиофайлы из публичной группы
async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global TRACKS, FILE_SHA

    audio = update.message.audio
    msg_id = update.message.message_id
    
    # Формируем рабочую ссылку для публичной группы
    if update.message.chat.username:
        tg_url = f"https://t.me{update.message.chat.username}/{msg_id}"
    else:
        chat_id = str(update.message.chat_id).replace("-100", "")
        tg_url = f"https://t.mec/{chat_id}/{msg_id}"

    title = audio.title if audio.title else audio.file_name
    if audio.performer:
        title = f"{audio.performer} — {title}"

    # Синхронизируем базу перед записью нового трека
    updated_tracks, updated_sha = load_tracks()
    TRACKS = updated_tracks if updated_tracks else []
    FILE_SHA = updated_sha
    
    # Если база состояла из дефолтной заглушки — очищаем её перед добавлением реального трека
    if len(TRACKS) == 1 and "Плейлист пуст" in TRACKS[0]["title"]:
        TRACKS = []
        
    TRACKS.append({"title": title, "url": tg_url})
    save_tracks(TRACKS, FILE_SHA)
    
    await update.message.reply_text(f"✅ Трек успешно добавлен в плеер:\n*{title}*", parse_mode="Markdown")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    global TRACKS
    # Синхронизируем треки при нажатии кнопок
    updated_tracks, updated_sha = load_tracks()
    if updated_tracks:
        TRACKS = updated_tracks

    if query.data.startswith("play_"):
        # Исправлено: забираем ID трека по индексу после разделения строки
        idx = int(query.data.split("_")[1])
        text, reply_markup = get_player_data(idx)
        await query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode="Markdown")
        
    elif query.data == "show_list":
        list_text = "📋 *Список доступных песен:*\n\n" + "\n".join([f"{i+1}. {t['title']}" for i, t in enumerate(TRACKS)])
        keyboard = [[InlineKeyboardButton("⬅️ Вернуться в плеер", callback_data="play_0")]]
        await query.edit_message_text(text=list_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

def main():
    token = os.environ.get("BOT_TOKEN")
    app = Application.builder().token(token).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(InlineQueryHandler(inline_query))
    app.add_handler(CallbackQueryHandler(button_handler))
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
