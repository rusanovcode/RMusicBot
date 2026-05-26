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
    url = f"https://github.com{GITHUB_REPO}/contents/{FILE_PATH}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    res = requests.get(url, headers=headers)
    if res.status_code == 200:
        content = res.json()
        file_content = base64.b64decode(content['content']).decode('utf-8')
        return json.loads(file_content), content['sha']
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
    results = [
        InlineQueryResultArticle(
            id=str(uuid4()), 
            title="🎵 Запустить аудио плеер", 
            # Исправлено: text заменено на message_text
            input_message_content=InputTextMessageContent(message_text=text, parse_mode="Markdown"), 
            reply_markup=reply_markup
        )
    ]
    await update.inline_query.answer(results, cache_time=1)

# АВТОДОБАВЛЕНИЕ: Бот слушает новые аудиофайлы от админа
async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global TRACKS, FILE_SHA
    if update.effective_user.id != OWNER_ID:
        return # Игнорируем чужих пользователей

    audio = update.message.audio
    # Получаем прямую ссылку на сообщение в чате
    chat_id = str(update.message.chat_id).replace("-100", "")
    msg_id = update.message.message_id
    tg_url = f"https://t.mec/{chat_id}/{msg_id}" if update.message.chat.type != "private" else f"https://t.meshare/url?url={tg_url}" 
    
    # Если бот в приватном чате, то лучше использовать пересылку или получить File ID, но для инлайн ссылок идеальна ссылка на пост канала/группы
    if update.message.chat.type == "private":
        await update.message.reply_text("⚠️ Внимание: для работы ссылок в чужих группах, пересылайте треки в любой *публичный или приватный суперчат/канал*, где есть этот бот, и берите ссылку оттуда.")
        return

    title = audio.title if audio.title else audio.file_name
    if audio.performer:
        title = f"{audio.performer} — {title}"

    TRACKS, FILE_SHA = load_tracks()
    # Если был дефолтный пустой трек — удаляем его
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
    app.add_handler(MessageHandler(filters.AUDIO, handle_audio)) # Слушаем аудиофайлы
    
    port = int(os.environ.get("PORT", 8443))
    app.run_webhook(listen="0.0.0.0", port=port, url_path=token, webhook_url=f"https://{os.environ.get('RENDER_EXTERNAL_HOSTNAME')}/{token}")

if __name__ == '__main__':
    main()
