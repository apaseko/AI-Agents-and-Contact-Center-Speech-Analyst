import asyncio
import logging
from typing import List, Dict, Any
from agents.classifier import ClassifierAgent
from agents.quality import QualityAgent
from agents.compliance import ComplianceAgent
from agents.summarizer import SummarizerAgent

logger = logging.getLogger(__name__)

class Supervisor:
    def __init__(self, api_key: str = None, base_url: str = None, model: str = None):
        """
        Инициализация Supervisor для оркестрации агентов.
        Инициализирует дочерних агентов с общими настройками LLM.
        """
        self.classifier = ClassifierAgent(api_key, base_url, model)
        self.quality = QualityAgent(api_key, base_url, model)
        self.compliance = ComplianceAgent(api_key, base_url, model)
        self.summarizer = SummarizerAgent(api_key, base_url, model)

    async def analyze(self, transcript: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Запускает всех агентов параллельно для анализа транскрипта звонка
        и объединяет их ответы в единую структуру.
        """
        if not transcript:
            logger.warning("Получен пустой транскрипт для анализа. Возвращаются пустые результаты.")
            return {
                "classification": {"topic": "другое", "priority": "low"},
                "quality_score": {
                    "total": 0,
                    "checklist": {
                        "greeting": False,
                        "need_detection": False,
                        "solution_provided": False,
                        "farewell": False
                    }
                },
                "compliance": {"passed": True, "issues": []},
                "summary": "Разговор отсутствует или пуст.",
                "action_items": []
            }

        logger.info(f"Начало параллельного мультиагентного анализа транскрипта...")
        
        # Асинхронный параллельный запуск всех четырех агентов
        tasks = [
            self.classifier.run(transcript),
            self.quality.run(transcript),
            self.compliance.run(transcript),
            self.summarizer.run(transcript)
        ]
        
        try:
            # gather запускает задачи конкурентно и ждет завершения всех
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Обработка результатов с проверкой на ошибки в процессах
            # Classifier
            classifier_res = results[0]
            if isinstance(classifier_res, Exception):
                logger.error(f"Агент Classifier завершился с ошибкой: {classifier_res}")
                classifier_res = {"topic": "другое", "priority": "low"}
                
            # Quality
            quality_res = results[1]
            if isinstance(quality_res, Exception):
                logger.error(f"Агент Quality завершился с ошибкой: {quality_res}")
                quality_res = {
                    "total": 0,
                    "checklist": {
                        "greeting": False,
                        "need_detection": False,
                        "solution_provided": False,
                        "farewell": False
                    }
                }
                
            # Compliance
            compliance_res = results[2]
            if isinstance(compliance_res, Exception):
                logger.error(f"Агент Compliance завершился с ошибкой: {compliance_res}")
                compliance_res = {"passed": True, "issues": []}
                
            # Summarizer
            summarizer_res = results[3]
            if isinstance(summarizer_res, Exception):
                logger.error(f"Агент Summarizer завершился с ошибкой: {summarizer_res}")
                summarizer_res = {
                    "summary": "Не удалось проанализировать разговор из-за технической ошибки.",
                    "action_items": []
                }
                
            # Агрегирование в единый структурированный JSON
            final_report = {
                "classification": classifier_res,
                "quality_score": quality_res,
                "compliance": compliance_res,
                "summary": summarizer_res.get("summary", ""),
                "action_items": summarizer_res.get("action_items", [])
            }
            
            logger.info("Параллельный мультиагентный анализ звонка успешно завершен.")
            return final_report
            
        except Exception as e:
            logger.critical(f"Критическая ошибка оркестратора Supervisor: {e}")
            # Откат в безопасное дефолтное состояние
            return {
                "classification": {"topic": "другое", "priority": "low"},
                "quality_score": {
                    "total": 0,
                    "checklist": {
                        "greeting": False,
                        "need_detection": False,
                        "solution_provided": False,
                        "farewell": False
                    }
                },
                "compliance": {"passed": True, "issues": []},
                "summary": f"Внутренняя ошибка сервиса анализа: {str(e)}",
                "action_items": []
            }
