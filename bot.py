import asyncio
import sys
import logging
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ConversationHandler
from telegram import Update
from config import TELEGRAM_TOKEN
from database import init_db
from handlers.meal import handle_text, meal_type_callback, SELECT_MEAL_TYPE
from handlers.stats import stats_command, history_callback, back_to_today_callback, VIEW_HISTORY

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
            "• Несколько продуктов через запятую или с новой строки\n\n"
            "Команды:\n"
            "/stats - статистика за сегодня\n"
            "/history - история по дням",
            parse_mode="Markdown"
        )

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
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CallbackQueryHandler(history_callback, pattern="^hist_"))
    app.add_handler(CallbackQueryHandler(back_to_today_callback, pattern="^hist_today$"))
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
