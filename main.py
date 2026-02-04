import os
import logging
import threading
import time
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def run_api_server():
    """Запуск API сервера"""
    import uvicorn
    from api_server import app
    
    port = int(os.getenv('PORT', 8000))
    logger.info(f"🚀 Запуск API сервера на порту {port}")
    
    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info"
    )
    server = uvicorn.Server(config)
    server.run()

def run_telegram_bot():
    """Запуск Telegram бота"""
    # Даем время API серверу запуститься
    time.sleep(3)
    
    try:
        from telegram_bot import main as bot_main
        
        logger.info("🤖 Запуск Telegram бота...")
        bot_main()
        
    except Exception as e:
        logger.error(f"❌ Ошибка запуска бота: {e}")

def main():
    """Главная функция - запускает оба сервиса"""
    logger.info("🚀 Запуск Margiana Logistics System...")
    
    # Запускаем API сервер в отдельном потоке
    api_thread = threading.Thread(target=run_api_server, daemon=True)
    api_thread.start()
    
    # Даем время API запуститься
    time.sleep(2)
    
    # Запускаем бота в основном потоке
    run_telegram_bot()

if __name__ == "__main__":
    main()
