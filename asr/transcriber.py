import os
import asyncio
import logging
from typing import List, Dict, Any, Tuple
from faster_whisper import WhisperModel

logger = logging.getLogger(__name__)

class Transcriber:
    def __init__(self, model_size: str = "small", device: str = "cpu", compute_type: str = "int8"):
        """
        Инициализация Whisper модели.
        model_size: tiny, base, small, medium, large-v3
        device: cpu, cuda
        compute_type: int8, float16, float32
        """
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.model = None

    def load_model(self):
        """
        Загрузка модели в память. Вызывается при старте приложения.
        """
        if self.model is None:
            logger.info(f"Загрузка модели Whisper '{self.model_size}' на {self.device} ({self.compute_type})...")
            # Загружаем модель. На CPU используем int8 для уменьшения памяти и ускорения
            self.model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type
            )
            logger.info(f"Модель Whisper '{self.model_size}' успешно загружена.")

    def _transcribe_sync(self, audio_path: str) -> List[Dict[str, Any]]:
        """
        Синхронная транскрибация файла.
        """
        if self.model is None:
            self.load_model()
            
        logger.info(f"Начало транскрибации файла: {audio_path}")
        # beam_size=5 - стандартное значение для хорошего баланса скорости и качества.
        # language="ru" - жестко задаем русский язык для исключения ошибок автоопределения.
        segments, info = self.model.transcribe(
            audio_path,
            beam_size=5,
            language="ru",
            word_timestamps=False  # Нам достаточно таймингов сегментов
        )
        
        result = []
        for segment in segments:
            result.append({
                "start": round(segment.start, 2),
                "end": round(segment.end, 2),
                "text": segment.text.strip()
            })
            
        logger.info(f"Транскрибация завершена. Сгенерировано {len(result)} сегментов.")
        return result

    async def transcribe(self, audio_path: str) -> List[Dict[str, Any]]:
        """
        Асинхронная транскрибация файла, запускаемая в пуле потоков.
        """
        # Запуск тяжелой синхронной операции в отдельном потоке, чтобы не блокировать event loop FastAPI
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._transcribe_sync, audio_path)
