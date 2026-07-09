import os
import json
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

class BaseAgent:
    def __init__(self, name: str, api_key: str = None, base_url: str = None, model: str = None):
        """
        Инициализация базового LLM-агента.
        """
        self.name = name
        self.api_key = api_key or os.environ.get("LLM_API_KEY", "")
        self.base_url = base_url or os.environ.get("LLM_BASE_URL", "https://api.groq.com/openai/v1")
        self.model = model or os.environ.get("LLM_MODEL", "llama-3.3-70b-versatile")
        
        self.client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )

    def _log_json(self, event: str, data: Dict[str, Any]):
        """
        Логирование событий агента в формате JSON.
        """
        log_payload = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "agent": self.name,
            "event": event,
            "data": data
        }
        # Записываем как одну строку JSON, чтобы лог-парсеры могли легко ее парсить
        logger.info(json.dumps(log_payload, ensure_ascii=False))

    def _format_transcript(self, transcript: List[Dict[str, Any]]) -> str:
        """
        Форматирует структурированный транскрипт в текстовый вид для промпта LLM.
        """
        formatted_lines = []
        for turn in transcript:
            speaker = turn.get("speaker", "Неизвестный")
            text = turn.get("text", "")
            start = turn.get("start", 0.0)
            end = turn.get("end", 0.0)
            formatted_lines.append(f"[{start:04.1f} - {end:04.1f}] {speaker}: {text}")
        return "\n".join(formatted_lines)

    async def _call_llm(
        self, 
        system_prompt: str, 
        user_prompt: str, 
        temperature: float = 0.0,
        response_format_json: bool = True
    ) -> str:
        """
        Вспомогательный метод для асинхронного вызова LLM с логированием.
        """
        # Логируем входные данные
        self._log_json("input", {
            "model": self.model,
            "system_prompt_length": len(system_prompt),
            "user_prompt_length": len(user_prompt),
            "temperature": temperature
        })
        
        try:
            kwargs = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "temperature": temperature,
                "timeout": 30.0
            }
            
            if response_format_json:
                kwargs["response_format"] = {"type": "json_object"}
                
            response = await self.client.chat.completions.create(**kwargs)
            response_text = response.choices[0].message.content
            
            # Попытаемся распарсить JSON, если он ожидался, для лога
            output_data = {}
            if response_format_json:
                try:
                    output_data = json.loads(response_text)
                except:
                    output_data = {"raw_text": response_text, "error": "Failed to parse JSON"}
            else:
                output_data = {"text": response_text}
                
            # Логируем выходные данные
            self._log_json("output", {
                "status": "success",
                "result": output_data
            })
            
            return response_text
            
        except Exception as e:
            self._log_json("output", {
                "status": "error",
                "error_message": str(e)
            })
            raise e

    async def run(self, transcript: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Основной метод выполнения задачи агента. Должен быть переопределен в наследниках.
        """
        raise NotImplementedError("Каждый агент должен реализовать метод run()")
