from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from sqlalchemy import select
from database import async_session
from models import User, Meal
from utils.parser import find_in_local_db
from ai_service import analyze_text_meal
from config import FREE_DAILY_LIMIT

# Состояние ConversationHandler для выбора типа приема пищи
SELECT_MEAL_TYPE = 1

MEAL_TYPES = {
    "breakfast": "🍳 Завтрак",
    "lunch": "🍽 Обед",
    "dinner": "🌙 Ужин",
    "snack": "🍎 Перекус"
}


def split_food_items(text: str) -> list:
    """Разделяет текст на отдельные продукты по переносам строк и запятым"""
    items = [line.strip() for line in text.split('\n') if line.strip()]
    if len(items) == 1 and ',' in text:
        items = [item.strip() for item in text.split(',') if item.strip()]
    return items


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка текстового сообщения с продуктами.
    Если продуктов несколько — предлагаем выбрать тип приема пищи.
    Если один — сразу обрабатываем и сохраняем.
    """
    user = update.effective_user
    text = update.message.text.strip()

    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == user.id))
        db_user = result.scalar_one_or_none()
        if not db_user:
            await update.message.reply_text("❌ Сначала нажми /start")
            return ConversationHandler.END

        # Сброс счётчика запросов, если день сменился
        today = datetime.now().strftime("%Y-%m-%d")
        if db_user.last_request_date != today:
            db_user.daily_requests = 0
            db_user.last_request_date = today

        # Проверка лимита для бесплатных пользователей
        if not db_user.is_pro and db_user.daily_requests >= FREE_DAILY_LIMIT:
            await update.message.reply_text("⚠️ Лимит 10 запросов/день исчерпан")
            return ConversationHandler.END

        food_items = split_food_items(text)

        # Если продуктов несколько — предлагаем выбрать тип приема пищи
        if len(food_items) > 1:
            context.user_data['pending_food'] = text
            context.user_data['food_count'] = len(food_items)

            keyboard = [
                [InlineKeyboardButton(v, callback_data=f"m_{k}")]
                for k, v in MEAL_TYPES.items()
            ]

            items_text = "\n".join(f"• {item}" for item in food_items)
            await update.message.reply_text(
                f"📝 Найдено продуктов: {len(food_items)}\n\n{items_text}\n\nВыбери приём пищи:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return SELECT_MEAL_TYPE

        # Один продукт — обрабатываем сразу
        await process_single_food(update, session, db_user, today, food_items[0])
        return ConversationHandler.END


async def meal_type_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора типа приема пищи для нескольких продуктов"""
    query = update.callback_query
    await query.answer()

    meal_type = query.data[2:]  # Убираем префикс "m_"
    text = context.user_data.get('pending_food', '')
    if not text:
        await query.edit_message_text("❌ Данные устарели. Напиши продукты заново.")
        return ConversationHandler.END

    food_items = split_food_items(text)
    food_count = context.user_data.get('food_count', len(food_items))

    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == query.from_user.id))
        db_user = result.scalar_one_or_none()
        if not db_user:
            return ConversationHandler.END

        today = datetime.now().strftime("%Y-%m-%d")

        total_calories = 0
        results = []
        errors = []

        for food in food_items:
            # Сначала ищем в локальной БД
            meal_data = find_in_local_db(food)
            # Если не нашли — запрашиваем у AI
            if not meal_data:
                meal_data = await analyze_text_meal(food)

            if meal_data:
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
                total_calories += meal_data["calories"]
                results.append(f"✅ {meal_data['name']} — {meal_data['calories']} ккал")
            else:
                errors.append(f"❌ {food}")

        # Увеличиваем счётчик запросов на количество распознанных продуктов
        db_user.daily_requests += food_count
        await session.commit()

        # Очищаем временные данные
        context.user_data.pop('pending_food', None)
        context.user_data.pop('food_count', None)

        # Формируем ответ
        response = f"✅ Добавлено в {MEAL_TYPES[meal_type]}:\n\n"
        if results:
            response += "\n".join(results)
            response += f"\n\n🔥 Всего: {total_calories} ккал"
        if errors:
            response += "\n\nНе распознано:\n" + "\n".join(errors)

        await query.edit_message_text(response)
        return ConversationHandler.END


async def process_single_food(update, session, db_user, today, text):
    """Обработка одного продукта — парсинг и сохранение в БД"""
    meal_data = find_in_local_db(text)
    if not meal_data:
        msg = await update.message.reply_text(f"🤔 Ищу '{text}' через ИИ...")
        meal_data = await analyze_text_meal(text)
        if not meal_data:
            await msg.edit_text(f"❌ Не удалось распознать '{text}'")
            return
        await msg.delete()

    meal = Meal(
        user_id=db_user.id,
        date=today,
        name=meal_data["name"],
        weight=meal_data["weight"],
        calories=meal_data["calories"],
        protein=meal_data["protein"],
        fat=meal_data["fat"],
        carbs=meal_data["carbs"],
        meal_type="snack"
    )
    session.add(meal)
    db_user.daily_requests += 1
    await session.commit()

    await update.message.reply_text(
        f"✅ {meal_data['name']}\n"
        f"⚖️ {meal_data['weight']}г\n"
        f"🔥 {meal_data['calories']} ккал\n"
        f"🥩 Б: {meal_data['protein']}г | 🥑 Ж: {meal_data['fat']}г | 🍞 У: {meal_data['carbs']}г"
    )
