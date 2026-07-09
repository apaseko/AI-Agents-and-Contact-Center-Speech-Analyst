import os
import requests
import json
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

class Pipeline:
    class Valves(BaseModel):
        API_BASE_URL: str = Field(
            default="http://api-backend:8000",
            description="Базовый URL бэкенда аналитики (FastAPI)"
        )
        OPENWEBUI_URL: str = Field(
            default="http://openwebui:8080",
            description="Внутренний URL OpenWebUI для загрузки файлов контейнером Pipelines"
        )

    def __init__(self):
        self.name = "Речевая аналитика звонков (MTBank)"
        self.valves = self.Valves()

    async def on_startup(self):
        print(f"Pipeline '{self.name}' запущен. Бэкенд: {self.valves.API_BASE_URL}")

    async def on_shutdown(self):
        print(f"Pipeline '{self.name}' остановлен.")

    def _extract_file_url(self, body: Dict[str, Any]) -> Optional[str]:
        """
        Извлекает URL файла или локальный путь к файлу на диске.
        """
        import re
        
        messages = body.get("messages", [])
        if not messages:
            return None
        
        last_message = messages[-1]
        
        # 1. Проверяем файлы в самом сообщении (поле files)
        files = last_message.get("files", [])
        if files and len(files) > 0:
            file_info = files[0]
            file_url = file_info.get("file", {}).get("url")
            if file_url:
                return file_url
            
        # 2. Ищем XML-подобные теги файлов в контенте сообщения
        content = last_message.get("content", "")
        file_tags = re.findall(r'<file\s+([^>]+)/>', content)
        for tag in file_tags:
            url_match = re.search(r'url=["\']([^"\']+)["\']', tag)
            name_match = re.search(r'name=["\']([^"\']+)["\']', tag)
            if url_match and name_match:
                file_id = url_match.group(1)
                file_name = name_match.group(1)
                
                # Проверяем, смонтирован ли диск и доступен ли файл локально
                local_path = f"/app/backend/data/uploads/{file_id}_{file_name}"
                if os.path.exists(local_path):
                    print(f"Файл найден локально на диске: {local_path}")
                    return local_path
                
                # Если диск не смонтирован, возвращаем ссылку для скачивания по сети
                if not file_id.startswith("http"):
                    return f"{self.valves.OPENWEBUI_URL}/api/v1/files/{file_id}/content"
                return file_id
            
        # 3. Также пробуем найти прямые ссылки на аудио в тексте сообщения
        if content.strip().startswith("http://") or content.strip().startswith("https://"):
            return content.split()[0]
            
        return None

    def _download_file(self, url: str, token: Optional[str] = None) -> Optional[tuple]:
        """
        Получает содержимое файла. Если путь локальный — читает с диска,
        иначе скачивает по сети с передачей JWT-токена пользователя.
        """
        # Если передан локальный путь на диске
        if url.startswith("/app/backend/data/"):
            try:
                print(f"Прямое чтение файла с диска: {url}")
                filename = os.path.basename(url)
                # Отсекаем префикс UUID_ (36 символов UUID + 1 символ подчеркивания)
                if len(filename) > 37 and filename[36] == "_":
                    filename = filename[37:]
                with open(url, "rb") as f:
                    content = f.read()
                return filename, content
            except Exception as e:
                print(f"Ошибка при чтении файла с диска: {e}")
                # Если локальное чтение не удалось, продолжаем попытку сетевого скачивания
        
        download_url = url
        # Если URL указывает на localhost/127.0.0.1 OpenWebUI, подменяем на имя контейнера в сети docker
        if "localhost:8080" in download_url:
            download_url = download_url.replace("localhost:8080", "openwebui:8080")
        elif "127.0.0.1:8080" in download_url:
            download_url = download_url.replace("127.0.0.1:8080", "openwebui:8080")
        # Для портов по умолчанию (если в докере openwebui мапится на 3000 снаружи, а внутри 8080)
        elif "localhost:3000" in download_url:
            download_url = download_url.replace("localhost:3000", "openwebui:8080")
        elif "127.0.0.1:3000" in download_url:
            download_url = download_url.replace("127.0.0.1:3000", "openwebui:8080")

        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        try:
            print(f"Скачивание файла по адресу: {download_url}")
            response = requests.get(download_url, headers=headers, stream=True, timeout=30)
            response.raise_for_status()
            
            # Извлекаем имя файла из заголовков или URL
            filename = "audio.wav"
            if "content-disposition" in response.headers:
                cd = response.headers.get("content-disposition", "")
                if "filename=" in cd:
                    filename = cd.split("filename=")[1].strip('"')
            else:
                filename = os.path.basename(download_url.split("?")[0]) or "audio.wav"
                
            return filename, response.content
        except Exception as e:
            print(f"Ошибка при скачивании файла: {e}")
            return None

    def _format_markdown_report(self, data: Dict[str, Any]) -> str:
        """
        Форматирует JSON-ответ бэкенда в красивый Markdown-отчет.
        """
        classification = data.get("classification", {})
        priority = classification.get("priority", "low").upper()
        priority_emoji = "🟢" if priority == "LOW" else ("🟡" if priority == "MEDIUM" else "🔴")
        
        quality = data.get("quality_score", {})
        checklist = quality.get("checklist", {})
        
        def check_emoji(val):
            return "✅" if val else "❌"
            
        compliance = data.get("compliance", {})
        compliance_status = "✅ Пройдено" if compliance.get("passed", True) else "❌ Выявлены нарушения"
        
        # Формирование разделов
        report = []
        report.append("# 🏦 Отчет речевой аналитики звонка\n")
        
        # Общая сводка
        report.append("## 🏷️ Общая информация")
        report.append(f"- **Тематика обращения:** `{classification.get('topic', 'Не определена')}`")
        report.append(f"- **Приоритет:** {priority_emoji} `{priority}`\n")
        
        # Резюме
        report.append("## 📝 Резюме разговора")
        report.append(f"> {data.get('summary', 'Резюме отсутствует.')}\n")
        
        # Оценка качества
        report.append("## 📋 Чек-лист качества работы оператора")
        report.append(f"- **Итоговая оценка:** **{quality.get('total', 0)} / 100**")
        report.append(f"- {check_emoji(checklist.get('greeting', False))} Приветствие")
        report.append(f"- {check_emoji(checklist.get('need_detection', False))} Выявление потребности")
        report.append(f"- {check_emoji(checklist.get('solution_provided', False))} Предоставление решения")
        report.append(f"- {check_emoji(checklist.get('farewell', False))} Вежливое прощание\n")
        
        # Комплаенс
        report.append("## 🛡️ Комплаенс-контроль")
        report.append(f"- **Статус:** {compliance_status}")
        issues = compliance.get("issues", [])
        if issues:
            report.append("- **Замечания:**")
            for issue in issues:
                report.append(f"  - ⚠️ {issue}")
        else:
            report.append("- **Замечания:** отсутствуют\n")
            
        # Action Items
        report.append("## 🎯 Задачи к исполнению (Action Items)")
        action_items = data.get("action_items", [])
        if action_items:
            for i, item in enumerate(action_items, 1):
                report.append(f"{i}. {item}")
        else:
            report.append("*Задачи не выявлены*")
        report.append("\n")
        
        # Транскрипт
        report.append("## 💬 Транскрипт диалога")
        transcript = data.get("transcript", [])
        if transcript:
            for turn in transcript:
                speaker = turn.get("speaker", "Неизвестный")
                start = turn.get("start", 0.0)
                end = turn.get("end", 0.0)
                text = turn.get("text", "")
                
                # Выделение спикеров
                speaker_prefix = "👩‍💼 **Оператор**" if speaker == "Оператор" else "👤 **Клиент**"
                report.append(f"**[{start:04.1f} - {end:04.1f}]** {speaker_prefix}: {text}")
        else:
            report.append("*Транскрипт пуст или не был сгенерирован.*")
            
        return "\n".join(report)

    def pipe(self, body: Dict[str, Any], __user__: Optional[Dict[str, Any]] = None, **kwargs) -> str:
        """
        Основной метод обработки сообщения в OpenWebUI Pipelines.
        """
        # Логируем body и user для отладки структуры файлов
        print(f"DEBUG: body keys = {list(body.keys())}")
        print(f"DEBUG: __user__ = {__user__}")
        print(f"DEBUG: body['user'] = {body.get('user')}")
        print(f"DEBUG: kwargs keys = {list(kwargs.keys())}")
        for k, v in kwargs.items():
            # Ограничим длину вывода для безопасности/читаемости
            val_str = str(v)
            if len(val_str) > 200:
                val_str = val_str[:200] + "..."
            print(f"DEBUG: kwargs[{k}] = {val_str}")
        if "messages" in body and body["messages"]:
            print(f"DEBUG: last message keys = {list(body['messages'][-1].keys())}")
            if "files" in body["messages"][-1]:
                print(f"DEBUG: last message files = {body['messages'][-1]['files']}")
            else:
                # Напечатаем само последнее сообщение без больших полей, чтобы понять структуру RAG
                msg_copy = body["messages"][-1].copy()
                if "content" in msg_copy and len(msg_copy["content"]) > 200:
                    msg_copy["content"] = msg_copy["content"][:200] + "..."
                print(f"DEBUG: last message data = {msg_copy}")
                
        # Извлекаем ссылку на аудиофайл
        file_url = self._extract_file_url(body)
        
        if not file_url:
            # Если это системный/фоновый запрос OpenWebUI (RAG, подсказки, поиск и т.д.),
            # мы возвращаем пустую строку, чтобы не затирать основной отчет аналитики звонка.
            content = last_message.get("content", "")
            if "### Task:" in content or "Respond to the" in content or "Suggest" in content:
                print("DEBUG: Игнорирование системного/фонового запроса OpenWebUI.")
                return ""
                
            return (
                "❌ **Аудиофайл не найден.**\n\n"
                "Пожалуйста, загрузите аудиофайл (WAV, MP3, OGG) в чат "
                "или отправьте прямую URL-ссылку на него."
            )
            
        # Извлекаем JWT-токен пользователя для авторизованного скачивания из OpenWebUI
        user_token = __user__.get("token") if __user__ else None
            
        # Скачиваем файл
        download_result = self._download_file(file_url, user_token)
        if not download_result:
            return f"❌ **Не удалось загрузить аудиофайл по ссылке:** `{file_url}`"
            
        filename, file_content = download_result
        
        # Отправляем файл на анализ в FastAPI бэкенд
        analyze_url = f"{self.valves.API_BASE_URL}/analyze"
        try:
            print(f"Отправка файла '{filename}' на анализ в бэкенд: {analyze_url}")
            files = {"file": (filename, file_content, "application/octet-stream")}
            
            response = requests.post(analyze_url, files=files, timeout=120)
            
            if response.status_code != 200:
                error_msg = response.text
                try:
                    error_json = response.json()
                    error_msg = error_json.get("detail", error_msg)
                except:
                    pass
                return f"❌ **Ошибка бэкенда аналитики (Код {response.status_code}):**\n```\n{error_msg}\n```"
                
            # Форматируем результат в красивый Markdown
            analysis_result = response.json()
            return self._format_markdown_report(analysis_result)
            
        except requests.exceptions.RequestException as e:
            return f"❌ **Ошибка соединения с бэкендом аналитики ({analyze_url}):**\n`{str(e)}`"
        except Exception as e:
            return f"❌ **Непредвиденная ошибка при обработке:**\n`{str(e)}`"
