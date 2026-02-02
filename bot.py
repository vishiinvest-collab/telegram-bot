import os
import logging
from typing import Dict

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# -----------------------------
# ENV
# -----------------------------
BOT_TOKEN = (os.getenv("BOT_TOKEN", "") or "").strip()
OWNER_TG_ID = (os.getenv("OWNER_TG_ID", "") or "").strip()
DOCTOR_CODES_RAW = (os.getenv("DOCTOR_CODES", "") or "").strip()

# -----------------------------
# State (in-memory)
# -----------------------------
AUTHORIZED_DOCTORS: Dict[int, str] = {}  # user_id -> doctor_name
WAITING_DRAFT_FOR: Dict[int, bool] = {}  # user_id -> waiting for draft text?
DRAFT_TEXT: Dict[int, str] = {}          # user_id -> last draft text


def parse_doctor_codes(raw: str) -> Dict[str, str]:
    """
    DOCTOR_CODES="CODE1:Doctor Name;CODE2:Doctor Name2"
    """
    out: Dict[str, str] = {}
    if not raw:
        return out
    parts = [p.strip() for p in raw.split(";") if p.strip()]
    for p in parts:
        if ":" not in p:
            continue
        code, name = p.split(":", 1)
        code = code.strip()
        name = (name or "").strip() or "Доктор"
        if code:
            out[code] = name
    return out


DOCTOR_CODES = parse_doctor_codes(DOCTOR_CODES_RAW)


def owner_only(user_id: int) -> bool:
    return OWNER_TG_ID.isdigit() and int(OWNER_TG_ID) == user_id


def is_private(update: Update) -> bool:
    return bool(update.effective_chat and update.effective_chat.type == "private")


def approve_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Approve", callback_data="appr")],
        [InlineKeyboardButton("❌ Cancel", callback_data="canc")],
    ])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_private(update) or not update.message:
        return
    await update.message.reply_text(
        "Я бот для врачей AV FITO (работаю в личке).\n"
        "1) /access <CODE> — доступ\n"
        "2) /draft — создать черновик\n"
        "3) пришлите текст одним сообщением → Approve\n\n"
        "Финал будет оформлен «как от бренда» с подписью врача."
    )


async def access(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_private(update) or not update.message:
        return

    user = update.effective_user
    if not user:
        return

    if len(context.args) < 1:
        await update.message.reply_text("Формат: /access AV-DR-0001")
        return

    code = context.args[0].strip()
    if code not in DOCTOR_CODES:
        await update.message.reply_text("Код не найден. Проверьте код доступа.")
        return

    doctor_name = DOCTOR_CODES[code]
    AUTHORIZED_DOCTORS[user.id] = doctor_name

    await update.message.reply_text(
        f"Доступ подтверждён ✅\n"
        f"Вы зарегистрированы как: {doctor_name}\n\n"
        f"Дальше: /draft"
    )


async def draft(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_private(update) or not update.message:
        return

    user = update.effective_user
    if not user:
        return

    if user.id not in AUTHORIZED_DOCTORS:
        await update.message.reply_text("Нет доступа. Сначала: /access <CODE>")
        return

    WAITING_DRAFT_FOR[user.id] = True
    await update.message.reply_text(
        "Ок. Отправьте текст рекомендаций ОДНИМ сообщением.\n"
        "После этого появится кнопка Approve."
    )


async def addcode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Owner helper: показывает, как добавить код в DOCTOR_CODES."""
    if not is_private(update) or not update.message:
        return

    user = update.effective_user
    if not user or not owner_only(user.id):
        await update.message.reply_text("Команда доступна только владельцу.")
        return

    if len(context.args) < 2:
        await update.message.reply_text("Формат: /addcode AV-DR-1234 доктор Иванов")
        return

    code = context.args[0].strip()
    name = " ".join(context.args[1:]).strip()

    await update.message.reply_text(
        "Добавьте это в переменную DOCTOR_CODES (через ;):\n"
        f"{code}:{name}\n\n"
        "Пример:\n"
        "AV-DR-0001:доктор Асем;AV-DR-1234:доктор Иванов"
    )


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_private(update) or not update.message:
        return

    user = update.effective_user
    if not user:
        return

    if not WAITING_DRAFT_FOR.get(user.id):
        return

    if user.id not in AUTHORIZED_DOCTORS:
        WAITING_DRAFT_FOR.pop(user.id, None)
        await update.message.reply_text("Нет доступа. /access <CODE>")
        return

    text = (update.message.text or "").strip()
    if not text:
        await update.message.reply_text("Текст пустой. Отправьте одним сообщением.")
        return

    WAITING_DRAFT_FOR[user.id] = False
    DRAFT_TEXT[user.id] = text

    doctor_name = AUTHORIZED_DOCTORS.get(user.id, "Доктор")
    await update.message.reply_text(
        f"Черновик готов (доктор: {doctor_name}).\n"
        "Нажмите Approve — и я выдам финальный текст «как от бренда".,
        reply_markup=approve_keyboard(),
    )


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    await query.answer()

    user = update.effective_user
    if not user:
        return

    data = query.data or ""

    if data == "canc":
        DRAFT_TEXT.pop(user.id, None)
        WAITING_DRAFT_FOR[user.id] = False
        await query.edit_message_text("Отменено ❌")
        return

    if data == "appr":
        if user.id not in AUTHORIZED_DOCTORS:
            await query.edit_message_text("Нет доступа. /access <CODE>")
            return

        draft_text = DRAFT_TEXT.get(user.id)
        if not draft_text:
            await query.edit_message_text("Черновик не найден. Сделайте /draft заново.")
            return

        doctor_name = AUTHORIZED_DOCTORS.get(user.id, "Доктор")

        final_text = (
            f"Рекомендации доктора {doctor_name}\n\n"
            f"{draft_text}\n\n"
            "— AV FITO · Doc. Victor Bondarenco"
        )

        await context.bot.send_message(chat_id=query.message.chat_id, text=final_text)
        await query.edit_message_text("Готово ✅ Финальный текст отправлен отдельным сообщением.")


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logging.exception("Unhandled exception in handler", exc_info=context.error)


def main() -> None:
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
    )

    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN environment variable is not set")

    if not DOCTOR_CODES:
        logging.warning("DOCTOR_CODES is empty. /access will not grant access until you set DOCTOR_CODES.")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("access", access))
    app.add_handler(CommandHandler("draft", draft))
    app.add_handler(CommandHandler("addcode", addcode))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    app.add_error_handler(on_error)

    logging.info("Starting bot polling...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()