import os
import asyncio
import subprocess
import json
from edge_tts import Communicate

# Папка для тестовых данных
TEST_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_data")
TEMP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp_generate")

# Голоса для синтеза
VOICE_OPERATOR = "ru-RU-SvetlanaNeural"  # Женский
VOICE_CLIENT = "ru-RU-DmitryNeural"      # Мужской

# 1. Сценарий диалога (docs/sample-dialog.md)
DIALOG_SCRIPT = [
    ("Оператор", "Добрый день, МТБанк, меня зовут Анна, чем могу помочь?"),
    ("Клиент", "Здравствуйте. Хочу узнать про условия по кредиту наличными."),
    ("Оператор", "Конечно, подскажите, пожалуйста, какая сумма вас интересует и на какой срок?"),
    ("Клиент", "Примерно десять тысяч рублей, на год."),
    ("Оператор", "Отлично. На данный момент ставка от четырнадцати и девяти процентов годовых, решение за пятнадцать минут. Вы уже являетесь клиентом МТБанка?"),
    ("Клиент", "Да, у меня есть карточка ваша."),
    ("Оператор", "Прекрасно, тогда для вас действуют специальные условия. Ежемесячный платёж составит около девятисот рублей. Вам удобно подать заявку онлайн через приложение или предпочитаете приехать в отделение?"),
    ("Клиент", "Лучше онлайн. Но у меня вопрос — если я захочу досрочно погасить, есть штрафы?"),
    ("Оператор", "Нет, досрочное погашение без штрафов и комиссий, в любое время и в любом объёме."),
    ("Клиент", "Хорошо, а страховка обязательна?"),
    ("Оператор", "Страхование жизни подключается по вашему желанию, это не обязательное условие получения кредита. Однако при подключении страховки ставка может быть немного снижена."),
    ("Клиент", "Понятно. Тогда я попробую подать через приложение."),
    ("Оператор", "Отлично. Если возникнут вопросы в процессе заполнения — звоните, мы поможем. Также могу отправить вам краткую инструкцию на email, если хотите."),
    ("Клиент", "Да, пожалуйста, отправьте."),
    ("Оператор", "Хорошо, подскажите ваш email."),
    ("Клиент", "Михаил-собака-пример-точка-бай."),
    ("Оператор", "Записала. В течение нескольких минут получите письмо с инструкцией и ссылкой на заявку. Есть ещё вопросы?"),
    ("Клиент", "Нет, всё понятно, спасибо."),
    ("Оператор", "Спасибо за обращение в МТБанк, хорошего дня!"),
    ("Клиент", "И вам, до свидания.")
]

# 2. Монологи
MONOLOGUES = {
    "monologue_operator_card": (
        VOICE_OPERATOR,
        "Уважаемые клиенты, рады представить вам карту рассрочки Халва от МТБанка. "
        "С Халвой вы можете совершать покупки в рассрочку до двенадцати месяцев в сети более чем двадцати тысяч магазинов-партнеров. "
        "Без первоначального взноса, без переплат и скрытых комиссий. Оформить карту можно онлайн в мобильном приложении за пять минут."
    ),
    "monologue_client_complaint": (
        VOICE_CLIENT,
        "Здравствуйте. Я крайне недоволен качеством обслуживания. "
        "Вчера я совершил перевод на карту другого банка, и с меня списали комиссию в размере двух процентов, "
        "хотя в приложении было написано, что перевод без комиссии. "
        "Я требую вернуть мне списанные деньги и объяснить, почему информация в приложении не соответствует действительности."
    ),
    "monologue_operator_transfer": (
        VOICE_OPERATOR,
        "Для совершения перевода через систему ЕРИП вам необходимо зайти в мобильное приложение МТБанка, "
        "выбрать раздел Платежи, далее нажать на ЕРИП. В дереве услуг выберите необходимую категорию, "
        "например, коммунальные платежи или мобильная связь. "
        "Введите реквизиты платежа, сумму и подтвердите операцию кодом из СМС."
    )
}

async def generate_audio_segment(text: str, voice: str, filename: str) -> str:
    """
    Синтезирует один речевой сегмент в MP3 файл.
    """
    filepath = os.path.join(TEMP_DIR, filename)
    communicate = Communicate(text, voice)
    await communicate.save(filepath)
    return filepath

def run_ffmpeg(cmd: list):
    """
    Запускает команду ffmpeg и проверяет ошибки.
    """
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg error: {result.stderr.decode('utf-8')}")

async def build_dialog_audio():
    """
    Синтезирует все реплики диалога, добавляет тишину и склеивает их в один файл.
    """
    print("Генерация реплик диалога...")
    os.makedirs(TEMP_DIR, exist_ok=True)
    os.makedirs(TEST_DATA_DIR, exist_ok=True)
    
    # 1. Генерируем секундную тишину
    silence_wav = os.path.join(TEMP_DIR, "silence.wav")
    run_ffmpeg([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono", 
        "-t", "1.0", silence_wav
    ])
    
    # 2. Генерируем каждую реплику и конвертируем в WAV 16kHz
    wav_files = []
    text_lines = []
    
    for i, (speaker, text) in enumerate(DIALOG_SCRIPT):
        voice = VOICE_OPERATOR if speaker == "Оператор" else VOICE_CLIENT
        mp3_name = f"dialog_seg_{i}.mp3"
        wav_name = f"dialog_seg_{i}.wav"
        
        mp3_path = await generate_audio_segment(text, voice, mp3_name)
        wav_path = os.path.join(TEMP_DIR, wav_name)
        
        # Конвертируем в WAV 16kHz Mono
        run_ffmpeg([
            "ffmpeg", "-y", "-i", mp3_path, "-ar", "16000", "-ac", "1", wav_path
        ])
        
        wav_files.append(wav_path)
        text_lines.append(f"{speaker}: {text}")
        
    # 3. Создаем список для конкатенации (с паузами)
    concat_list_path = os.path.join(TEMP_DIR, "concat_list.txt")
    with open(concat_list_path, "w", encoding="utf-8") as f:
        for i, wav_path in enumerate(wav_files):
            f.write(f"file '{wav_path}'\n")
            # Добавляем паузу после каждой реплики, кроме последней
            if i < len(wav_files) - 1:
                f.write(f"file '{silence_wav}'\n")
                
    # 4. Склеиваем диалог
    output_dialog_path = os.path.join(TEST_DATA_DIR, "call_dialog_1.wav")
    print(f"Склейка диалога в: {output_dialog_path}")
    run_ffmpeg([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_list_path, 
        "-c", "copy", output_dialog_path
    ])
    
    # 5. Сохраняем эталонный транскрипт диалога
    txt_dialog_path = os.path.join(TEST_DATA_DIR, "call_dialog_1.txt")
    with open(txt_dialog_path, "w", encoding="utf-8") as f:
        f.write("\n".join(text_lines))
        
    # 6. Создаем версию 8kHz (телефонное качество)
    output_8khz_path = os.path.join(TEST_DATA_DIR, "call_dialog_8khz.wav")
    print(f"Создание 8kHz версии: {output_8khz_path}")
    run_ffmpeg([
        "ffmpeg", "-y", "-i", output_dialog_path, "-ar", "8000", output_8khz_path
    ])
    
    # Копируем эталонный транскрипт для 8kHz версии
    txt_8khz_path = os.path.join(TEST_DATA_DIR, "call_dialog_8khz.txt")
    with open(txt_8khz_path, "w", encoding="utf-8") as f:
        f.write("\n".join(text_lines))

async def build_monologue_audios():
    """
    Синтезирует монологи и сохраняет их в WAV 16kHz с текстовыми эталонами.
    """
    print("Генерация монологов...")
    for name, (voice, text) in MONOLOGUES.items():
        mp3_name = f"{name}.mp3"
        mp3_path = await generate_audio_segment(text, voice, mp3_name)
        
        wav_path = os.path.join(TEST_DATA_DIR, f"{name}.wav")
        print(f"Сохранение монолога {name} в {wav_path}")
        run_ffmpeg([
            "ffmpeg", "-y", "-i", mp3_path, "-ar", "16000", "-ac", "1", wav_path
        ])
        
        # Сохраняем эталонный текст
        txt_path = os.path.join(TEST_DATA_DIR, f"{name}.txt")
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(text)

async def main():
    print("=== Начало генерации тестовых данных ===")
    os.makedirs(TEMP_DIR, exist_ok=True)
    
    try:
        await build_dialog_audio()
        await build_monologue_audios()
        print("=== Все тестовые данные успешно сгенерированы ===")
    except Exception as e:
        print(f"Ошибка при генерации тестовых данных: {e}")
    finally:
        # Очистка временных файлов
        import shutil
        if os.path.exists(TEMP_DIR):
            shutil.rmtree(TEMP_DIR, ignore_errors=True)

if __name__ == "__main__":
    asyncio.run(main())
