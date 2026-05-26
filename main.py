import os
import json
import base64
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, InlineQueryHandler, MessageHandler, filters, ContextTypes
from uuid import uuid4

# Конфигурация GitHub для автосохранения
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_REPO = os.environ.get("GITHUB_REPO")
OWNER_ID = int(os.environ.get("OWNER_ID", 0))
FILE_PATH = "playlist.json"

def load_tracks():
    # Исправлен адрес API GitHub
    url = f"https://github.com{GITHUB_REPO}/contents/{FILE_PATH}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    res = requests.get(url, headers=headers)
    if res.status_code == 200:
        content = res.json()
        file_content = base64.b64decode(content['content']).decode('utf-8')
        return json.loads(file_content), content['sha']
    return [], None

def save_tracks(tracks, sha=None):
    # Исправлен адрес API GitHub
    url = f"https://github.com{GITHUB_REPO}/contents/{FILE_PATH}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    data = {
        "message": "Update playlist via Telegram Bot",
        "content": base64.b64encode(json.dumps(tracks, ensure_ascii=False, indent=4).encode('utf-8')).decode('utf-8')
    }
    if sha:
        data["sha"] = sha
    requests.put(url, headers=headers, json=data)

# Загружаем треки при старте
try:
    TRACKS, FILE_SHA = load_tracks()
except:
    TRACKS, FILE_SHA = [], None

if not TRACKS:
    TRACKS = [{"title": "Плейлист пуст. Отправьте мне mp3 файлы!", "url": "https://t.me"}]

def get_player_data(idx: int):
    idx = idx % len(TRACKS)
    track = TRACKS[idx]
    text = f"🎵 *МУЗЫКАЛЬНЫЙ ПЛЕЕР*\n\n📌 Название: {track['title']}\n🔗 Ссылка: [Открыть трек]({track['url']})\n\n_Всего песен в базе: {len(TRACKS)}_"
    
    keyboard = [
        [
            InlineKeyboardButton("◀️ Назад", callback_data=f"play_{ (idx - 1) % len(TRACKS) }"),
            InlineKeyboardButton("▶️ Вперед", callback_data=f"play_{ (idx + 1) % len(TRACKS) }")
        ],
        [InlineKeyboardButton("📋 Список песен", callback_data="show_list")]
    ]
    return text, InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text, reply_markup = get_player_data(0)
    await update.message.reply_text(text=text, reply_markup=reply_markup, parse_mode="Markdown")

async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text, reply_markup = get_player_data(0)
    # ИСПРАВЛЕНО: text заменен на аргумент message_text
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
    if OWNER_ID and update.effective_user.id != OWNER_ID:
        return # Игнорируем чужих пользователей, если задан OWNER_ID

    audio = update.message.audio
    msg_id = update.message.message_id
    
    # ИСПРАВЛЕНО: Генерация ссылки для публичной группы по её юзернейму
    if update.message.chat.username:
        tg_url = f"https://t.me{update.message.chat.username}/{msg_id}"
    else:
        # Резервный вариант, если у группы нет короткого имени, но она публичная
        chat_id = str(update.message.chat_id).replace("-100", "")
        tg_url = f"https://t.mec/{chat_id}/{msg_id}"

    title = audio.title if audio.title else audio.file_name
    if audio.performer:
        title = f"{audio.performer} — {title}"

    TRACKS, FILE_SHA = load_tracks()
    
    if len(TRACKS) == 1 and "Плейлист пуст" in TRACKS[0]["title"]:
        TRACKS = []
        
    TRACKS.append({"title": title, "url": tg_url})
    save_tracks(TRACKS, FILE_SHA)
    
    await update.message.reply_text(f"✅ Трек успешно добавлен в плеер:\n*{title}*", parse_mode="Markdown")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data.startswith("play_"):
        idx = int(query.data.split("_")[1])
        text, reply_markup = get_player_data(idx)
        await query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode="Markdown")
    elif query.data == "show_list":
        TRACKS_CURRENT, _ = load_tracks()
        list_text = "📋 *Список доступных песен:*\n\n" + "\n".join([f"{i+1}. {t['title']}" for i, t in enumerate(TRACKS_CURRENT or TRACKS)])
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
