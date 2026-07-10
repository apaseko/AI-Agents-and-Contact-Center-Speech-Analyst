#!/bin/bash
# Скрипт автоматического развертывания системы речевой аналитики на Ubuntu без Docker

set -e

echo "=== 1. Установка системных зависимостей ==="
sudo apt update
sudo apt install -y python3-pip python3-venv ffmpeg build-essential git nginx

echo "=== 2. Настройка папок и клонирование проекта ==="
sudo mkdir -p /opt
sudo git clone https://github.com/apaseko/AI-Agents-and-Contact-Center-Speech-Analyst.git /opt/mtbank-analytics || true

echo "=== 3. Настройка FastAPI бэкенда ==="
cd /opt/mtbank-analytics
python3 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt
if [ ! -f .env ]; then
    cp .env.example .env
fi

echo "=== 4. Настройка OpenWebUI Pipelines ==="
sudo git clone https://github.com/open-webui/pipelines.git /opt/pipelines || true
cd /opt/pipelines
python3 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt
cp /opt/mtbank-analytics/pipeline.py /opt/pipelines/pipelines/pipeline.py

echo "=== 5. Настройка OpenWebUI ==="
sudo mkdir -p /opt/openwebui
cd /opt/openwebui
python3 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install openwebui

# Связываем папки для прямого доступа к загружаемым файлам
sudo mkdir -p /app/backend/data
sudo ln -sf /opt/openwebui/data/uploads /app/backend/data/uploads

echo "=== 6. Создание служб Systemd ==="

# Бэкенд
sudo bash -c 'cat > /etc/systemd/system/mtbank-backend.service <<EOF
[Unit]
Description=MTBank Analytics FastAPI Backend
After=network.target

[Service]
User=root
WorkingDirectory=/opt/mtbank-analytics
EnvironmentFile=/opt/mtbank-analytics/.env
ExecStart=/opt/mtbank-analytics/venv/bin/uvicorn api.main:app --host 127.0.0.1 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
EOF'

# Pipelines
sudo bash -c 'cat > /etc/systemd/system/openwebui-pipelines.service <<EOF
[Unit]
Description=OpenWebUI Pipelines Service
After=network.target

[Service]
User=root
WorkingDirectory=/opt/pipelines
Environment=PIPELINES_API_KEY=dummy_key_for_pipelines
ExecStart=/opt/pipelines/venv/bin/uvicorn main:app --host 127.0.0.1 --port 9099
Restart=always

[Install]
WantedBy=multi-user.target
EOF'

# OpenWebUI
sudo bash -c 'cat > /etc/systemd/system/openwebui.service <<EOF
[Unit]
Description=OpenWebUI Service
After=network.target

[Service]
User=root
WorkingDirectory=/opt/openwebui
Environment=DATA_DIR=/opt/openwebui/data
ExecStart=/opt/openwebui/venv/bin/openwebui serve --port 8080
Restart=always

[Install]
WantedBy=multi-user.target
EOF'

echo "=== 7. Настройка Nginx ==="
sudo bash -c 'cat > /etc/nginx/sites-available/default <<EOF
server {
    listen 80 default_server;
    listen [::]:80 default_server;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF'

echo "=== 8. Запуск всех сервисов ==="
sudo systemctl daemon-reload
sudo systemctl enable mtbank-backend openwebui-pipelines openwebui
sudo systemctl restart mtbank-backend openwebui-pipelines openwebui
sudo systemctl restart nginx

echo "=== Развертывание завершено успешно! ==="
echo "Перейдите по IP вашего сервера в браузере для работы с системой."
