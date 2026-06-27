from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from ai_service import analyze_text_meal  # ваш AI сервис

# Короткие коды для callback_data
MEAL_TYPE_CODES = {
    "mt_brkfst": "Завтрак",
    "mt_lunch": "Обед", 
    "mt_dinner": "Ужин",
    "mt_snack": "Перекус",
}

async def add_food(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начало добавления пищи - показываем выбор типа приема пищи"""
    keyboard = [
        [
            InlineKeyboardButton("🍳 Завтрак", callback_data="mt_brkfst"),
            InlineKeyboardButton("🍲 Обед", callback_data="mt_lunch"),
        ],
        [
            InlineKeyboardButton("🥗 Ужин", callback_data="mt_dinner"),
            InlineKeyboardButton("🍎 Перекус", callback_data="mt_snack"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Выберите тип приема пищи:",
        reply_markup=reply_markup
    )
    return SELECT_MEAL_TYPE

async def select_meal_type_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка выбора типа приема пищи"""
    query = update.callback_query
    await query.answer()
    
    meal_code = query.data
    meal_type = MEAL_TYPE_CODES.get(meal_code, "Неизвестно")
    context.user_data['meal_type'] = meal_type
    
    await query.edit_message_text(
        f"Выбрано: {meal_type}\n\n"
        "Отправьте текст о продуктах (или фото для парсинга):"
    )
    return ADD_FOOD

async def process_food_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка текста с продуктами"""
    text = update.message.text
    meal_type = context.user_data.get('meal_type', 'Не указано')
    
    try:
        # Парсинг через AI
        meal_data = await analyze_text_meal(text)
        
        # Сохраняем данные
        context.user_data['parsed_meal'] = meal_data
        
        # Показываем для подтверждения
        await update.message.reply_text(
            f"📝 Распознано:\n\n"
            f"Тип: {meal_type}\n"
            f"Продукты: {meal_data.get('products', 'Не распознано')}\n"
            f"Калории: {meal_data.get('calories', '?')} ккал\n\n"
            "Подтвердить запись?"
        )
        
        return CONFIRM_ENTRY
        
    except Exception as e:
        await update.message.reply_text(f"Ошибка при парсинге: {e}")
        return ADD_FOOD

async def confirm_entry_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Подтверждение записи"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "confirm_yes":
        # Сохраняем в базу данных
        meal_data = context.user_data.get('parsed_meal', {})
        # TODO: добавить сохранение в БД
        
        await query.edit_message_text("✅ Запись добавлена!")
    else:
        await query.edit_message_text("❌ Отменено")
    
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отмена"""
    await update.message.reply_text("Отменено.")
    return ConversationHandler.END
