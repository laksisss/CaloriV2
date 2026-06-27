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


def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📊 Статистика", callback_data="menu_stats"),
            InlineKeyboardButton("📅 История", callback_data="menu_history"),
        ],
        [InlineKeyboardButton("🎯 Цель", callback_data="menu_goal")],
    ])


async def send_reply(update: Update, text: str, keyboard=None):
    reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
        except Exception:
            await update.callback_query.message.reply_text(text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, reply_markup=reply_markup)


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
            "• Фото блюда — распознаю автоматически",
            [
                [
                    InlineKeyboardButton("📊 Статистика", callback_data="menu_stats"),
                    InlineKeyboardButton("📅 История", callback_data="menu_history"),
                ],
                [InlineKeyboardButton("🎯 Цель", callback_data="menu_goal")],
            ],
        )


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
            f"🥩 Белки: {protein}/{goal_p}г\n"
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

        meal_types = {"breakfast": "🍳 Завтрак", "lunch": "🍽 Обед", "dinner": "🌙 Ужин", "snack": "🍎 Перекус"}
        for mt, mc in meal_stats:
            if mt in meal_types:
                response += f"{meal_types[mt]}: {mc} ккал\n"

        await send_reply(update, response, [[InlineKeyboardButton("🏠 Главное меню", callback_data="menu_main")]])


async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    async with async_session() as session:
        db_user = (await session.execute(select(User).where(User.telegram_id == user.id))).scalar_one_or_none()
        if not db_user:
            await send_reply(update, "❌ Сначала нажми /start")
            return

        today = datetime.now().date()
        response = "📅 История за последние 7 дней:\n\n"

        for i in range(6, -1, -1):
            date = (today - timedelta(days=i)).strftime("%Y-%m-%d")
            meals = (await session.execute(
                select(Meal.name, Meal.meal_type, Meal.calories)
                .where(and_(Meal.user_id == db_user.id, Meal.date == date))
               
