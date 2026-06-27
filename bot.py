import asyncio
import sys
import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, CallbackQueryHandler, ConversationHandler, ContextTypes
)
from sqlalchemy import select, func, and_
from config import TELEGRAM_TOKEN
from database import init_db, async_session
from models import User, Meal, Goal
from handlers.meal import handle_text, meal_type_callback, SELECT_MEAL_TYPE
from handlers.photo import handle_photo, photo_meal_type_callback, PHOTO_CONFIRM

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ─── Главное меню ───
def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📊 Статистика", callback_data="menu_stats"),
            InlineKeyboardButton("📅 История", callback_data="menu_history"),
        ],
        [InlineKeyboardButton("🎯 Цель", callback_data="menu_goal")],
    ])


# ─── Универсальная отправка ответа ───
async def send_reply(update: Update, text: str, keyboard=None):
    reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
        except Exception:
            await update.callback_query.message.reply_text(text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, reply_markup=reply_markup)


# ─── /start ───
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == user.id))
        db_user = result.scalar_one_or_none()
        if not db_user:
            db_user = User(telegram_id=user.id, username=user.username, first_name=user.first_name)
            session.add(db_user)
            session.add(Goal(user_id=user.id))
            await session.commit()

        await send_reply(
            update,
            f"👋 Привет, {user.first_name}!\n\n"
            "Отправь мне:\n"
            "• Текст: `курица 200г, рис 150г`\n"
            "• Фото блюда — распознаю автоматически\n"
            "• Несколько продуктов через запятую или с новой строки",
            [
                [
                    InlineKeyboardButton(" Статистика", callback_data="menu_stats"),
                    InlineKeyboardButton("📅 История", callback_data="menu_history"),
                ],
                [InlineKeyboardButton("🎯 Цель", callback_data="menu_goal")],
            ],
        )


# ─── /stats ───
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    async with async_session() as session:
        db_user = (await session.execute(select(User).where(User.telegram_id == user.id))).scalar_one_or_none()
        if not db_user:
            await send_reply(update, "❌ Сначала нажми /start")
            return

        goal = (await session.execute(select(Goal).where(Goal.user_id == db_user.id))).scalar_one_or_none()
        today = datetime.now().strftime("%Y-%m-%d")

        total = (await session.execute(
            select(func.sum(Meal.calories), func.sum(Meal.protein),
                   func.sum(Meal.fat), func.sum(Meal.carbs))
            .where(and_(Meal.user_id == db_user.id, Meal.date == today))
        )).first()

        calories, protein, fat, carbs = (total[0] or 0, total[1] or 0, total[2] or 0, total[3] or 0)
        goal_cal = goal.calories if goal else 2000
        goal_p = goal.protein if goal else 100
        goal_f = goal.fat if goal else 70
        goal_c = goal.carbs if goal else 250
        cal_pct = round((calories / goal_cal) * 100) if goal_cal else 0

        response = (
            f"📊 Статистика за {today}\n\n"
            f"🔥 {calories} / {goal_cal} ккал ({cal_pct}%)\n"
            f"{'█' * min(cal_pct // 5, 20)}{'░' * max(20 - cal_pct // 5, 0)}\n\n"
            f" Белки: {protein}/{goal_p}г\n"
            f"🥑 Жиры: {fat}/{goal_f}г\n"
            f"🍞 Углеводы: {carbs}/{goal_c}г\n\n"
            f"─────────────────\n"
            f"📅 По приемам пищи:\n"
        )

        meal_stats = (await session.execute(
            select(Meal.meal_type, func.sum(Meal.calories))
            .where(and_(Meal.user_id == db_user.id, Meal.date == today))
            .group_by(Meal.meal_type)
        )).all()

        meal_types = {"breakfast": "🍳 Завтрак", "lunch": " Обед", "dinner": "🌙 Ужин", "snack": "🍎 Перекус"}
        for mt, mc in meal_stats:
            if mt in meal_types:
                response += f"{meal_types[mt]}: {mc} ккал\n"

        await send_reply(update, response, [[InlineKeyboardButton("🏠 Главное меню", callback_data="menu_main")]])


# ─── /history ───
async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    async with async_session() as session:
        db_user = (await session.execute(select(User).where(User.telegram_id == user.id))).scalar_one_or_none()
        if not db_user:
            await send_reply(update, "❌ Сначала нажми /start")
            return

        today = datetime.now().date()
        response = " История за последние 7 дней:\n\n"

        for i in range(6, -1, -1):
            date = (today - timedelta(days=i)).strftime("%Y-%m-%d")
            meals = (await session.execute(
                select(Meal.name, Meal.meal_type, Meal.calories)
                .where(and_(Meal.user_id == db_user.id, Meal.date == date))
                .order_by(Meal.meal_type)
            )).all()

            if meals:
                grouped = {}
                total_cal = 0
                for name, mt, cal in meals:
                    grouped.setdefault(mt, []).append(name)
                    total_cal += cal
                emojis = {"breakfast": "🍳", "lunch": "🍽", "dinner": "", "snack": "🍎"}
                response += f"📆 {date} ({total_cal} ккал)\n"
                for mt, items in grouped.items():
                    response += f"  {emojis.get(mt, '•')} {', '.join(items)}\n\n"
            else:
                response += f"⚪ {date}: нет данных\n\n"

        await send_reply(update, response, [[InlineKeyboardButton("🏠 Главное меню", callback_data="menu_main")]])


# ── /goal ───
async def goal_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    async with async_session() as session:
        db_user = (await session.execute(select(User).where(User.telegram_id == user.id))).scalar_one_or_none()
        if not db_user:
            await send_reply(update, "❌ Сначала нажми /start")
            return

        goal = (await session.execute(select(Goal).where(Goal.user_id == db_user.id))).scalar_one_or_none()
        if not goal:
            goal = Goal(user_id=db_user.id)
            session.add(goal)
            await session.commit()

        response = (
            "🎯 Ваши цели:\n\n"
            f"🔥 Калории: {goal.calories} ккал\n"
            f"🥩 Белки: {goal.protein}г\n"
            f"🥑 Жиры: {goal.fat}г\n"
            f"🍞 Углеводы: {goal.carbs}г\n\n"
            "Чтобы изменить, отправьте:\n"
            "`/setgoal 2000 100 70 250`"
        )
        await send_reply(update, response, [[InlineKeyboardButton(" Главное меню", callback_data="menu_main")]])


# ─── /setgoal ───
async def set_goal_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    try:
        calories, protein, fat, carbs = map(int, context.args)
    except (ValueError, IndexError, TypeError):
        await send_reply(update, "❌ Формат: /setgoal 2000 100 70 250")
        return

    async with async_session() as session:
        db_user = (await session.execute(select(User).where(User.telegram_id == user.id))).scalar_one_or_none()
        if not db_user:
            await send_reply(update, "❌ Сначала нажми /start")
            return
        goal = (await session.execute(select(Goal).where(Goal.user_id == db_user.id))).scalar_one_or_none()
        if not goal:
            goal = Goal(user_id=db_user.id)
            session.add(goal)
        goal.calories, goal.protein, goal.fat, goal.carbs = calories, protein, fat, carbs
        await session.commit()

    await send_reply(
        update,
        f"✅ Цели установлены:\n🔥 {calories} ккал\n🥩 {protein}г\n {fat}г\n🍞 {carbs}г",
        [[InlineKeyboardButton(" Главное меню", callback_data="menu_main")]],
    )


# ─── Обработка кнопок меню ───
async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "menu_stats":
        await stats_command(update, context)
    elif query.data == "menu_history":
        await history_command(update, context)
    elif query.data == "menu_goal":
        await goal_command(update, context)
    elif query.data == "menu_main":
        user = query.from_user
        async with async_session() as session:
            db_user = (await session.execute(select(User).where(User.telegram_id == user.id))).scalar_one_or_none()
            name = db_user.first_name if db_user else "друг"
            await query.edit_message_text(
                f"👋 Привет, {name}!\n\n"
                "Отправь текст или фото блюда, или выбери раздел:",
                reply_markup=get_main_menu_keyboard(),
            )


# ── Обработка ошибок ───
async def error_handler(update: object, context) -> None:
    logger.error(f"Ошибка: {context.error}", exc_info=context.error)


# ─── Запуск ───
async def main():
    await init_db()
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # Обработчик фото (должен быть ДО текстового, чтобы перехватывать фото)
    photo_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.PHOTO, handle_photo)],
        states={
            PHOTO_CONFIRM: [CallbackQueryHandler(photo_meal_type_callback, pattern="^pm_")],
        },
        fallbacks=[],
    )

    # Обработчик текста
    text_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text)],
        states={
            SELECT_MEAL_TYPE: [CallbackQueryHandler(meal_type_callback, pattern="^m_")],
        },
        fallbacks=[],
    )

    app.add_handler(photo_handler)
    app.add_handler(text_handler)
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("history", history_command))
    app.add_handler(CommandHandler("goal", goal_command))
    app.add_handler(CommandHandler("setgoal", set_goal_command))
    app.add_handler(CallbackQueryHandler(menu_callback, pattern="^menu_"))
    app.add_error_handler(error_handler)

    logger.info("Бот запущен!")
    await app.initialize()
    await app.start()
    await app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
    await asyncio.Event().wait()


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
