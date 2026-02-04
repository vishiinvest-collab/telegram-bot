import os
import re
import logging

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

from openai import OpenAI


# ---------- LOGGING ----------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

print("BOOT1: imports ok", flush=True)

# ---------- ENV ----------
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
DOCTOR_NAME_DEFAULT = os.getenv("DOCTOR_NAME", "Доктор").strip()

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing. Set it in Render Environment variables.")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY is missing. Set it in Render Environment variables.")

client = OpenAI(api_key=OPENAI_API_KEY)


# ---------- SAFETY: strip sensitive % ----------
def _strip_sensitive(text: str) -> str:
    # Убираем любые "проценты" из текста, если вдруг врач их впишет
    return re.sub(r"\b\d{1,3}\s*%\b", "[%]", text)


def build_gpt_prompt(draft: str, doctor_name: str) -> str:
    draft = _strip_sensitive(draft)

    return f"""
Ты — медицинский редактор бренда AV FITO (Detox System by Doc. Victor Bondarenco).
Задача: сделать из черновика врача чистый, структурированный, клиентоориентированный текст.

Вход: черновик рекомендаций врача.
Выход: финальная версия для клиента.

Жёсткие правила:
- НЕ упоминать, что это сгенерировано ИИ.
- НЕ добавлять выдуманные диагнозы/анализы/лекарства.
- НЕ добавлять дозировки/назначения рецептурных препаратов.
- НЕ указывать процентное соотношение ингредиентов (если встречается — убери).
- Язык: русский, тёплый профессиональный тон.
- Формат: заголовок + пункты + короткие абзацы, без воды.
- В конце подпись бренда.

Структура:
1) Заголовок: «Рекомендации доктора {doctor_name}»
2) Краткое резюме (1–3 предложения)
3) Блок «Что делаем сейчас» (список)
4) Блок «На что обратить внимание» (список)
5) Мягкий дисклеймер: «Если симптомы усиливаются — обратитесь к врачу/вызовите скорую при острых состояниях»
6) Подпись: «— AV FITO · Doc. Victor Bondarenco»

Черновик врача:
---
{draft}
---
""".strip()


# ---------- TELEGRAM HANDLERS ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "✅ AV FITO бот запущен.\n\n"
        "Отправь мне текст черновика врача — я оформлю его как финальные рекомендации.\n"
        "Команды:\n"
        " /start — проверка\n"
        " /doctor Имя Фамилия — указать имя доктора для подписи"
    )


async def set_doctor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # /doctor Victor Bondarenco
    name = " ".join(context.args).strip()
    if not name:
        await update.message.reply_text("Укажи имя после команды, например:\n/doctor Victor Bondarenco")
        return
    context.user_data["doctor_name"] = name
    await update.message.reply_text(f"✅ Имя доктора сохранено: {name}")


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    draft = (update.message.text or "").strip()
    if not draft:
        return

    doctor_name = context.user_data.get("doctor_name", DOCTOR_NAME_DEFAULT)

    prompt = build_gpt_prompt(draft=draft, doctor_name=doctor_name)

    # Быстрый UX
    await update.message.reply_text("🧾 Принято. Оформляю рекомендации...")

    try:
        # Модель можно вынести в env при желании: OPENAI_MODEL
        model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "Ты аккуратный медицинский редактор. Соблюдай жёсткие правила из промпта."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.4,
        )

        text = resp.choices[0].message.content or ""
        text = _strip_sensitive(text)  # двойная защита на выходе

        # Telegram лимит ~4096 символов: режем аккуратно
        if len(text) <= 3800:
            await update.message.reply_text(text)
        else:
            # отправляем частями
            chunk_size = 3800
            for i in range(0, len(text), chunk_size):
                await update.message.reply_text(text[i:i + chunk_size])

    except Exception as e:
        logging.exception("OpenAI call failed")
        await update.message.reply_text(f"❌ Ошибка при обработке. Детали в логах.\n({type(e).__name__})")


def main():
    print("BOOT3: run_polling next", flush=True)

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("doctor", set_doctor))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    logging.info("BOOT4: polling starting now...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
