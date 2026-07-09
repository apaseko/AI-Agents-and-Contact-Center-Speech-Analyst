import json
import logging
from typing import List, Dict, Any
from agents.base import BaseAgent

logger = logging.getLogger(__name__)

class QualityAgent(BaseAgent):
    def __init__(self, api_key: str = None, base_url: str = None, model: str = None):
        super().__init__("QualityAgent", api_key, base_url, model)

    async def run(self, transcript: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Оценивает качество работы оператора по чек-листу.
        """
        logger.info("Запуск агента QualityAgent...")
        
        transcript_text = self._format_transcript(transcript)
        
        system_prompt = (
            "Ты — аудитор качества обслуживания МТБанка. Твоя задача — проверить соблюдение "
            "оператором стандартов обслуживания клиентов по чек-листу.\n\n"
            "Критерии чек-листа:\n"
            "1. 'greeting' (Приветствие): Поприветствовал ли оператор клиента в начале разговора и представился ли? "
            "(Например: 'Добрый день, МТБанк, меня зовут Анна...'). Должно быть вежливое приветствие банка и имени.\n"
            "2. 'need_detection' (Выявление потребности): Задавал ли оператор уточняющие вопросы для понимания "
            "сути обращения клиента? (Например: спросил о сумме и сроке кредита, статусе клиента и т.д.).\n"
            "3. 'solution_provided' (Предоставление решения): Дал ли оператор четкий, понятный и полезный ответ на вопрос "
            "клиента? Объяснил ли условия, рассказал ли про досрочное погашение, страховку или другие детали?\n"
            "4. 'farewell' (Вежливое прощание): Вежливо ли попрощался оператор с клиентом в конце разговора, "
            "поблагодарил ли за обращение? (Например: 'Спасибо за обращение в МТБанк, хорошего дня!').\n\n"
            "Выходной формат строго JSON:\n"
            "{\n"
            "  \"greeting\": true | false,\n"
            "  \"need_detection\": true | false,\n"
            "  \"solution_provided\": true | false,\n"
            "  \"farewell\": true | false\n"
            "}"
        )
        
        user_prompt = f"Транскрипт звонка:\n{transcript_text}"
        
        try:
            response_text = await self._call_llm(system_prompt, user_prompt, temperature=0.0)
            checklist = json.loads(response_text)
            
            # Валидация булевых значений
            greeting = bool(checklist.get("greeting", False))
            need_detection = bool(checklist.get("need_detection", False))
            solution_provided = bool(checklist.get("solution_provided", False))
            farewell = bool(checklist.get("farewell", False))
            
            # Расчет итогового балла
            # Веса: приветствие (15), выявление потребности (35), решение (35), прощание (15)
            total_score = 0
            if greeting:
                total_score += 15
            if need_detection:
                total_score += 35
            if solution_provided:
                total_score += 35
            if farewell:
                total_score += 15
                
            return {
                "total": total_score,
                "checklist": {
                    "greeting": greeting,
                    "need_detection": need_detection,
                    "solution_provided": solution_provided,
                    "farewell": farewell
                }
            }
            
        except Exception as e:
            logger.error(f"Ошибка в агенте QualityAgent: {e}")
            # Умный fallback на основе ключевых слов в тексте транскрипта
            text_lower = transcript_text.lower()
            
            # Приветствие
            greeting = any(word in text_lower for word in ["здравствуйте", "добрый день", "доброе утро", "приветствую", "мтбанк", "меня зовут"])
            
            # Выявление потребности
            need_detection = any(word in text_lower for word in ["чем могу", "что вас", "какой вопрос", "какие условия", "уточните", "подскажите", "цель", "сумма", "срок"])
            
            # Предоставление решения
            solution_provided = any(word in text_lower for word in ["оформить", "карта", "кредит", "перевести", "сделать", "процент", "ставка", "условия", "решение"])
            
            # Прощание
            farewell = any(word in text_lower for word in ["до свидания", "всего доброго", "хорошего дня", "всего хорошего", "до встречи", "спасибо за звонок"])
            
            # Расчет итогового балла
            total_score = 0
            if greeting:
                total_score += 15
            if need_detection:
                total_score += 35
            if solution_provided:
                total_score += 35
            if farewell:
                total_score += 15
                
            return {
                "total": total_score,
                "checklist": {
                    "greeting": greeting,
                    "need_detection": need_detection,
                    "solution_provided": solution_provided,
                    "farewell": farewell
                }
            }
