from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from pro.methodology_v16 import Intake, YesNoUnknown, decide
from pro.bot_templates import format_doctor_answer


# ---------- КНОПКИ ----------
BTN_YES = "pro_yes"
BTN_NO = "pro_no"
BTN_UNK = "pro_unk"

def yn_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Да", callback_data=BTN_YES),
        InlineKeyboardButton("❌ Нет", callback_data=BTN_NO),
        InlineKeyboardButton("❓ Не знаю", callback_data=BTN_UNK),
    ]])


# ---------- ВОПРОСЫ (КОРОТКО, ВРАЧЕБНО) ----------
QUESTIONS = [
    ("stool_daily", "Стул ежедневный?"),
    ("stool_strain_or_bloating", "Есть вздутие или ощущение неполного опорожнения?"),

    ("low_energy_or_fatigue", "Есть выраженная слабость, нехватка сил?"),
    ("anxiety_or_bad_sleep", "Есть тревожность или нарушения сна?"),

    ("overweight_or_belly", "Есть лишний вес или живот?"),
    ("sugar_cravings_or_postmeal_sleep", "Тяга к сладкому или сонливость после еды?"),

    ("liver_symptoms", "Есть тяжесть справа, горечь, плохая переносимость жирного?"),
    ("active_itch", "Есть активный зуд сейчас?"),

    ("edema_or_pastosity", "Есть отёки или пастозность?"),
    ("lor_chronic", "Есть ЛОР-хроника (гайморит, ринит)?"),
    ("joint_pains_no_infl", "Есть суставные боли без явного воспаления?"),
]


# ---------- ВСПОМОГАТЕЛЬНОЕ ----------
def _get_intake(ctx: ContextTypes.DEFAULT_TYPE) -> Intake:
    if isinstance(ctx.user_data.get("pro_intake"), Intake):
        return ctx.user_data["pro_intake"]
    it = Intake()
    ctx.user_data["pro_intake"] = it
    return it


# ---------- СТАРТ PRO ----------
async def pro_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    # проверка доступа врача
    if update.effective_user.id not in context.application.bot_data.get("AUTHORIZED_DOCTORS", {}):
        await update.message.reply_text("Нет доступа. Сначала используйте /access <CODE>")
        return

    context.user_data["pro_q_idx"] = 0
    context.user_data["pro_case_text"] = (update.message.text or "").replace("/pro", "").strip()

    await update.message.reply_text(
        "Начинаем PRO-анализ по методике AV FITO.\n"
        "Отвечайте кнопками — это займёт 1–2 минуты."
    )
    await ask_next(update, context)


# ---------- ЗАДАТЬ СЛЕДУЮЩИЙ ВОПРОС ----------
async def ask_next(update: Update, context: ContextTypes.DEFAULT_TYPE):
    idx = context.user_data.get("pro_q_idx", 0)
    if idx >= len(QUESTIONS):
        await finalize(update, context)
        return

    _, question = QUESTIONS[idx]

    if update.callback_query:
        await update.callback_query.message.reply_text(question, reply_markup=yn_keyboard())
    else:
        await update.message.reply_text(question, reply_markup=yn_keyboard())


# ---------- ОБРАБОТКА ОТВЕТА ----------
async def pro_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    await query.answer()

    idx = context.user_data.get("pro_q_idx", 0)
    if idx >= len(QUESTIONS):
        return

    field, _ = QUESTIONS[idx]
    intake = _get_intake(context)

    if query.data == BTN_YES:
        value = YesNoUnknown.YES
    elif query.data == BTN_NO:
        value = YesNoUnknown.NO
    else:
        value = YesNoUnknown.UNKNOWN

    setattr(intake, field, value)

    context.user_data["pro_q_idx"] = idx + 1
    await ask_next(update, context)


# ---------- ФИНАЛ ----------
async def finalize(update: Update, context: ContextTypes.DEFAULT_TYPE):
    intake = _get_intake(context)
    decision = decide(intake)

    doctor_name = context.user_data.get("doctor_name", "Доктор")
    case_text = context.user_data.get("pro_case_text", "Клинический кейс без уточнений")

    final_text = format_doctor_answer(
        doctor_name=doctor_name,
        case_text=case_text,
        decision=decision,
    )

    if update.callback_query:
        await update.callback_query.message.reply_text(final_text)
    else:
        await update.message.reply_text(final_text)

    # очистка состояния
    for k in ["pro_q_idx", "pro_case_text", "pro_intake"]:
        context.user_data.pop(k, None)