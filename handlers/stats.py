from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from sqlalchemy import select, func
from datetime import datetime, timedelta
from database import async_session
from models import User, Meal, Goal


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == user.id)
        )
        db_user = result.scalar_one_or_none()
        
        if not db_user:
            response = "❌ Пользователь не найден. Отправь /start"
            # Универсальная отправка
            if update.callback_query:
                await update.callback_query.edit_message_text(response)
            else:
                await update.message.reply_text(response)
            return

        # Статистика за сегодня
        today = datetime.now().strftime("%Y-%m-%d")
        result = await session.execute(
            select(
                func.sum(Meal.calories),
                func.sum(Meal.protein),
                func.sum(Meal.fat),
                func.sum(Meal.carbs),
            ).where((Meal.user_id == db_user.id) & (Meal.date == today))
        )
        today_stats = result.first()

        # Цель
        result = await session.execute(
            select(Goal).where(Goal.user_id == db_user.id)
        )
        goal = result.scalar_one_or_none()

        # Формируем ответ
        calories = today_stats[0] or 0
        protein = today_stats[1] or 0
        fat = today_stats[2] or 0
        carbs = today_stats[3] or 0

        response = (
            f"📊 *Статистика за сегодня*\n\n"
            f"🔥 Калории: {calories} ккал"
        )
        
        if goal:
            response += f" / {goal.calories}\n"
            response += f"🥩 Белки: {protein}г / {goal.protein}г\n"
            response += f"🥑 Жиры: {fat}г / {goal.fat}г\n"
            f"🍞 Углеводы: {carbs}г / {goal.carbs}г\n"
        else:
            response += "\n"
            response += f"🥩 Белки: {protein}г\n"
            response += f"🥑 Жиры: {fat}г\n"
            response += f"🍞 Углеводы: {carbs}г\n"

        keyboard = [
            [InlineKeyboardButton("🏠 Главное меню", callback_data="menu")],
        ]

        # Универсальная отправка - работает и для callback, и для обычного сообщения
        if update.callback_query:
            await update.callback_query.edit_message_text(
                response,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(
                response,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )
