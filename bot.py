from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, BotCommand
from telegram.constants import ParseMode
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
APPLICATION_TIMEOUT_SECONDS = int(os.getenv("APPLICATION_TIMEOUT_SECONDS", "900"))

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
    "welcome": (
        "👋 Добро пожаловать!\n\n"
        "Через этот бот вы можете откликнуться на вакансию.\n"
    ),
    "pick_vacancy": "📌 Пожалуйста, выберите вакансию:",
    "ask_name": "✍️ Введите ваше имя и фамилию:",
    "ask_phone": "📞 Введите ваш номер телефона:",
    "new_application": "📩 Новая заявка",
    "draft_application": "📝 Незавершенная заявка",
    "vacancy": "📌 Вакансия",
    "name": "👤 Имя",
    "phone": "📞 Телефон",
    "thanks": "✅ Спасибо! Наш менеджер свяжется с вами.",
    "bad_vacancy": "Выберите вакансию кнопкой ниже.",
    "chat_id_info": "ID этого чата: {chat_id}",
    "send_error": "⚠️ Заявка принята, но не удалось отправить менеджеру. Проверьте CHAT_ID.",
    "unknown_text": "Напишите /start, чтобы начать отклик.",
    "unknown_command": "Неизвестная команда. Используйте /start или /help.",
    "timeout_user": "⏳ Время ожидания истекло. Вы можете начать заново: /start",
    "help": (
        "Команды бота:\n"
        "/start - начать отклик\n"
        "/help - помощь\n"
        "/ping - проверка работы\n"
        "/chatid - ID текущего чата\n\n"
        "Если анкета не завершена, через 15 минут менеджер получит черновик."
    ),
    "vacancies": [["Сварщик"], ["Арматурщик"], ["Бетонщик"], ["Электрик"]],
}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_draft_if_needed(update, context, notify_user=False)
    clear_application_data(context)

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

    allowed_vacancies = {"Сварщик", "Арматурщик", "Бетонщик", "Электрик"}
    context.user_data["vacancy"] = selected if selected in allowed_vacancies else "Сварщик"

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

    clear_application_data(context)

    return ConversationHandler.END


async def chat_id_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        TEXTS["chat_id_info"].format(chat_id=update.effective_chat.id)
    )


async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("pong")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(TEXTS["help"])


def format_draft_message(data: dict, user) -> str:
    username = getattr(user, "username", None)
    user_id = getattr(user, "id", "-")
    full_name = getattr(user, "full_name", "Кандидат")
    username_line = f"Username: @{username}" if username else "Username: -"
    profile_line = f'Профиль: <a href="tg://user?id={user_id}">{full_name}</a>'

    return (
        f"{TEXTS['draft_application']}\n\n"
        f"Telegram ID: {user_id}\n"
        f"{username_line}\n"
        f"{profile_line}\n"
        f"{TEXTS['vacancy']}: {data.get('vacancy', '-')}\n"
        f"{TEXTS['name']}: {data.get('name', '-')}\n"
        f"{TEXTS['phone']}: {data.get('phone', '-')}"
    )


def clear_application_data(context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("vacancy", None)
    context.user_data.pop("name", None)
    context.user_data.pop("phone", None)


async def send_draft_if_needed(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    notify_user: bool
):
    data = context.user_data
    has_partial = any(data.get(field) for field in ("vacancy", "name", "phone"))
    if not has_partial:
        return

    target_chat_id = CHAT_ID if CHAT_ID is not None else update.effective_chat.id
    draft_message = format_draft_message(data, update.effective_user)

    try:
        await context.bot.send_message(
            chat_id=target_chat_id,
            text=draft_message,
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        logger.exception("Failed to send draft application to chat_id=%s", target_chat_id)

    if notify_user and update and update.effective_message:
        await update.effective_message.reply_text(TEXTS["timeout_user"])

    clear_application_data(context)


async def on_timeout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_draft_if_needed(update, context, notify_user=True)
    return ConversationHandler.END


async def catch_all_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("Catch-all text received outside conversation: %r", update.message.text)
    await update.message.reply_text(TEXTS["unknown_text"])


async def catch_all_commands(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("Unknown command received: %r", update.message.text)
    await update.message.reply_text(TEXTS["unknown_command"])


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.exception("Unhandled exception while processing update", exc_info=context.error)


async def post_init(app):
    if not WEBHOOK_URL:
        # Prevent getUpdates/webhook conflicts when running locally in polling mode.
        await app.bot.delete_webhook(drop_pending_updates=False)
        logger.info("Webhook cleared for polling mode.")

    await app.bot.set_my_commands([
        BotCommand("start", "Начать отклик"),
        BotCommand("help", "Как пользоваться ботом"),
        BotCommand("ping", "Проверка работы"),
        BotCommand("chatid", "Показать ID чата"),
    ])

    me = await app.bot.get_me()
    logger.info("Authorized as @%s (id=%s)", me.username, me.id)


app = ApplicationBuilder().token(TOKEN).post_init(post_init).build()

conv_handler = ConversationHandler(
    entry_points=[CommandHandler("start", start)],
    allow_reentry=True,
    conversation_timeout=APPLICATION_TIMEOUT_SECONDS,
    states={
        VACANCY: [MessageHandler(filters.TEXT & ~filters.COMMAND, vacancy)],
        NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, name)],
        PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, phone)],
        ConversationHandler.TIMEOUT: [MessageHandler(filters.ALL, on_timeout)],
    },
    fallbacks=[CommandHandler("start", start)]
)

app.add_handler(conv_handler)
app.add_handler(CommandHandler("chatid", chat_id_command))
app.add_handler(CommandHandler("ping", ping))
app.add_handler(CommandHandler("help", help_command))
app.add_handler(MessageHandler(filters.COMMAND, catch_all_commands))
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
