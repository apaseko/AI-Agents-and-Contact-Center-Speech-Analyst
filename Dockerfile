FROM python:3.11-slim

# Установка системных зависимостей, необходимых для faster-whisper и ffmpeg
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Установка Python-зависимостей
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование исходного кода
COPY . .

# Открытие порта
EXPOSE 8000

# Запуск приложения
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
