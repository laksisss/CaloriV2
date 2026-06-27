import json
import base64
import logging
from config import GROQ_API_KEY, TELEGRAM_TOKEN

logger = logging.getLogger(__name__)


def _get_client():
    """Создаёт Groq-клиент только когда нужен (lazy init)"""
    from groq import AsyncGroq
    return AsyncGroq(api_key=GROQ_API_KEY)


async def analyze_text_meal(text: str) -> dict | None:
    """Анализ текста через Groq Llama 3.3"""
    prompt = f"""Ты эксперт по питанию. Проанализируй описание еды и верни ТОЛЬКО JSON без пояснений.

Описание: {text}

Верни JSON в формате:
{{"name": "название блюда", "weight": 100, "calories": 250, "protein": 15, "fat": 8, "carbs": 30}}

Если несколько продуктов - верни массив объектов."""

    try:
        client = _get_client()
        response = await client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "Отвечай только валидным JSON без markdown."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=500
        )

        text_response = response.choices[0].message.content.strip()

        if text_response.startswith("```"):
            text_response = text_response.split("```")[1]
            if text_response.startswith("json"):
                text_response = text_response[4:]
            text_response = text_response.strip()

        if '[' in text_response:
            start = text_response.find('[')
            end = text_response.rfind(']') + 1
        else:
            start = text_response.find('{')
            end = text_response.rfind('}') + 1

        if start != -1 and end != 0:
            data = json.loads(text_response[start:end])
            if isinstance(data, list):
                return data[0] if data else None
            return data
    except Exception as e:
        logger.error(f"Groq error: {e}")

    return None


async def analyze_photo_meal(photo_file_id: str) -> dict | None:
    """Анализ фото через Groq Vision"""
    from telegram import Bot

    try:
        bot = Bot(token=TELEGRAM_TOKEN)
        file = await bot.get_file(photo_file_id)
        photo_bytes = await file.download_as_bytearray()
        photo_base64 = base64.b64encode(photo_bytes).decode('utf-8')

        client = _get_client()
        response = await client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "Проанализируй фото еды. Определи:\n"
                                "1. Название блюда\n"
                                "2. Примерный вес в граммах\n"
                                "3. Калории (всего, не на 100г)\n"
                                "4. БЖУ (белки, жиры, углеводы - всего)\n\n"
                                "Отвечай ТОЛЬКО в формате JSON:\n"
                                '{"name": "блюдо", "weight": 200, "calories": 300, "protein": 24, "fat": 10, "carbs": 36}'
                            )
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{photo_base64}"
                            }
                        }
                    ]
                }
            ],
            max_tokens=500,
            temperature=0.3
        )

        result = response.choices[0].message.content.strip()

        if "```json" in result:
            result = result.split("```json")[1].split("```")[0].strip()
        elif "```" in result:
            result = result.split("```")[1].split("```")[0].strip()

        data = json.loads(result)

        return {
            "name": data.get("name", "Блюдо"),
            "weight": data.get("weight", 100),
            "calories": data.get("calories", 0),
            "protein": data.get("protein", 0),
            "fat": data.get("fat", 0),
            "carbs": data.get("carbs", 0)
        }

    except Exception as e:
        logger.error(f"Ошибка анализа фото: {e}")
        return None
