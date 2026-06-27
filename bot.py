import asyncio
import sys
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ConversationHandler, ContextTypes
from sqlalchemy import select, func, and_
from config import TELEGRAM_TOKEN
from database import init_db, async_session
from models import User, Meal, Goal
from handlers.meal import handle_text, meal_type_callback, SELECT_MEAL_TYPE

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    """Главное меню с кнопками"""
    keyboard = [
        [
            InlineKeyboardButton("📊 Статистика", callback_data="menu_stats"),
            InlineKeyboardButton("📅 История", callback_data="menu_history")
        ],
        [
            InlineKeyboardButton("🎯 Цель", callback_data="menu_goal")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

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

        await update.message.reply_text(
            f"👋 Привет, {user.first_name}!\n\n"
            "Отправь мне:\n"
            "• Текст: `курица 200г, рис 150г`\n"
            "• Несколько продуктов через запятую или с новой строки",
            parse_mode="Markdown",
            reply_markup=get_main_menu_keyboard()
        )

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
            select(func.sum(Meal.calories), func.sum(Meal.protein), func.sum(Meal.fat), func.sum(Meal.carbs))
            .where(and_(Meal.user_id == db_user.id, Meal.date == today))
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
        
        keyboard = [[InlineKeyboardButton("🏠 Главное меню", callback_data="menu_main")]]
        await update.message.reply_text(response, reply_markup=InlineKeyboardMarkup(keyboard))

async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает историю за последние 7 дней"""
    user = update.effective_user
    
    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == user.id))
        db_user = result.scalar_one_or_none()
        if not db_user:
            await update.message.reply_text("❌ Сначала нажми /start")
            return
        
        from datetime import timedelta
        today = datetime.now().date()
        
        response = "📅 История за последние 7 дней:\n\n"
        
        for i in range(6, -1, -1):
            date = (today - timedelta(days=i)).strftime("%Y-%m-%d")
            result = await session.execute(
                select(func.sum(Meal.calories))
                .where(and_(Meal.user_id == db_user.id, Meal.date == date))
            )
            total = result.scalar() or 0
            emoji = "✅" if total > 0 else "⚪"
            response += f"{emoji} {date}: {total} ккал\n"
        
        keyboard = [[InlineKeyboardButton("🏠 Главное меню", callback_data="menu_main")]]
        await update.message.reply_text(response, reply_markup=InlineKeyboardMarkup(keyboard))

async def goal_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает и позволяет изменить цели"""
    user = update.effective_user
    
    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == user.id))
        db_user = result.scalar_one_or_none()
        if not db_user:
            await update.message.reply_text("❌ Сначала нажми /start")
            return
        
        result = await session.execute(select(Goal).where(Goal.user_id == db_user.id))
        goal = result.scalar_one_or_none()
        
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
            "`/setgoal 2000 100 70 250`\n"
            "(калории белки жиры углеводы)"
        )
        
        keyboard = [[InlineKeyboardButton("🏠 Главное меню", callback_data="menu_main")]]
        await update.message.reply_text(response, reply_markup=InlineKeyboardMarkup(keyboard))

async def set_goal_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Устанавливает новые цели"""
    user = update.effective_user
    
    try:
        calories, protein, fat, carbs = map(int, context.args)
        
        async with async_session() as session:
            result = await session.execute(select(User).where(User.telegram_id == user.id))
            db_user = result.scalar_one_or_none()
            if not db_user:
                await update.message.reply_text("❌ Сначала нажми /start")
                return
            
            result = await session.execute(select(Goal).where(Goal.user_id == db_user.id))
            goal = result.scalar_one_or_none()
            
            if not goal:
                goal = Goal(user_id=db_user.id)
                session.add(goal)
            
            goal.calories = calories
            goal.protein = protein
            goal.fat = fat
            goal.carbs = carbs
            await session.commit()
        
        await update.message.reply_text(
            f"✅ Цели установлены:\n"
            f"🔥 {calories} ккал\n"
            f"🥩 {protein}г белков\n"
            f"🥑 {fat}г жиров\n"
            f"🍞 {carbs}г углеводов",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Главное меню", callback_data="menu_main")]])
        )
    except (ValueError, IndexError):
        await update.message.reply_text("❌ Формат: /setgoal 2000 100 70 250")

async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка кнопок главного меню"""
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
            result = await session.execute(select(User).where(User.telegram_id == user.id))
            db_user = result.scalar_one_or_none()
            if db_user:
                await query.edit_message_text(
                    f"👋 Привет, {db_user.first_name}!\n\n"
                    "Отправь продукты или выбери раздел:",
                    reply_markup=get_main_menu_keyboard()
                )

async def error_handler(update: object, context) -> None:
    logger.error(f"Ошибка: {context.error}", exc_info=context.error)

async def main():
    await init_db()
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text)],
        states={SELECT_MEAL_TYPE: [CallbackQueryHandler(meal_type_callback)]},
        fallbacks=[CommandHandler("start", start_command)],
    )

    app.add_handler(conv_handler)
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
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
