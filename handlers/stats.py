from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from sqlalchemy import select, func, and_
from database import async_session
from models import User, Meal, Goal

VIEW_HISTORY = 1

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает статистику за сегодня"""
    user = update.effective_user
    
    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == user.id))
        db_user = result.scalar_one_or_none()
        if not db_user:
            await update.message.reply_text("❌ Сначала нажми /start")
            return
        
        result = await session.execute(select(Goal).where(Goal.user_id == db_user.id))
        goal = result.scalar_one_or_none()
        
        today = datetime.now().strftime("%Y-%m-%d")
        
        result = await session.execute(
            select(
                func.sum(Meal.calories),
                func.sum(Meal.protein),
                func.sum(Meal.fat),
                func.sum(Meal.carbs)
            ).where(
                and_(Meal.user_id == db_user.id, Meal.date == today)
            )
        )
        total = result.first()
        
        calories = total[0] or 0
        protein = total[1] or 0
        fat = total[2] or 0
        carbs = total[3] or 0
        
        goal_calories = goal.calories if goal else 2000
        goal_protein = goal.protein if goal else 100
        goal_fat = goal.fat if goal else 70
        goal_carbs = goal.carbs if goal else 250
        
        cal_percent = round((calories / goal_calories) * 100) if goal_calories else 0
        
        response = (
            f"📊 Статистика за {today}\n\n"
            f"🔥 {calories} / {goal_calories} ккал ({cal_percent}%)\n"
            f"{'█' * (cal_percent // 5)}{'░' * (20 - cal_percent // 5)}\n\n"
            f"🥩 Белки: {protein}/{goal_protein}г\n"
            f"🥑 Жиры: {fat}/{goal_fat}г\n"
            f"🍞 Углеводы: {carbs}/{goal_carbs}г\n\n"
            f"─────────────────\n"
            f"📅 По приемам пищи:\n"
        )
        
        result = await session.execute(
            select(Meal.meal_type, func.sum(Meal.calories))
            .where(and_(Meal.user_id == db_user.id, Meal.date == today))
            .group_by(Meal.meal_type)
        )
        meal_stats = result.all()
        
        meal_types = {"breakfast": "🍳 Завтрак", "lunch": "🍽 Обед", "dinner": "🌙 Ужин", "snack": "🍎 Перекус"}
        for meal_type, meal_calories in meal_stats:
            if meal_type in meal_types:
                response += f"{meal_types[meal_type]}: {meal_calories} ккал\n"
        
        keyboard = [
            [InlineKeyboardButton("📅 Вчера", callback_data="hist_1")],
            [InlineKeyboardButton("📅 Другая дата", callback_data="hist_custom")]
        ]
        
        await update.message.reply_text(response, reply_markup=InlineKeyboardMarkup(keyboard))

async def history_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает статистику за выбранный день"""
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    
    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == user.id))
        db_user = result.scalar_one_or_none()
        if not db_user:
            await query.edit_message_text("❌ Пользователь не найден")
            return
        
        result = await session.execute(select(Goal).where(Goal.user_id == db_user.id))
        goal = result.scalar_one_or_none()
        
        if query.data == "hist_1":
            target_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
            date_label = "вчера"
        else:
            target_date = context.user_data.get('target_date', datetime.now().strftime("%Y-%m-%d"))
            date_label = target_date
        
        result = await session.execute(
            select(
                func.sum(Meal.calories),
                func.sum(Meal.protein),
                func.sum(Meal.fat),
                func.sum(Meal.carbs)
            ).where(
                and_(Meal.user_id == db_user.id, Meal.date == target_date)
            )
        )
        total = result.first()
        
        calories = total[0] or 0
        protein = total[1] or 0
        fat = total[2] or 0
        carbs = total[3] or 0
        
        goal_calories = goal.calories if goal else 2000
        goal_protein = goal.protein if goal else 100
        goal_fat = goal.fat if goal else 70
        goal_carbs = goal.carbs if goal else 250
        
        cal_percent = round((calories / goal_calories) * 100) if goal_calories else 0
        
        response = (
            f"📊 Статистика за {date_label} ({target_date})\n\n"
            f"🔥 {calories} / {goal_calories} ккал ({cal_percent}%)\n"
            f"{'█' * (cal_percent // 5)}{'░' * (20 - cal_percent // 5)}\n\n"
            f"🥩 Белки: {protein}/{goal_protein}г\n"
            f"🥑 Жиры: {fat}/{goal_fat}г\n"
            f"🍞 Углеводы: {carbs}/{goal_carbs}г\n\n"
            f"─────────────────\n"
            f"📅 По приемам пищи:\n"
        )
        
        result = await session.execute(
            select(Meal.meal_type, func.sum(Meal.calories))
            .where(and_(Meal.user_id == db_user.id, Meal.date == target_date))
            .group_by(Meal.meal_type)
        )
        meal_stats = result.all()
        
        meal_types = {"breakfast": "🍳 Завтрак", "lunch": "🍽 Обед", "dinner": "🌙 Ужин", "snack": "🍎 Перекус"}
        for meal_type, meal_calories in meal_stats:
            if meal_type in meal_types:
                response += f"{meal_types[meal_type]}: {meal_calories} ккал\n"
        
        keyboard = [
            [InlineKeyboardButton("⬅️ Назад к сегодня", callback_data="hist_today")],
        ]
        
        await query.edit_message_text(response, reply_markup=InlineKeyboardMarkup(keyboard))

async def back_to_today_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Возврат к сегодняшней статистике"""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Выберите дату:", reply_markup=None)
    await stats_command(update, context)
