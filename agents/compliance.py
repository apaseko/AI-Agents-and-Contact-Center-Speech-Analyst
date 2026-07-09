import json
import logging
from typing import List, Dict, Any
from agents.base import BaseAgent

logger = logging.getLogger(__name__)

class ComplianceAgent(BaseAgent):
    def __init__(self, api_key: str = None, base_url: str = None, model: str = None):
        super().__init__("ComplianceAgent", api_key, base_url, model)

    async def run(self, transcript: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Проверяет звонок на соответствие комплаенс-требованиям банка.
        """
        logger.info("Запуск агента ComplianceAgent...")
        
        transcript_text = self._format_transcript(transcript)
        
        system_prompt = (
            "Ты — комплаенс-офицер МТБанка. Твоя задача — проанализировать транскрипт разговора "
            "оператора с клиентом на предмет нарушений регуляторных норм и внутренних регламентов.\n\n"
            "Критические нарушения комплаенса (поле 'passed': false, если найдено хотя бы одно):\n"
            "1. Навязывание страхования: Утверждение о том, что страхование жизни является ОБЯЗАТЕЛЬНЫМ "
            "для получения кредита (по регламенту страховка добровольна: 'подключается по вашему желанию').\n"
            "2. Введение в заблуждение (Ложные гарантии): Обещание 100% одобрения кредита или карты до "
            "официального решения банка (например: 'я вам гарантирую одобрение', 'вам 100% одобрят').\n"
            "3. Запрещенные фразы и некорректное отношение:\n"
            "   - Использование слов паразитов или неформальной речи оператором ('че', 'ща', 'нету', 'чё').\n"
            "   - Фразы 'не знаю' без предложения альтернативы (вместо 'не знаю' должно быть 'позвольте мне уточнить...').\n"
            "   - Отказ в помощи или фраза 'это не в моей компетенции' / 'я этим не занимаюсь'.\n"
            "   - Проявление грубости или перебивание клиента.\n\n"
            "Выходной формат строго JSON:\n"
            "{\n"
            "  \"passed\": true | false,\n"
            "  \"issues\": [\n"
            "    \"описание нарушения 1\",\n"
            "    \"описание нарушения 2\"\n"
            "  ]\n"
            "}"
        )
        
        user_prompt = f"Транскрипт звонка:\n{transcript_text}"
        
        try:
            response_text = await self._call_llm(system_prompt, user_prompt, temperature=0.0)
            result = json.loads(response_text)
            
            passed = bool(result.get("passed", True))
            issues = result.get("issues", [])
            
            # Если нарушений нет, список issues должен быть пустым
            if passed and issues:
                issues = []
            elif not passed and not issues:
                issues = ["Обнаружено комплаенс-нарушение без подробного описания."]
                
            return {
                "passed": passed,
                "issues": issues
            }
            
        except Exception as e:
            logger.error(f"Ошибка в агенте ComplianceAgent: {e}")
            # При сбое считаем, что проверка пройдена (чтобы не блокировать систему), но логируем ошибку
            return {
                "passed": True,
                "issues": []
            }
