import os
from groq import AsyncGroq
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

client = AsyncGroq(api_key=GROQ_API_KEY)

async def analyze_text_meal(text: str) -> dict | None:
    """
    Анализирует текст и определяет тип приема пищи
    """
    try:
        completion = await client.chat.completions.create(
            model="llama-3.1-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": """Ты эксперт по питанию. Определи тип приема пищи по описанию.
Возможные типы:
- breakfast (завтрак)
- lunch (обед) 
- dinner (ужин)
- snack (перекус)

Отвечай ТОЛЬКО названием типа на английском языке, без дополнительных объяснений."""
                },
                {
                    "role": "user",
                    "content": f"Определи тип приема пищи: {text}"
                }
            ],
            temperature=0.3,
            max_tokens=50
        )
        
        meal_type = completion.choices[0].message.content.strip().lower()
        
        # Проверяем, что вернули правильный тип
        valid_types = ['breakfast', 'lunch', 'dinner', 'snack']
        if meal_type in valid_types:
            return {"type": meal_type, "description": text}
        else:
            # Пытаемся найти тип в ответе
            for valid_type in valid_types:
                if valid_type in meal_type:
                    return {"type": valid_type, "description": text}
            return None
            
    except Exception as e:
        print(f"Error analyzing text: {e}")
        return None


async def analyze_photo_meal(photo_file_id: str) -> dict | None:
    """
    Анализирует фото еды и определяет тип приема пищи
    """
    try:
        completion = await client.chat.completions.create(
            model="llama-3.2-90b-vision-preview",
            messages=[
                {
                    "role": "system",
                    "content": """Ты эксперт по питанию. Определи тип приема пищи по фотографии.
Возможные типы:
- breakfast (завтрак)
- lunch (обед)
- dinner (ужин)
- snack (перекус)

Отвечай ТОЛЬКО названием типа на английском языке, без дополнительных объяснений."""
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Определи тип этого приема пищи"
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"https://api.telegram.org/file/bot{os.getenv('BOT_TOKEN')}/{photo_file_id}"
                            }
                        }
                    ]
                }
            ],
            temperature=0.3,
            max_tokens=50
        )
        
        meal_type = completion.choices[0].message.content.strip().lower()
        
        # Проверяем, что вернули правильный тип
        valid_types = ['breakfast', 'lunch', 'dinner', 'snack']
        if meal_type in valid_types:
            return {"type": meal_type, "description": "Photo analysis"}
        else:
            # Пытаемся найти тип в ответе
            for valid_type in valid_types:
                if valid_type in meal_type:
                    return {"type": valid_type, "description": "Photo analysis"}
            return None
            
    except Exception as e:
        print(f"Error analyzing photo: {e}")
        return None
