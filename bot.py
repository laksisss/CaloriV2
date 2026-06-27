import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, ConversationHandler, MessageHandler, filters
from sqlalchemy import select, func, and_
from database import init_db, async_session
from handlers.meal import handle_text, meal_type_callback, SELECT_MEAL_TYPE

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

SELECT_GOAL = 1
SELECT_HISTORY = 2
SELECT_STATS = 3

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('Добро пожаловать! Выберите действие:')

async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == 'stats':
        await stats_command(update, context)
    elif query.data == 'history':
        await history_command(update, context)
    elif query.data == 'goal':
        await goal_command(update, context)

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🔙 Назад", callback_data='menu')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    async with async_session() as session:
        total_meals = await session.execute(select(func.count()).select_from(...))
        response = f"Всего записей: {total_meals.scalar()}"
    
    if hasattr(update, 'message') and update.message:
        await update.message.reply_text(response, reply_markup=reply_markup)
    elif hasattr(update, 'callback_query') and update.callback_query:
        await update.callback_query.message.reply_text(response, reply_markup=reply_markup)

async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🔙 Назад", callback_data='menu')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    response = "История питания..."
    
    if hasattr(update, 'message') and update.message:
        await update.message.reply_text(response, reply_markup=reply_markup)
    elif hasattr(update, 'callback_query') and update.callback_query:
        await update.callback_query.message.reply_text(response, reply_markup=reply_markup)

async def goal_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🔙 Назад", callback_data='menu')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    response = "Ваши цели..."
    
    if hasattr(update, 'message') and update.message:
        await update.message.reply_text(response, reply_markup=reply_markup)
    elif hasattr(update, 'callback_query') and update.callback_query:
        await update.callback_query.message.reply_text(response, reply_markup=reply_markup)

def main():
    application = Application.builder().token("8870574029:AAEZMMO84mDhG9dywNYIRxdo3DLfl0ztF5I").build()
    
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CallbackQueryHandler(menu_callback))
    
    logger.info("Бот запущен!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
