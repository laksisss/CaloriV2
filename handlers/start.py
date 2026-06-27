from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from sqlalchemy import select
from database import async_session
from models import User, Goal

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
    
    keyboard = [
        [InlineKeyboardButton("📊 Статистика", callback_data="stats")],
        [InlineKeyboardButton("🎯 Цель", callback_data="goal")],
    ]
    await update.message.reply_text(
        f"👋 Привет, {user.first_name}!\n\n"
        "Я помогу отслеживать питание.\n\n"
        "📝 Отправь мне:\n"
        "• Текст: `курица 200г, рис 150г`\n"
        "• Несколько продуктов через запятую или с новой строки\n"
        "• Я предложу выбрать приём пищи\n\n"
        "🆓 10 запросов/день бесплатно",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )