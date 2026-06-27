from groq import AsyncGroq
import json
from config import GROQ_API_KEY

# Асинхронный клиент - не блокирует бота!
client = AsyncGroq(api_key=GROQ_API_KEY)

async def analyze_text_meal(text: str):
    """Анализ текста через Groq Llama 3.3 (бесплатно)"""
    prompt = f"""Ты эксперт по питанию. Проанализируй описание еды и верни ТОЛЬКО JSON без пояснений.

Описание: {text}

Верни JSON в формате:
{{"name": "название блюда", "weight": 100, "calories": 250, "protein": 15, "fat": 8, "carbs": 30}}

Если несколько продуктов - верни массив объектов."""
    
    try:
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
        
        # Убираем markdown обёртки если есть
        if text_response.startswith("```"):
            text_response = text_response.split("```")[1]
            if text_response.startswith("json"):
                text_response = text_response[4:]
            text_response = text_response.strip()
        
        # Извлекаем JSON
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
        print(f"Groq error: {e}")
    
    return None
