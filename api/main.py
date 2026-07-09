import os
import shutil
import logging
from contextlib import asynccontextmanager
from typing import Optional, List, Dict, Any
import httpx
from fastapi import FastAPI, File, UploadFile, Form, Request, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from asr.transcriber import Transcriber
from asr.diarizer import LLMDiarizer
from agents.supervisor import Supervisor

# Загрузка переменных окружения
from dotenv import load_dotenv
load_dotenv()

# Настройка логирования
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("api.main")

# Глобальные объекты
transcriber: Optional[Transcriber] = None
diarizer: Optional[LLMDiarizer] = None
supervisor: Optional[Supervisor] = None

# Директория для временного хранения аудио
TEMP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "temp")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Управление жизненным циклом приложения:
    Инициализация Whisper и агентов при старте, очистка при остановке.
    """
    global transcriber, diarizer, supervisor
    
    # Создаем временную директорию в воркспейсе
    os.makedirs(TEMP_DIR, exist_ok=True)
    logger.info(f"Временная директория создана по пути: {TEMP_DIR}")
    
    # Читаем параметры Whisper из .env
    whisper_model = os.getenv("WHISPER_MODEL", "small")
    
    # Инициализируем и загружаем Whisper
    transcriber = Transcriber(model_size=whisper_model)
    try:
        transcriber.load_model()
    except Exception as e:
        logger.critical(f"Не удалось загрузить модель Whisper: {e}")
        
    # Инициализируем диаризатор и супервизор
    diarizer = LLMDiarizer()
    supervisor = Supervisor()
    
    yield
    
    # Очистка временной директории при завершении
    if os.path.exists(TEMP_DIR):
        logger.info(f"Удаление временной директории: {TEMP_DIR}")
        shutil.rmtree(TEMP_DIR, ignore_errors=True)

app = FastAPI(
    title="MTBank Speech Analytics API",
    version="1.0.0",
    description="REST API для речевой аналитики звонков с транскрибацией и мультиагентным анализом",
    lifespan=lifespan
)

class AnalyzeRequest(BaseModel):
    url: str

async def download_file_to_temp(url: str, filename: str) -> str:
    """
    Скачивает файл по ссылке во временную директорию.
    """
    temp_path = os.path.join(TEMP_DIR, filename)
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream("GET", url) as response:
                if response.status_code != 200:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Не удалось скачать файл по ссылке. Статус-код: {response.status_code}"
                    )
                with open(temp_path, "wb") as f:
                    async for chunk in response.aiter_bytes():
                        f.write(chunk)
        return temp_path
    except Exception as e:
        logger.error(f"Ошибка при скачивании файла {url}: {e}")
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ошибка скачивания файла: {str(e)}"
        )

@app.get("/health", summary="Проверка работоспособности")
async def health():
    return {
        "status": "healthy",
        "whisper_model": transcriber.model_size if transcriber else None,
        "llm_model": os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")
    }

@app.post("/analyze", summary="Анализ аудиозаписи звонка")
async def analyze(
    request: Request,
    file: Optional[UploadFile] = File(None),
    url_form: Optional[str] = Form(None, alias="url")
):
    """
    Эндпоинт для анализа аудио.
    Поддерживает:
    - multipart/form-data: загрузка файла в поле 'file'
    - multipart/form-data: передача ссылки в поле 'url'
    - application/json: передача JSON вида {"url": "https://..."}
    """
    audio_path = None
    temp_filename = ""
    
    # 1. Определяем формат входных данных
    content_type = request.headers.get("content-type", "")
    
    try:
        if "application/json" in content_type:
            # Читаем JSON body
            try:
                body = await request.json()
                url = body.get("url")
                if not url:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="В JSON-теле запроса отсутствует обязательное поле 'url'"
                    )
                temp_filename = f"downloaded_{os.urandom(4).hex()}_{os.path.basename(url.split('?')[0]) or 'audio.wav'}"
                audio_path = await download_file_to_temp(url, temp_filename)
            except json.JSONDecodeError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Некорректный JSON"
                )
        
        elif "multipart/form-data" in content_type:
            # Читаем multipart форму
            if file:
                # Сохраняем загруженный файл во временную директорию
                safe_filename = f"uploaded_{os.urandom(4).hex()}_{file.filename}"
                audio_path = os.path.join(TEMP_DIR, safe_filename)
                logger.info(f"Сохранение загруженного файла во временный путь: {audio_path}")
                with open(audio_path, "wb") as buffer:
                    shutil.copyfileobj(file.file, buffer)
            elif url_form:
                # Скачиваем файл по URL из формы
                temp_filename = f"downloaded_{os.urandom(4).hex()}_{os.path.basename(url_form.split('?')[0]) or 'audio.wav'}"
                audio_path = await download_file_to_temp(url_form, temp_filename)
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Не передан ни аудиофайл в поле 'file', ни ссылка в поле 'url'"
                )
        else:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="Поддерживаются только Content-Type: multipart/form-data и application/json"
            )
            
        # 2. Выполняем транскрибацию (ASR)
        logger.info(f"Запуск ASR для файла: {audio_path}")
        raw_segments = await transcriber.transcribe(audio_path)
        
        if not raw_segments:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Не удалось извлечь речь из аудиофайла. Возможно, файл пуст или поврежден."
            )
            
        # 3. Выполняем диаризацию (Вариант С)
        logger.info("Запуск LLM-диаризации...")
        diarized_transcript = await diarizer.diarize(raw_segments)
        
        # 4. Выполняем мультиагентный анализ через Supervisor
        logger.info("Запуск мультиагентного анализа...")
        analysis_report = await supervisor.analyze(diarized_transcript)
        
        # 5. Формируем финальный ответ
        response_data = {
            "transcript": diarized_transcript,
            **analysis_report
        }
        
        return JSONResponse(content=response_data)
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.exception("Критическая ошибка при обработке запроса /analyze")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Внутренняя ошибка сервера: {str(e)}"
        )
    finally:
        # Всегда очищаем временные файлы
        if audio_path and os.path.exists(audio_path):
            try:
                os.remove(audio_path)
                logger.info(f"Временный файл успешно удален: {audio_path}")
            except Exception as e:
                logger.error(f"Не удалось удалить временный файл {audio_path}: {e}")
