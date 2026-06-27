from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from sqlalchemy import select
from database import async_session
from models import User, Meal
from ai_service import analyze_photo_meal

# Состояния для ConversationHandler
PHOTO_CONFIRM = 10

MEAL_TYPES = {
    "breakfast": "🍳 Завтрак",
    "lunch": "🍽 Обед",
    "dinner": "🌙 Ужин",
    "snack": "🍎 Перекус"
}


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка отправленного фото еды"""
    user = update.effective_user

    # Проверяем пользователя в БД
    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == user.id))
        db_user = result.scalar_one_or_none()
        if not db_user:
            await update.message.reply_text("❌ Сначала нажми /start")
            return

    # Берём самое большое фото (последнее в списке)
    photo = update.message.photo[-1]
    file_id = photo.file_id

    # Отправляем сообщение "анализирую"
    msg = await update.message.reply_text("🔍 Анализирую фото...")

    # Вызываем AI для анализа
    meal_data = await analyze_photo_meal(file_id)

    if not meal_data:
        await msg.edit_text("❌ Не удалось распознать блюдо. Попробуй отправить фото ещё раз или напиши текст.")
        return

    # Сохраняем данные во временное хранилище
    context.user_data['pending_meal'] = meal_data

    # Показываем результат с кнопками подтверждения
    response = (
        f"🍽 Распознано блюдо:\n\n"
        f"📌 {meal_data['name']}\n"
        f"⚖️ {meal_data['weight']}г\n"
        f" {meal_data['calories']} ккал\n"
        f"🥩 Б: {meal_data['protein']}г | 🥑 Ж: {meal_data['fat']}г | 🍞 У: {meal_data['carbs']}г\n\n"
        f"Выбери приём пищи:"
    )

    keyboard = [
        [InlineKeyboardButton(v, callback_data=f"pm_{k}")]
        for k, v in MEAL_TYPES.items()
    ]
    keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="pm_cancel")])

    await msg.edit_text(response, reply_markup=InlineKeyboardMarkup(keyboard))
    return PHOTO_CONFIRM


async def photo_meal_type_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора типа приёма пищи для фото"""
    query = update.callback_query
    await query.answer()

    action = query.data[3:]  # Убираем префикс "pm_"

    if action == "cancel":
        context.user_data.pop('pending_meal', None)
        await query.edit_message_text("❌ Отменено.", reply_markup=None)
        return None

    meal_type = action
    meal_data = context.user_data.get('pending_meal')

    if not meal_data:
        await query.edit_message_text("❌ Данные устарели. Отправь фото заново.")
        return None

    # Сохраняем в БД
    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == query.from_user.id))
        db_user = result.scalar_one_or_none()
        if not db_user:
            await query.edit_message_text("❌ Пользователь не найден.")
            return None

        today = datetime.now().strftime("%Y-%m-%d")

        meal = Meal(
            user_id=db_user.id,
            date=today,
            name=meal_data["name"],
            weight=meal_data["weight"],
            calories=meal_data["calories"],
            protein=meal_data["protein"],
            fat=meal_data["fat"],
            carbs=meal_data["carbs"],
            meal_type=meal_type
        )
        session.add(meal)
        await session.commit()

    # Очищаем временные данные
    context.user_data.pop('pending_meal', None)

    # Показываем результат с кнопкой возврата в меню
    response = (
        f"✅ Добавлено в {MEAL_TYPES[meal_type]}:\n\n"
        f"📌 {meal_data['name']}\n"
        f"⚖️ {meal_data['weight']}г\n"
        f"🔥 {meal_data['calories']} ккал\n"
        f"🥩 Б: {meal_data['protein']}г | 🥑 Ж: {meal_data['fat']}г |  У: {meal_data['carbs']}г"
    )

    keyboard = [[InlineKeyboardButton("🏠 Главное меню", callback_data="menu_main")]]
    await query.edit_message_text(response, reply_markup=InlineKeyboardMarkup(keyboard))
    return None
