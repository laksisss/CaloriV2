from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from sqlalchemy import select
from database import async_session
from models import User, Meal
from utils.parser import find_in_local_db
from ai_service import analyze_text_meal

SELECT_MEAL_TYPE = 1

MEAL_TYPES = {
    "breakfast": "🍳 Завтрак",
    "lunch": "🍽 Обед",
    "dinner": "🌙 Ужин",
    "snack": "🍎 Перекус"
}

def get_back_to_menu_button() -> InlineKeyboardMarkup:
    """Кнопка возврата в главное меню"""
    keyboard = [[InlineKeyboardButton("🏠 Главное меню", callback_data="menu_main")]]
    return InlineKeyboardMarkup(keyboard)

def split_food_items(text: str) -> list:
    items = [line.strip() for line in text.split('\n') if line.strip()]
    if len(items) == 1 and ',' in text:
        items = [item.strip() for item in text.split(',') if item.strip()]
    return items

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text.strip()

    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == user.id))
        db_user = result.scalar_one_or_none()
        if not db_user:
            await update.message.reply_text("❌ Сначала нажми /start")
            return ConversationHandler.END

        food_items = split_food_items(text)

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

        await process_single_food(update, session, db_user, datetime.now().strftime("%Y-%m-%d"), food_items[0])
        return ConversationHandler.END

async def meal_type_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    meal_type = query.data[2:]
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
            meal_data = find_in_local_db(food)
            if not meal_data:
                meal_data = await analyze_text_meal(food)

            if meal_data:
                meal = Meal(
                    user_id=db_user.id, date=today, name=meal_data["name"],
                    weight=meal_data["weight"], calories=meal_data["calories"],
                    protein=meal_data["protein"], fat=meal_data["fat"],
                    carbs=meal_data["carbs"], meal_type=meal_type
                )
                session.add(meal)
                total_calories += meal_data["calories"]
                results.append(f"✅ {meal_data['name']} — {meal_data['calories']} ккал")
            else:
                errors.append(f"❌ {food}")

        db_user.daily_requests += food_count
        await session.commit()

        context.user_data.pop('pending_food', None)
        context.user_data.pop('food_count', None)

        response = f"✅ Добавлено в {MEAL_TYPES[meal_type]}:\n\n"
        if results:
            response += "\n".join(results)
            response += f"\n\n🔥 Всего: {total_calories} ккал"
        if errors:
            response += "\n\nНе распознано:\n" + "\n".join(errors)

        await query.edit_message_text(response, reply_markup=get_back_to_menu_button())
        return ConversationHandler.END

async def process_single_food(update, session, db_user, today, text):
    meal_data = find_in_local_db(text)
    if not meal_data:
        msg = await update.message.reply_text(f"🤔 Ищу '{text}' через ИИ...")
        meal_data = await analyze_text_meal(text)
        if not meal_data:
            await msg.edit_text(f"❌ Не удалось распознать '{text}'")
            return
        await msg.delete()

    meal = Meal(
        user_id=db_user.id, date=today, name=meal_data["name"],
        weight=meal_data["weight"], calories=meal_data["calories"],
        protein=meal_data["protein"], fat=meal_data["fat"],
        carbs=meal_data["carbs"], meal_type="snack"
    )
    session.add(meal)
    db_user.daily_requests += 1
    await session.commit()

    await update.message.reply_text(
        f"✅ {meal_data['name']}\n"
        f"⚖️ {meal_data['weight']}г\n"
        f"🔥 {meal_data['calories']} ккал\n"
        f"🥩 Б: {meal_data['protein']}г | 🥑 Ж: {meal_data['fat']}г | 🍞 У: {meal_data['carbs']}г",
        reply_markup=get_back_to_menu_button()
    )
