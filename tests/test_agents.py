import pytest
from unittest.mock import AsyncMock, patch
from agents.classifier import ClassifierAgent
from agents.quality import QualityAgent
from agents.compliance import ComplianceAgent
from agents.summarizer import SummarizerAgent

# Фиктивный транскрипт диалога для тестов
MOCK_TRANSCRIPT = [
    {"speaker": "Оператор", "start": 0.0, "end": 4.0, "text": "Добрый день, МТБанк, меня зовут Анна, чем могу помочь?"},
    {"speaker": "Клиент", "start": 4.5, "end": 8.0, "text": "Здравствуйте, хочу узнать про кредит наличными."},
    {"speaker": "Оператор", "start": 8.5, "end": 12.0, "text": "Конечно, подскажите сумму и срок."},
    {"speaker": "Клиент", "start": 12.5, "end": 15.0, "text": "Десять тысяч рублей на один год."},
    {"speaker": "Оператор", "start": 15.5, "end": 20.0, "text": "Отлично, ставка от 14.9%, страховка по желанию. До свидания!"},
    {"speaker": "Клиент", "start": 20.5, "end": 22.0, "text": "Спасибо, до свидания."}
]

@pytest.mark.asyncio
async def test_classifier_agent_success():
    """
    Проверка успешной работы агента Classifier.
    """
    agent = ClassifierAgent(api_key="test_key")
    
    # Мокаем вызов LLM
    mock_response = '{"topic": "кредиты", "priority": "medium"}'
    
    with patch.object(agent, '_call_llm', new_callable=AsyncMock) as mock_call:
        mock_call.return_value = mock_response
        result = await agent.run(MOCK_TRANSCRIPT)
        
        mock_call.assert_called_once()
        assert result["topic"] == "кредиты"
        assert result["priority"] == "medium"

@pytest.mark.asyncio
async def test_classifier_agent_fallback():
    """
    Проверка работы Classifier при некорректном ответе от LLM.
    """
    agent = ClassifierAgent(api_key="test_key")
    
    # Мокаем вызов LLM, возвращающий невалидный JSON
    with patch.object(agent, '_call_llm', new_callable=AsyncMock) as mock_call:
        mock_call.side_effect = Exception("LLM connection error")
        result = await agent.run(MOCK_TRANSCRIPT)
        
        assert result["topic"] == "другое"
        assert result["priority"] == "low"

@pytest.mark.asyncio
async def test_quality_agent_success():
    """
    Проверка работы QualityAgent и подсчета баллов.
    """
    agent = QualityAgent(api_key="test_key")
    
    # Приветствие (15) + Выявление (35) + Решение (35) + Прощание (15) = 100
    mock_response_full = '{"greeting": true, "need_detection": true, "solution_provided": true, "farewell": true}'
    # Приветствие (15) + Выявление (35) = 50
    mock_response_half = '{"greeting": true, "need_detection": true, "solution_provided": false, "farewell": false}'
    
    with patch.object(agent, '_call_llm', new_callable=AsyncMock) as mock_call:
        # Тестируем полный балл
        mock_call.return_value = mock_response_full
        result_full = await agent.run(MOCK_TRANSCRIPT)
        assert result_full["total"] == 100
        assert result_full["checklist"]["greeting"] is True
        assert result_full["checklist"]["farewell"] is True
        
        # Тестируем половинный балл
        mock_call.return_value = mock_response_half
        result_half = await agent.run(MOCK_TRANSCRIPT)
        assert result_half["total"] == 50
        assert result_half["checklist"]["solution_provided"] is False
        assert result_half["checklist"]["farewell"] is False

@pytest.mark.asyncio
async def test_compliance_agent_success():
    """
    Проверка работы ComplianceAgent.
    """
    agent = ComplianceAgent(api_key="test_key")
    
    # Случай без нарушений
    mock_response_passed = '{"passed": true, "issues": []}'
    # Случай с нарушениями
    mock_response_failed = '{"passed": false, "issues": ["Оператор навязывал страховку как обязательную", "Использовались грубые слова"]}'
    
    with patch.object(agent, '_call_llm', new_callable=AsyncMock) as mock_call:
        mock_call.return_value = mock_response_passed
        result_passed = await agent.run(MOCK_TRANSCRIPT)
        assert result_passed["passed"] is True
        assert len(result_passed["issues"]) == 0
        
        mock_call.return_value = mock_response_failed
        result_failed = await agent.run(MOCK_TRANSCRIPT)
        assert result_failed["passed"] is False
        assert len(result_failed["issues"]) == 2
        assert "навязывал страховку" in result_failed["issues"][0]

@pytest.mark.asyncio
async def test_summarizer_agent_success():
    """
    Проверка работы SummarizerAgent.
    """
    agent = SummarizerAgent(api_key="test_key")
    
    mock_response = '{"summary": "Клиент позвонил узнать о кредите на 10 тысяч рублей. Оператор озвучил ставку и условия. Договорились об оформлении.", "action_items": ["Отправить инструкцию на email"]}'
    
    with patch.object(agent, '_call_llm', new_callable=AsyncMock) as mock_call:
        mock_call.return_value = mock_response
        result = await agent.run(MOCK_TRANSCRIPT)
        
        assert "кредите на 10 тысяч" in result["summary"]
        assert len(result["action_items"]) == 1
        assert result["action_items"][0] == "Отправить инструкцию на email"
