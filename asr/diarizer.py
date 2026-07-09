import os
import json
import logging
from typing import List, Dict, Any
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

class LLMDiarizer:
    def __init__(self, api_key: str = None, base_url: str = None, model: str = None):
        """
        Инициализация диаризатора на базе LLM.
        """
        self.api_key = api_key or os.environ.get("LLM_API_KEY", "")
        self.base_url = base_url or os.environ.get("LLM_BASE_URL", "https://api.groq.com/openai/v1")
        self.model = model or os.environ.get("LLM_MODEL", "llama-3.3-70b-versatile")
        
        # Инициализируем клиент OpenAI
        # Если ключ не задан, клиент всё равно создастся, но упадет при вызове (что логично)
        self.client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )

    async def diarize(self, segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Выполняет разметку спикеров (Оператор / Клиент) для списка сегментов ASR.
        """
        if not segments:
            return []

        logger.info(f"Запуск LLM-диаризации для {len(segments)} сегментов...")

        # Превращаем сегменты в компактный формат для отправки в LLM
        formatted_input = []
        for i, seg in enumerate(segments):
            formatted_input.append({
                "id": i,
                "start": seg["start"],
                "end": seg["end"],
                "text": seg["text"]
            })

        prompt = (
            "Ты — профессиональный аналитик контакт-центра МТБанка. Тебе предоставлен текстовый транскрипт "
            "звонка с временными метками. Твоя задача — классифицировать спикера для каждого сегмента речи. "
            "Доступные роли спикеров:\n"
            "1. 'Оператор' (сотрудник МТБанка, который консультирует, приветствует клиента, предлагает продукты, прощается)\n"
            "2. 'Клиент' (человек, обратившийся в банк с вопросом, отвечающий на вопросы оператора)\n\n"
            "Правила классификации:\n"
            "- Анализируй контекст разговора, вежливость фраз, вопросы и ответы, чтобы понять, кто говорит.\n"
            "- Сохраняй исходную структуру сегментов (id, start, end, text) в неизменном виде. Изменять текст фраз ЗАПРЕЩЕНО.\n"
            "- Добавь поле 'speaker' (значения: 'Оператор' или 'Клиент') для каждого сегмента.\n\n"
            "Входные сегменты:\n"
            f"{json.dumps(formatted_input, ensure_ascii=False, indent=2)}\n\n"
            "Верни ответ строго в формате JSON, соответствующем следующей JSON-схеме:\n"
            "{\n"
            "  \"transcript\": [\n"
            "    {\n"
            "      \"speaker\": \"Оператор\" или \"Клиент\",\n"
            "      \"start\": число (start),\n"
            "      \"end\": число (end),\n"
            "      \"text\": \"строка (оригинальный текст сегмента)\"\n"
            "    }\n"
            "  ]\n"
            "}"
        )

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "Ты полезный AI-ассистент, который всегда возвращает корректный JSON по схеме."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.0, # Минимизируем креативность для стабильности структуры
                timeout=30.0
            )

            response_text = response.choices[0].message.content
            logger.info("Успешный ответ от LLM для диаризации.")
            
            result_json = json.loads(response_text)
            diarized_transcript = result_json.get("transcript", [])
            
            # Простая валидация, чтобы убедиться, что число сегментов совпадает с оригинальным
            # Если LLM пропустила сегменты, восстанавливаем исходный список с ролями по умолчанию
            if len(diarized_transcript) != len(segments):
                logger.warning(
                    f"Количество сегментов после диаризации ({len(diarized_transcript)}) "
                    f"не совпадает с оригинальным ({len(segments)}). Производится сопоставление по тексту/таймингам."
                )
                
                # Попробуем сопоставить или просто проставим роли по умолчанию
                new_diarized = []
                for i, orig_seg in enumerate(segments):
                    # Попытка найти по индексу
                    if i < len(diarized_transcript) and diarized_transcript[i].get("text") == orig_seg["text"]:
                        speaker = diarized_transcript[i].get("speaker", "Клиент")
                    else:
                        # Поиск по тексту в результатах LLM
                        speaker = "Клиент" # Роль по умолчанию
                        for diar_seg in diarized_transcript:
                            if diar_seg.get("text") == orig_seg["text"]:
                                speaker = diar_seg.get("speaker", "Клиент")
                                break
                    
                    new_diarized.append({
                        "speaker": speaker,
                        "start": orig_seg["start"],
                        "end": orig_seg["end"],
                        "text": orig_seg["text"]
                    })
                return new_diarized

            # Приведем к финальному виду
            final_transcript = []
            for item in diarized_transcript:
                final_transcript.append({
                    "speaker": item.get("speaker", "Клиент") if item.get("speaker") in ["Оператор", "Клиент"] else "Клиент",
                    "start": item.get("start"),
                    "end": item.get("end"),
                    "text": item.get("text")
                })
            
            return final_transcript

        except Exception as e:
            logger.error(f"Ошибка во время LLM-диаризации: {e}")
            # В случае ошибки возвращаем исходный транскрипт с дефолтными ролями (например, попеременно или все Клиент)
            # Чтобы система не ломалась полностью
            fallback_transcript = []
            for i, seg in enumerate(segments):
                # Наверняка первая реплика обычно за Оператором (приветствие)
                speaker = "Оператор" if i % 2 == 0 else "Клиент"
                fallback_transcript.append({
                    "speaker": speaker,
                    "start": seg["start"],
                    "end": seg["end"],
                    "text": seg["text"]
                })
            return fallback_transcript
