import asyncio
import sys
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ConversationHandler, ContextTypes
from config import TELEGRAM_TOKEN
from database import init_db
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
    from database import async_session
    from models import User, Goal
    from sqlalchemy import select

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

async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка кнопок главного меню"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "menu_stats":
        from handlers.stats import stats_command
        await stats_command(update, context)
    elif query.data == "menu_history":
        await query.edit_message_text(" История по дням - используй /history")
    elif query.data == "menu_goal":
        await query.edit_message_text(" Цель - используй /goal для настройки")

async def error_handler(update: object, context) -> None:
    logger.error(f"Ошибка: {context.error}", exc_info=context.error)

async def main():
    await init_db()
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text),
        ],
        states={
            SELECT_MEAL_TYPE: [CallbackQueryHandler(meal_type_callback)],
        },
        fallbacks=[
            CommandHandler("start", start_command),
        ],
    )

    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("start", start_command))
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
