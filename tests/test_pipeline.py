import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient

# Патчим load_model при импорте, чтобы при старте приложения не загружался реальный Whisper
with patch('asr.transcriber.Transcriber.load_model', MagicMock()):
    from api.main import app

@pytest.fixture
def client():
    # Запускаем TestClient с контекстным менеджером для выполнения lifespan событий (создание temp папки)
    with TestClient(app) as c:
        yield c

def test_health_endpoint(client):
    """
    Тест работоспособности эндпоинта /health.
    """
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"

@patch('asr.transcriber.Transcriber.transcribe', new_callable=AsyncMock)
@patch('asr.diarizer.LLMDiarizer.diarize', new_callable=AsyncMock)
@patch('agents.supervisor.Supervisor.analyze', new_callable=AsyncMock)
def test_analyze_endpoint_with_file(mock_analyze, mock_diarize, mock_transcribe, client):
    """
    Интеграционный тест POST /analyze с загрузкой файла.
    """
    # Настраиваем моки
    mock_transcribe.return_value = [
        {"start": 0.0, "end": 2.0, "text": "Привет"}
    ]
    mock_diarize.return_value = [
        {"speaker": "Оператор", "start": 0.0, "end": 2.0, "text": "Привет"}
    ]
    mock_analyze.return_value = {
        "classification": {"topic": "карты", "priority": "low"},
        "quality_score": {"total": 100, "checklist": {"greeting": True, "need_detection": True, "solution_provided": True, "farewell": True}},
        "compliance": {"passed": True, "issues": []},
        "summary": "Разговор приветствия.",
        "action_items": []
    }

    # Имитируем загрузку файла
    file_content = b"fake audio content"
    files = {"file": ("test.wav", file_content, "audio/wav")}
    
    response = client.post("/analyze", files=files)
    
    assert response.status_code == 200
    data = response.json()
    
    # Проверяем структуру ответа
    assert "transcript" in data
    assert data["transcript"][0]["speaker"] == "Оператор"
    assert data["classification"]["topic"] == "карты"
    assert data["quality_score"]["total"] == 100
    assert data["compliance"]["passed"] is True
    assert "summary" in data

    # Проверяем, что моки вызывались
    mock_transcribe.assert_called_once()
    mock_diarize.assert_called_once()
    mock_analyze.assert_called_once()

@patch('asr.transcriber.Transcriber.transcribe', new_callable=AsyncMock)
@patch('asr.diarizer.LLMDiarizer.diarize', new_callable=AsyncMock)
@patch('agents.supervisor.Supervisor.analyze', new_callable=AsyncMock)
@patch('api.main.download_file_to_temp', new_callable=AsyncMock)
def test_analyze_endpoint_with_json_url(mock_download, mock_analyze, mock_diarize, mock_transcribe, client):
    """
    Интеграционный тест POST /analyze с отправкой JSON с URL.
    """
    # Настраиваем моки
    mock_download.return_value = "temp/downloaded_audio.wav"
    mock_transcribe.return_value = [
        {"start": 0.0, "end": 2.0, "text": "Привет"}
    ]
    mock_diarize.return_value = [
        {"speaker": "Оператор", "start": 0.0, "end": 2.0, "text": "Привет"}
    ]
    mock_analyze.return_value = {
        "classification": {"topic": "карты", "priority": "low"},
        "quality_score": {"total": 100, "checklist": {"greeting": True, "need_detection": True, "solution_provided": True, "farewell": True}},
        "compliance": {"passed": True, "issues": []},
        "summary": "Разговор приветствия.",
        "action_items": []
    }

    response = client.post("/analyze", json={"url": "https://example.com/audio.mp3"})
    
    assert response.status_code == 200
    data = response.json()
    
    assert "transcript" in data
    assert data["classification"]["topic"] == "карты"
    
    mock_download.assert_called_once_with("https://example.com/audio.mp3", unittest_mock_any())
    mock_transcribe.assert_called_once()

# Вспомогательный класс для сравнения аргументов с моком
class AnyStringWithPattern:
    def __eq__(self, other):
        return isinstance(other, str) and "downloaded_" in other

def unittest_mock_any():
    return AnyStringWithPattern()
