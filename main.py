import os
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# Простейший список песен (Сюда вы сможете добавлять свои ссылки на mp3 файлы)
TRACKS = [
    {"title": "Песня 1 — Начало трека", "url": "https://soundhelix.com"},
    {"title": "Песня 2 — Вторая мелодия", "url": "https://soundhelix.com"},
    {"title": "Песня 3 — Финал", "url": "https://soundhelix.com"}
]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['current_index'] = 0
    await send_player(update, context, edit=False)

async def send_player(update: Update, context: ContextTypes.DEFAULT_TYPE, edit=True):
    idx = context.user_data.get('current_index', 0)
    track = TRACKS[idx]
    
    text = f"🎵 *СЕЙЧАС ИГРАЕТ*\n\n📌 Название: {track['title']}\n🔗 Ссылка: [Открыть трек]({track['url']})\n\n_Управляйте плеером кнопками ниже:_"
    
    keyboard = [
        [
            InlineKeyboardButton("◀️ Назад", callback_data="prev"),
            InlineKeyboardButton("▶️ Вперед", callback_data="next")
        ],
        [InlineKeyboardButton("📋 Список песен", callback_data="list")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if edit:
        query = update.callback_query
        await query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        await update.message.reply_text(text=text, reply_markup=reply_markup, parse_mode="Markdown")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    idx = context.user_data.get('current_index', 0)
    
    if query.data == "next":
        idx = (idx + 1) % len(TRACKS)
    elif query.data == "prev":
        idx = (idx - 1) % len(TRACKS)
    elif query.data == "list":
        list_text = "📋 *Список доступных песен:*\n\n" + "\n".join([f"{i+1}. {t['title']}" for i, t in enumerate(TRACKS)])
        keyboard = [[InlineKeyboardButton("⬅️ Вернуться в плеер", callback_data="back_to_player")]]
        await query.edit_message_text(text=list_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        return

    context.user_data['current_index'] = idx
    await send_player(update, context, edit=True)

def main():
    # Render автоматически передаст токен сюда
    token = os.environ.get("BOT_TOKEN")
    app = Application.builder().token(token).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    
    # Запуск вебхука для Render (чтобы работал на бесплатном тарифе)
    port = int(os.environ.get("PORT", 8443))
    app.run_webhook(listen="0.0.0.0", port=port, url_path=token, webhook_url=f"https://{os.environ.get('RENDER_EXTERNAL_HOSTNAME')}/{token}")

if __name__ == '__main__':
    main()
