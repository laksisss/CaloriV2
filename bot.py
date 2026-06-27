import asyncio
import sys
import os
import logging

import uvicorn
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, CallbackQueryHandler, ConversationHandler
)
from telegram import Update

from config import TELEGRAM_TOKEN
from database import init_db
from handlers.meal import handle_text, meal_type_callback, SELECT_MEAL_TYPE
from handlers.photo import handle_photo, photo_meal_type_callback, PHOTO_CONFIRM
from handlers.start import start_command
from handlers.profile import set_goal, show_goal
from handlers.stats import stats_command
from web_app import app as fastapi_app

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def menu_callback(update: Update, context):
    """Обработка callback-кнопок меню"""
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "stats":
        # Перенаправляем на stats_command с правильным update
        await stats_command(update, context)

    elif data == "goal":
        # Перенаправляем на show_goal с правильным update
        await show_goal(update, context)

    elif data in ("menu", "menu_stats", "menu_main"):
        # Перенаправляем на start_command с правильным update
        await start_command(update, context)

    elif data.startswith("hist_"):
        await query.edit_message_text("📅 История за другие дни доступна в Mini App!")

    elif data.startswith("m_"):
        await meal_type_callback(update, context)

    elif data.startswith("pm_"):
        await photo_meal_type_callback(update, context)


async def error_handler(update: object, context) -> None:
    logger.error(f"Ошибка: {context.error}", exc_info=context.error)


async def run_bot(application):
    """Запуск бота в фоне"""
    logger.info("✅ Бот запущен!")
    await application.updater.start_polling(allowed_updates=Update.ALL_TYPES)
    # Держим бота активным
    while True:
        await asyncio.sleep(1)


async def run_fastapi():
    """Запуск FastAPI сервера"""
    port = int(os.getenv("PORT", 8000))
    config = uvicorn.Config(fastapi_app, host="0.0.0.0", port=port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()


async def main():
    await init_db()

    application = Application.builder().token(TELEGRAM_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text)],
        states={SELECT_MEAL_TYPE: [CallbackQueryHandler(meal_type_callback)]},
        fallbacks=[CommandHandler("start", start_command)],
    )

    photo_conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.PHOTO, handle_photo)],
        states={PHOTO_CONFIRM: [CallbackQueryHandler(photo_meal_type_callback)]},
        fallbacks=[],
    )

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("goal", set_goal))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CallbackQueryHandler(menu_callback))
    application.add_handler(conv_handler)
    application.add_handler(photo_conv_handler)
    application.add_error_handler(error_handler)

    logger.info("🚀 Запуск бота и Mini App...")

    await application.initialize()
    await application.start()

    # Запускаем бота и FastAPI параллельно
    bot_task = asyncio.create_task(run_bot(application))
    fastapi_task = asyncio.create_task(run_fastapi())

    # Ждём завершения любой из задач (если одна упадёт — увидим ошибку)
    done, pending = await asyncio.wait(
        [bot_task, fastapi_task],
        return_when=asyncio.FIRST_COMPLETED
    )

    # Отменяем оставшиеся задачи
    for task in pending:
        task.cancel()

    # Корректное завершение
    await application.updater.stop()
    await application.stop()
    await application.shutdown()


if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
