import json
import logging
from typing import List, Dict, Any
from agents.base import BaseAgent

logger = logging.getLogger(__name__)

class ClassifierAgent(BaseAgent):
    def __init__(self, api_key: str = None, base_url: str = None, model: str = None):
        super().__init__("Classifier", api_key, base_url, model)

    async def run(self, transcript: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Классифицирует звонок по тематике и определяет приоритет.
        """
        logger.info("Запуск агента Classifier...")
        
        # Преобразуем транскрипт в плоский текст для анализа
        transcript_text = self._format_transcript(transcript)
        
        system_prompt = (
            "Ты — аналитический агент контакт-центра МТБанка. Твоя задача — классифицировать "
            "обращение клиента на основе транскрипта звонка.\n\n"
            "Доступные тематики (поле 'topic'):\n"
            "- 'кредиты' (кредит наличными, рассрочка, ставки, кредитные карты, досрочное погашение, страховка по кредиту)\n"
            "- 'карты' (дебетовые карты, оформление карт, активация, утеря, комиссии, тарифы)\n"
            "- 'переводы' (денежные переводы, SWIFT, переводы по номеру телефона, с карты на карту, сбои при переводах)\n"
            "- 'жалобы' (претензии к обслуживанию, сбои в работе приложения, несогласие с комиссиями, недовольство оператором)\n"
            "- 'другое' (если обращение не подходит ни под одну из категорий выше)\n\n"
            "Правила определения приоритета (поле 'priority'):\n"
            "- 'high': если это жалоба, сообщение об утере/краже карты, заблокированная транзакция, технический сбой, мешающий клиенту прямо сейчас, или если клиент проявляет агрессию/сильное раздражение.\n"
            "- 'medium': если клиент оставляет заявку на оформление продукта (кредит, карта), просит провести операцию, изменить данные или задает вопросы, требующие точных расчетов.\n"
            "- 'low': если это общий справочный вопрос (режим работы отделений, общие тарифы, адреса банкоматов) без жалоб и оформления заявок.\n\n"
            "Выходной формат строго JSON:\n"
            "{\n"
            "  \"topic\": \"кредиты\" | \"карты\" | \"переводы\" | \"жалобы\" | \"другое\",\n"
            "  \"priority\": \"low\" | \"medium\" | \"high\"\n"
            "}"
        )
        
        user_prompt = f"Транскрипт звонка:\n{transcript_text}"
        
        try:
            response_text = await self._call_llm(system_prompt, user_prompt, temperature=0.0)
            result = json.loads(response_text)
            
            # Валидация значений полей
            topic = result.get("topic", "другое").lower()
            if topic not in ["кредиты", "карты", "переводы", "жалобы", "другое"]:
                topic = "другое"
                
            priority = result.get("priority", "low").lower()
            if priority not in ["low", "medium", "high"]:
                priority = "low"
                
            return {
                "topic": topic,
                "priority": priority
            }
        except Exception as e:
            logger.error(f"Ошибка в агенте Classifier: {e}")
            # Умный fallback на основе ключевых слов в тексте транскрипта
            text_lower = transcript_text.lower()
            topic = "другое"
            priority = "low"
            
            if "кредит" in text_lower or "заем" in text_lower or "ипотек" in text_lower:
                topic = "кредиты"
                priority = "medium"
            elif "карт" in text_lower or "лимит" in text_lower:
                topic = "карты"
                priority = "medium"
            elif "перевод" in text_lower or "трансфер" in text_lower or "отправ" in text_lower:
                topic = "переводы"
                priority = "medium"
            elif "жалоб" in text_lower or "претенз" in text_lower or "ужас" in text_lower or "плох" in text_lower or "недоволен" in text_lower:
                topic = "жалобы"
                priority = "high"
                
            return {
                "topic": topic,
                "priority": priority
            }
        
