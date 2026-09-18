# -*- coding: utf-8 -*-
import logging
import os

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import db
from data import BUDGET_OPTIONS, CITIES, GRADE_OPTIONS, INTERESTS
from scoring import compute_recommendations, compute_roadmap

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

(GRADE, INTERESTS_STEP, ENT, LANGUAGES, BUDGET, CITY, MENU) = range(7)

LANG_LABELS = {"kz": "Казахский", "ru": "Русский", "en": "Английский"}


def kb_from_pairs(pairs, prefix, cols=1):
    rows, row = [], []
    for key, label in pairs:
        row.append(InlineKeyboardButton(label, callback_data=f"{prefix}:{key}"))
        if len(row) == cols:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(rows)


def kb_interests(selected):
    rows = []
    for key, label in INTERESTS:
        mark = "✅ " if key in selected else ""
        rows.append([InlineKeyboardButton(f"{mark}{label}", callback_data=f"int:{key}")])
    rows.append([InlineKeyboardButton("Готово ➡️", callback_data="int:done")])
    return InlineKeyboardMarkup(rows)


def kb_languages(selected):
    rows = []
    for key, label in LANG_LABELS.items():
        mark = "✅ " if key in selected else ""
        rows.append([InlineKeyboardButton(f"{mark}{label}", callback_data=f"lang:{key}")])
    rows.append([InlineKeyboardButton("Готово ➡️", callback_data="lang:done")])
    return InlineKeyboardMarkup(rows)


def kb_menu():
    rows = [
        [InlineKeyboardButton("📊 Рекомендации", callback_data="menu:recs")],
        [InlineKeyboardButton("⚖️ Сравнить 2 варианта", callback_data="menu:compare")],
        [InlineKeyboardButton("🗺 Мой roadmap", callback_data="menu:roadmap")],
        [InlineKeyboardButton("✅ Прогресс", callback_data="menu:progress")],
        [InlineKeyboardButton("✏️ Изменить анкету", callback_data="menu:edit")],
    ]
    return InlineKeyboardMarkup(rows)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data["interests"] = []
    context.user_data["languages"] = []
    text = (
        "👋 Привет! Я помогу построить *персональный маршрут поступления*: "
        "от короткой анкеты — до конкретного плана действий с дедлайнами.\n\n"
        "Сейчас фокус — на бакалавриате в Казахстане (демо-версия). "
        "Отвечайте на вопросы, и через 6 шагов вы получите:\n"
        "• диагностику своего профиля\n"
        "• минимум 3 подходящих вуза с объяснением «почему»\n"
        "• сравнение вариантов\n"
        "• пошаговый roadmap с ближайшим шагом\n\n"
        "⚠️ Данные о вузах в этом прототипе демонстрационные — сверяйте с сайтами вузов.\n\n"
        "Шаг 1/6. В каком вы классе?"
    )
    await update.message.reply_text(text, parse_mode="Markdown",
                                     reply_markup=kb_from_pairs(GRADE_OPTIONS, "grade"))
    return GRADE


async def on_grade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    context.user_data["grade"] = q.data.split(":", 1)[1]
    await q.edit_message_text(
        "Шаг 2/6. Какие направления вам интересны? Можно выбрать несколько, "
        "затем нажмите «Готово».",
        reply_markup=kb_interests(context.user_data["interests"]),
    )
    return INTERESTS_STEP


async def on_interest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    key = q.data.split(":", 1)[1]
    if key == "done":
        if not context.user_data["interests"]:
            await q.answer("Выберите хотя бы одно направление", show_alert=True)
            return INTERESTS_STEP
        await q.edit_message_text(
            "Шаг 3/6. Какой у вас балл ЕНТ (или ожидаемый)? Введите число от 0 до 140.\n"
            "Если ещё не сдавали — напишите примерную оценку."
        )
        return ENT
    sel = context.user_data["interests"]
    if key in sel:
        sel.remove(key)
    else:
        sel.append(key)
    await q.edit_message_reply_markup(reply_markup=kb_interests(sel))
    return INTERESTS_STEP


async def on_ent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    try:
        val = int(text)
        if not 0 <= val <= 140:
            raise ValueError
    except ValueError:
        await update.message.reply_text("Введите число от 0 до 140, например: 95")
        return ENT
    context.user_data["ent_score"] = val
    await update.message.reply_text(
        "Шаг 4/6. На каких языках вам комфортно учиться? Выберите один или несколько.",
        reply_markup=kb_languages(context.user_data["languages"]),
    )
    return LANGUAGES


async def on_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    key = q.data.split(":", 1)[1]
    if key == "done":
        if not context.user_data["languages"]:
            await q.answer("Выберите хотя бы один язык", show_alert=True)
            return LANGUAGES
        await q.edit_message_text(
            "Шаг 5/6. Какой у вас бюджет на обучение в год?",
            reply_markup=kb_from_pairs(BUDGET_OPTIONS, "budget"),
        )
        return BUDGET
    sel = context.user_data["languages"]
    if key in sel:
        sel.remove(key)
    else:
        sel.append(key)
    await q.edit_message_reply_markup(reply_markup=kb_languages(sel))
    return LANGUAGES


async def on_budget(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    context.user_data["budget"] = q.data.split(":", 1)[1]
    city_pairs = [(c, c) for c in CITIES]
    await q.edit_message_text(
        "Шаг 6/6. В каком городе хотите учиться?",
        reply_markup=kb_from_pairs(city_pairs, "city"),
    )
    return CITY


async def on_city(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    context.user_data["city"] = q.data.split(":", 1)[1]

    profile = {
        "grade": context.user_data["grade"],
        "interests": context.user_data["interests"],
        "ent_score": context.user_data["ent_score"],
        "languages": context.user_data["languages"],
        "budget": context.user_data["budget"],
        "city": context.user_data["city"],
    }
    user_id = update.effective_user.id
    db.save_profile(user_id, profile)

    await q.edit_message_text(_diagnostics_text(profile), parse_mode="Markdown")
    await _send_recommendations(update.effective_chat.id, context, user_id, profile)
    await context.bot.send_message(
        update.effective_chat.id,
        "Выберите, что дальше 👇",
        reply_markup=kb_menu(),
    )
    return MENU


def _diagnostics_text(profile):
    grade_map = dict(GRADE_OPTIONS)
    budget_map = dict(BUDGET_OPTIONS)
    strengths = []
    limits = []
    if profile["ent_score"] and profile["ent_score"] >= 90:
        strengths.append("высокий балл ЕНТ")
    elif profile["ent_score"] and profile["ent_score"] < 60:
        limits.append("балл ЕНТ пока ниже порогов большинства сильных вузов")
    if profile["budget"] == "grant":
        limits.append("нужен грант/бюджетное место — сужает выбор")
    if "en" in profile["languages"]:
        strengths.append("готовность учиться на английском расширяет выбор")

    lines = [
        "🧭 *Диагностика профиля*",
        f"Класс: {grade_map.get(profile['grade'], profile['grade'])}",
        f"Балл ЕНТ: {profile['ent_score']}",
        f"Бюджет: {budget_map.get(profile['budget'], profile['budget'])}",
        f"Город: {profile['city']}",
    ]
    if strengths:
        lines.append("Сильные стороны: " + "; ".join(strengths))
    if limits:
        lines.append("Ограничения: " + "; ".join(limits))
    return "\n".join(lines)


async def _send_recommendations(chat_id, context, user_id, profile):
    recs = compute_recommendations(profile, top_n=3)
    db.save_recommendations(user_id, recs)
    text_parts = ["🎯 *Рекомендации* (минимум 3, по убыванию соответствия):\n"]
    for i, r in enumerate(recs, 1):
        reasons = "; ".join(r["reasons"]) if r["reasons"] else "базовое совпадение по параметрам"
        text_parts.append(
            f"{i}. *{r['name']}* ({r['city']}) — совпадение {r['score']}%\n"
            f"   Почему подходит: {reasons}\n"
            f"   Демо-источник: {r['source']}"
        )
    await context.bot.send_message(chat_id, "\n\n".join(text_parts), parse_mode="Markdown")


async def menu_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    action = q.data.split(":", 1)[1]
    user_id = update.effective_user.id
    profile = db.get_profile(user_id)

    if action == "recs":
        await _send_recommendations(q.message.chat_id, context, user_id, profile)
        await context.bot.send_message(q.message.chat_id, "Что дальше?", reply_markup=kb_menu())
        return MENU

    if action == "compare":
        recs = db.get_recommendations(user_id)
        rows = [[InlineKeyboardButton(r["name"], callback_data=f"cmpA:{r['id']}")] for r in recs]
        await context.bot.send_message(
            q.message.chat_id, "Выберите первый вариант для сравнения:",
            reply_markup=InlineKeyboardMarkup(rows),
        )
        return MENU

    if action == "roadmap":
        recs = db.get_recommendations(user_id)
        if not recs:
            await context.bot.send_message(q.message.chat_id, "Сначала посмотрите рекомендации.")
            return MENU
        top = recs[0]
        steps = compute_roadmap(profile, top)
        db.save_roadmap(user_id, steps)
        await _render_roadmap(q.message.chat_id, context, user_id, top["name"])
        return MENU

    if action == "progress":
        await _render_roadmap(q.message.chat_id, context, user_id, None, header_only=True)
        return MENU

    if action == "edit":
        await context.bot.send_message(q.message.chat_id, "Ок, пройдём анкету заново.")
        return await _restart_via_callback(update, context)

    return MENU


async def _restart_via_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data["interests"] = []
    context.user_data["languages"] = []
    await context.bot.send_message(
        update.effective_chat.id,
        "Шаг 1/6. В каком вы классе?",
        reply_markup=kb_from_pairs(GRADE_OPTIONS, "grade"),
    )
    return GRADE


async def compare_a(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    prog_id = q.data.split(":", 1)[1]
    context.user_data["cmp_a"] = prog_id
    user_id = update.effective_user.id
    recs = [r for r in db.get_recommendations(user_id) if r["id"] != prog_id]
    rows = [[InlineKeyboardButton(r["name"], callback_data=f"cmpB:{r['id']}")] for r in recs]
    await q.edit_message_text("Теперь выберите второй вариант:", reply_markup=InlineKeyboardMarkup(rows))
    return MENU


async def compare_b(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    prog_id_b = q.data.split(":", 1)[1]
    prog_id_a = context.user_data.get("cmp_a")
    user_id = update.effective_user.id
    recs = {r["id"]: r for r in db.get_recommendations(user_id)}
    a, b = recs.get(prog_id_a), recs.get(prog_id_b)
    if not a or not b:
        await q.edit_message_text("Не удалось найти варианты для сравнения, попробуйте снова.")
        return MENU

    def fmt(p):
        tuition = "0 (грант)" if p["tuition_category"] == "grant_only" else f"{p['tuition_tenge_year']:,} ₸/год".replace(",", " ")
        return (
            f"*{p['name']}*\n"
            f"Город: {p['city']}\n"
            f"Порог ЕНТ (демо): {p['ent_threshold']}\n"
            f"Стоимость (демо): {tuition}\n"
            f"Дедлайн (демо): {p['deadline']}\n"
            f"Стипендии: {p['scholarship_note']}"
        )

    text = "⚖️ *Сравнение вариантов*\n\n" + fmt(a) + "\n\n— vs —\n\n" + fmt(b)
    await q.edit_message_text(text, parse_mode="Markdown")
    await context.bot.send_message(q.message.chat_id, "Что дальше?", reply_markup=kb_menu())
    return MENU


async def _render_roadmap(chat_id, context, user_id, program_name, header_only=False):
    steps = db.get_roadmap(user_id)
    if not steps:
        await context.bot.send_message(chat_id, "Roadmap ещё не построен — откройте «Рекомендации», затем «Мой roadmap».")
        return
    header = "✅ *Прогресс по roadmap*" if header_only else f"🗺 *Roadmap*: {program_name}"
    lines = [header]
    rows = []
    next_step_idx = None
    for i, s in enumerate(steps):
        mark = "✅" if s["done"] else "⬜️"
        lines.append(f"{mark} {i+1}. {s['text']}")
        if not s["done"] and next_step_idx is None:
            next_step_idx = i
    if next_step_idx is not None:
        lines.append(f"\n👉 *Ближайший шаг*: {steps[next_step_idx]['text']}")
        rows.append([InlineKeyboardButton("✅ Отметить шаг выполненным", callback_data=f"done:{next_step_idx}")])
    else:
        lines.append("\n🎉 Все шаги выполнены!")
    await context.bot.send_message(chat_id, "\n".join(lines), parse_mode="Markdown",
                                    reply_markup=InlineKeyboardMarkup(rows) if rows else None)


async def mark_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer("Отмечено ✅")
    idx = int(q.data.split(":", 1)[1])
    user_id = update.effective_user.id
    db.mark_step_done(user_id, idx, True)
    await _render_roadmap(q.message.chat_id, context, user_id, None, header_only=True)
    await context.bot.send_message(q.message.chat_id, "Что дальше?", reply_markup=kb_menu())
    return MENU


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Окей, анкета отменена. Наберите /start, когда будете готовы.")
    return ConversationHandler.END


def build_app():
    # Токен напрямую вставлен здесь:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "8895478279:AAHwUVmthxdBFs8FfCjGd0_unDndzt3lYJ8")

    db.init_db()
    app = Application.builder().token(token).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            GRADE: [CallbackQueryHandler(on_grade, pattern="^grade:")],
            INTERESTS_STEP: [CallbackQueryHandler(on_interest, pattern="^int:")],
            ENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, on_ent)],
            LANGUAGES: [CallbackQueryHandler(on_language, pattern="^lang:")],
            BUDGET: [CallbackQueryHandler(on_budget, pattern="^budget:")],
            CITY: [CallbackQueryHandler(on_city, pattern="^city:")],
            MENU: [
                CallbackQueryHandler(menu_router, pattern="^menu:"),
                CallbackQueryHandler(compare_a, pattern="^cmpA:"),
                CallbackQueryHandler(compare_b, pattern="^cmpB:"),
                CallbackQueryHandler(mark_done, pattern="^done:"),
                CallbackQueryHandler(on_grade, pattern="^grade:"),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel), CommandHandler("start", start)],
        allow_reentry=True,
    )
    app.add_handler(conv)
    return app


if __name__ == "__main__":
    application = build_app()
    logger.info("Бот запущен, ожидаю сообщения...")
    application.run_polling()