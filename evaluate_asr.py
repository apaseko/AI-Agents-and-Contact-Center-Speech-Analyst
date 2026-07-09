import os
import re
import requests
import jiwer
from typing import List, Dict, Any

TEST_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_data")
API_URL = "http://localhost:8000/analyze"

def clean_text(text: str) -> str:
    """
    Очищает текст от пунктуации, лишних пробелов,
    приводит к нижнему регистру и удаляет префиксы спикеров для корректного расчета WER.
    """
    # Удаляем разметку спикеров вида "Оператор:" или "Клиент:"
    text = re.sub(r'^(Оператор|Клиент):\s*', '', text, flags=re.IGNORECASE | re.MULTILINE)
    # Удаляем временные метки, если они есть
    text = re.sub(r'\[\d+:\d+\.\d+\]', '', text)
    # Приводим к нижнему регистру
    text = text.lower()
    # Заменяем дефисы, знаки пунктуации на пробелы
    text = re.sub(r'[^\w\s]', ' ', text)
    # Убираем лишние пробелы
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def calculate_wer_for_files():
    """
    Пробегает по тестовым файлам, отправляет их в API, сравнивает с эталонами и считает WER.
    """
    print("=== Начало оценки качества распознавания речи (WER) ===")
    
    if not os.path.exists(TEST_DATA_DIR):
        print(f"Ошибка: Директория с тестовыми данными {TEST_DATA_DIR} не найдена.")
        return
        
    # Находим все WAV файлы
    wav_files = [f for f in os.listdir(TEST_DATA_DIR) if f.endswith(".wav")]
    if not wav_files:
        print("Тестовые аудиофайлы не найдены. Сначала запустите generate_test_data.py.")
        return
        
    results = []
    total_wer = 0.0
    
    for wav_file in wav_files:
        base_name = os.path.splitext(wav_file)[0]
        txt_file = f"{base_name}.txt"
        
        wav_path = os.path.join(TEST_DATA_DIR, wav_file)
        txt_path = os.path.join(TEST_DATA_DIR, txt_file)
        
        if not os.path.exists(txt_path):
            print(f"Предупреждение: Эталонный файл {txt_file} не найден. Пропуск.")
            continue
            
        # 1. Читаем эталонный текст
        with open(txt_path, "r", encoding="utf-8") as f:
            reference_raw = f.read()
            
        reference_clean = clean_text(reference_raw)
        
        # 2. Отправляем аудио на распознавание в API
        print(f"Обработка {wav_file} через API...")
        try:
            with open(wav_path, "rb") as f:
                response = requests.post(API_URL, files={"file": (wav_file, f, "audio/wav")}, timeout=120)
                
            if response.status_code != 200:
                print(f"Ошибка API при обработке {wav_file}: {response.text}")
                continue
                
            response_data = response.json()
            transcript_items = response_data.get("transcript", [])
            
            # Склеиваем гипотезу в единую строку
            hypothesis_raw = " ".join([item["text"] for item in transcript_items])
            hypothesis_clean = clean_text(hypothesis_raw)
            
            # 3. Рассчитываем WER
            # Защита от деления на ноль, если эталон пуст
            if not reference_clean:
                wer = 1.0
            else:
                wer = jiwer.wer(reference_clean, hypothesis_clean)
                
            results.append({
                "file": wav_file,
                "ref_words": len(reference_clean.split()),
                "hyp_words": len(hypothesis_clean.split()),
                "wer": wer
            })
            total_wer += wer
            print(f"Успешно. WER = {wer:.2%}")
            
        except requests.exceptions.ConnectionError:
            print(f"Ошибка: Не удалось подключиться к API по адресу {API_URL}. Убедитесь, что бэкенд запущен.")
            return
        except Exception as e:
            print(f"Ошибка при обработке файла {wav_file}: {e}")
            
    if not results:
        print("Нет результатов для расчета WER.")
        return
        
    # Выводим красивую Markdown таблицу результатов
    avg_wer = total_wer / len(results)
    
    markdown_table = []
    markdown_table.append("| Аудиофайл | Слов в эталоне | Слов в гипотезе | WER |")
    markdown_table.append("|---|---|---|---|")
    for r in results:
        markdown_table.append(f"| `{r['file']}` | {r['ref_words']} | {r['hyp_words']} | **{r['wer']:.2%}** |")
    markdown_table.append(f"| **Средний WER** | | | **{avg_wer:.2%}** |")
    
    print("\n=== Результаты оценки ASR (для вставки в README.md) ===\n")
    print("\n".join(markdown_table))
    print("\n=======================================================")

if __name__ == "__main__":
    calculate_wer_for_files()
