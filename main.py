import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, InlineQueryHandler, ContextTypes
from uuid import uuid4

# Список треков (здесь вы можете менять ссылки на свои файлы из Телеграма)
TRACKS = [
    {"title": "Песня 1 — Начало трека", "url": "https://soundhelix.com"},
    {"title": "Песня 2 — Вторая мелодия", "url": "https://soundhelix.com"},
    {"title": "Песня 3 — Финал", "url": "https://soundhelix.com"}
]

# Общая функция для создания текста плеера и кнопок
def get_player_data(idx: int):
    track = TRACKS[idx]
    text = f"🎵 *МУЗЫКАЛЬНЫЙ ПЛЕЕР*\n\n📌 Название: {track['title']}\n🔗 Ссылка: [Открыть трек]({track['url']})\n\n_Управляйте треками ниже (доступно всем в чате):_"
    
    keyboard = [
        [
            InlineKeyboardButton("◀️ Назад", callback_data=f"play_{ (idx - 1) % len(TRACKS) }"),
            InlineKeyboardButton("▶️ Вперед", callback_data=f"play_{ (idx + 1) % len(TRACKS) }")
        ],
        [InlineKeyboardButton("📋 Список песен", callback_data="show_list")]
    ]
    return text, InlineKeyboardMarkup(keyboard)

# Обычный запуск внутри бота через /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text, reply_markup = get_player_data(0)
    await update.message.reply_text(text=text, reply_markup=reply_markup, parse_mode="Markdown")

# РЕЖИМ ДЛЯ ЧУЖИХ ГРУПП: Обработка ввода @имя_бота в поле сообщения
async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.inline_query.query
    text, reply_markup = get_player_data(0) # По умолчанию предлагаем первый трек
    
    results = [
        InlineQueryResultArticle(
            id=str(uuid4()),
            title="🎵 Запустить аудио плеер",
            description="Отправить интерактивный плеер в этот чат",
            input_message_content=InputTextMessageContent(text=text, parse_mode="Markdown"),
            reply_markup=reply_markup
        )
    ]
    await update.inline_query.answer(results, cache_time=1)

# Обработка нажатий на кнопки (Вперед, Назад, Список)
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data

    if data.startswith("play_"):
        idx = int(data.split("_")[1])
        text, reply_markup = get_player_data(idx)
        await query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode="Markdown")
        
    elif data == "show_list":
        list_text = "📋 *Список доступных песен:*\n\n" + "\n".join([f"{i+1}. {t['title']}" for i, t in enumerate(TRACKS)])
        keyboard = [[InlineKeyboardButton("⬅️ Вернуться в плеер", callback_data="play_0")]]
        await query.edit_message_text(text=list_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

def main():
    token = os.environ.get("BOT_TOKEN")
    app = Application.builder().token(token).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(InlineQueryHandler(inline_query)) # Обработчик инлайн режима
    app.add_handler(CallbackQueryHandler(button_handler))
    
    port = int(os.environ.get("PORT", 8443))
    app.run_webhook(
        listen="0.0.0.0",
        port=port,
        url_path=token,
        webhook_url=f"https://{os.environ.get('RENDER_EXTERNAL_HOSTNAME')}/{token}"
    )

if __name__ == '__main__':
    main()
