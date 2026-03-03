from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ConversationHandler, ContextTypes, filters
)

import os
import logging

TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID_RAW = os.getenv("CHAT_ID")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
PORT = int(os.getenv("PORT", "8080"))

if not TOKEN:
    raise RuntimeError("Environment variable BOT_TOKEN is required")

CHAT_ID = None
if CHAT_ID_RAW:
    try:
        CHAT_ID = int(CHAT_ID_RAW)
    except ValueError as exc:
        raise RuntimeError("Environment variable CHAT_ID must be an integer") from exc

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

VACANCY, NAME, PHONE = range(3)

TEXTS = {
    "welcome": "👋 Добро пожаловать!\n\nЧерез этот бот вы можете откликнуться на вакансию.",
    "pick_vacancy": "📌 Пожалуйста, выберите вакансию:",
    "ask_name": "✍️ Введите ваше имя и фамилию:",
    "ask_phone": "📞 Введите ваш номер телефона:",
    "new_application": "📩 Новая заявка",
    "vacancy": "📌 Вакансия",
    "name": "👤 Имя",
    "phone": "📞 Телефон",
    "thanks": "✅ Спасибо! Наш менеджер свяжется с вами.",
    "bad_vacancy": "Выберите вакансию кнопкой ниже.",
    "chat_id_info": "ID этого чата: {chat_id}",
    "send_error": "⚠️ Заявка принята, но не удалось отправить менеджеру. Проверьте CHAT_ID.",
    "unknown_text": "Напишите /start, чтобы начать отклик.",
    "vacancies": [["Сварщик"]],
}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        TEXTS["welcome"]
    )

    await update.message.reply_text(
        TEXTS["pick_vacancy"],
        reply_markup=ReplyKeyboardMarkup(TEXTS["vacancies"], resize_keyboard=True)
    )

    return VACANCY


async def vacancy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    selected = (update.message.text or "").strip()
    logger.info("Vacancy step received text: %r", selected)

    # Keep flow robust: if user typed anything or button text changed slightly,
    # continue the conversation and map to the only available vacancy.
    if not selected:
        await update.message.reply_text(
            TEXTS["bad_vacancy"],
            reply_markup=ReplyKeyboardMarkup(TEXTS["vacancies"], resize_keyboard=True)
        )
        return VACANCY

    context.user_data["vacancy"] = "Сварщик"

    await update.message.reply_text(
        TEXTS["ask_name"],
        reply_markup=ReplyKeyboardRemove()
    )

    return NAME


async def name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["name"] = update.message.text
    logger.info("Name step received")

    await update.message.reply_text(
        TEXTS["ask_phone"]
    )

    return PHONE


async def phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["phone"] = update.message.text
    logger.info("Phone step received")

    data = context.user_data
    target_chat_id = CHAT_ID if CHAT_ID is not None else update.effective_chat.id

    message = (
        f"{TEXTS['new_application']}\n\n"
        f"{TEXTS['vacancy']}: {data['vacancy']}\n"
        f"{TEXTS['name']}: {data['name']}\n"
        f"{TEXTS['phone']}: {data['phone']}"
    )

    try:
        await context.bot.send_message(
            chat_id=target_chat_id,
            text=message
        )
    except Exception:
        logger.exception("Failed to send application to chat_id=%s", target_chat_id)
        await update.message.reply_text(TEXTS["send_error"])
        return ConversationHandler.END

    await update.message.reply_text(
        TEXTS["thanks"]
    )

    return ConversationHandler.END


async def chat_id_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        TEXTS["chat_id_info"].format(chat_id=update.effective_chat.id)
    )


async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("pong")


async def catch_all_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("Catch-all text received outside conversation: %r", update.message.text)
    await update.message.reply_text(TEXTS["unknown_text"])


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.exception("Unhandled exception while processing update", exc_info=context.error)


async def post_init(app):
    if not WEBHOOK_URL:
        # Prevent getUpdates/webhook conflicts when running locally in polling mode.
        await app.bot.delete_webhook(drop_pending_updates=False)
        logger.info("Webhook cleared for polling mode.")

    me = await app.bot.get_me()
    logger.info("Authorized as @%s (id=%s)", me.username, me.id)


app = ApplicationBuilder().token(TOKEN).post_init(post_init).build()

conv_handler = ConversationHandler(
    entry_points=[CommandHandler("start", start)],
    allow_reentry=True,
    states={
        VACANCY: [MessageHandler(filters.TEXT & ~filters.COMMAND, vacancy)],
        NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, name)],
        PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, phone)],
    },
    fallbacks=[CommandHandler("start", start)]
)

app.add_handler(conv_handler)
app.add_handler(CommandHandler("chatid", chat_id_command))
app.add_handler(CommandHandler("ping", ping))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, catch_all_text))
app.add_error_handler(error_handler)

print("Bot started. Mode:", "webhook" if WEBHOOK_URL else "polling")
if CHAT_ID is None:
    print("CHAT_ID is not set. Applications will be sent to the current chat.")

if WEBHOOK_URL:
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        webhook_url=WEBHOOK_URL,
        close_loop=False,
    )
else:
    app.run_polling(close_loop=False)
