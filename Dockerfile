FROM python:3.11-slim

WORKDIR /app

# Устанавливаем минимальные системные зависимости
RUN apt-get update && apt-get install -y \
    python3-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Копируем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код
COPY . .

# Создаем директорию для временных файлов
RUN mkdir -p /tmp

# Запускаем бота
CMD ["python", "bot.py"]