from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from sqlalchemy import select, func
from database import async_session
from models import User, Meal, Goal

MEAL_TYPE_NAMES = {
    "breakfast": "🌅 Завтрак",
    "lunch": "🍽 Обед",
    "dinner": "🌙 Ужин",
    "snack": "🍎 Перекус",
    None: "❓ Без категории"
}

async def stats_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    today = datetime.now().strftime("%Y-%m-%d")
    
    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == user.id))
        db_user = result.scalar_one_or_none()
        
        if not db_user:
            text = "❌ Сначала нажми /start"
        else:
            result = await session.execute(select(Goal).where(Goal.user_id == db_user.id))
            goal = result.scalar_one_or_none()
            if not goal:
                goal = Goal(user_id=db_user.id)
                session.add(goal)
                await session.commit()
            
            # Общая статистика
            result = await session.execute(
                select(func.sum(Meal.calories), func.sum(Meal.protein),
                       func.sum(Meal.fat), func.sum(Meal.carbs))
                .where(Meal.user_id == db_user.id, Meal.date == today)
            )
            totals = result.one()
            total_calories = totals[0] or 0
            total_protein = totals[1] or 0
            total_fat = totals[2] or 0
            total_carbs = totals[3] or 0
            
            # ⭐ Разбивка по приемам пищи
            result = await session.execute(
                select(Meal.meal_type, func.sum(Meal.calories))
                .where(Meal.user_id == db_user.id, Meal.date == today)
                .group_by(Meal.meal_type)
            )
            meal_stats = result.all()
            
            progress = min(100, int((total_calories / goal.calories) * 100)) if goal.calories else 0
            bar = '█' * (progress // 10) + '░' * (10 - progress // 10)
            
            text = f"📊 **Статистика за {today}**\n\n"
            text += f"🔥 **{total_calories:.0f}** / {goal.calories:.0f} ккал ({progress}%)\n"
            text += f"{bar}\n\n"
            text += f"🥩 Белки: {total_protein:.0f}/{goal.protein:.0f}г\n"
            text += f"🥑 Жиры: {total_fat:.0f}/{goal.fat:.0f}г\n"
            text += f"🍞 Углеводы: {total_carbs:.0f}/{goal.carbs:.0f}г\n"
            
            # ⭐ Детализация по приемам пищи
            if meal_stats:
                text += "\n━━━━━━━━━━━━━━━\n**📋 По приемам пищи:**\n\n"
                order = ["breakfast", "lunch", "dinner", "snack", None]
                for meal_type in order:
                    for stat in meal_stats:
                        if stat[0] == meal_type:
                            name = MEAL_TYPE_NAMES.get(meal_type, "❓")
                            cal = stat[1] or 0
                            text += f"{name}: **{cal:.0f}** ккал\n"
    
    # ⭐ Кнопка возврата в главное меню
    keyboard = [
        [InlineKeyboardButton("🏠 Главное меню", callback_data="menu")]
    ]
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown"
        )