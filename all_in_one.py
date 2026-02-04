import os
import logging
import asyncio
from datetime import datetime
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from pydantic import BaseModel
from typing import Optional
import psycopg2
from psycopg2.extras import RealDictCursor
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    JobQueue
)
from telegram.constants import ParseMode
import threading

# ========== НАСТРОЙКА ==========
load_dotenv()

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
ADMIN_CHAT_IDS = os.getenv('ADMIN_CHAT_IDS', '').split(',')
DATABASE_URL = os.getenv('DATABASE_URL')
API_KEY = os.getenv('SYNC_API_KEY', 'margiana_sync_key_2024_secure_change_this')

logger.info("🚀 Margiana Logistics System запускается...")

# ========== БАЗА ДАННЫХ ==========
def get_db_connection():
    try:
        if not DATABASE_URL:
            DATABASE_URL = "postgresql://postgres.neypmeacztdapjfrnzgu:margiana0011@aws-1-eu-north-1.pooler.supabase.com:6543/postgres"
        
        return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    except Exception as e:
        logger.error(f"DB error: {e}")
        return None

# ========== FASTAPI ==========
app = FastAPI(title="Margiana Logistics API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class OrderSyncData(BaseModel):
    order_number: str
    client_name: str
    container_count: Optional[int] = 0
    goods_type: Optional[str] = None
    route: Optional[str] = None
    transit_port: Optional[str] = None
    document_number: Optional[str] = None
    chinese_transport_company: Optional[str] = None
    iranian_transport_company: Optional[str] = None
    status: Optional[str] = "New"
    status_color: Optional[str] = "#FFFFFF"
    creation_date: Optional[datetime] = None
    loading_date: Optional[datetime] = None
    departure_date: Optional[datetime] = None
    arrival_iran_date: Optional[datetime] = None
    truck_loading_date: Optional[datetime] = None
    arrival_turkmenistan_date: Optional[datetime] = None
    client_receiving_date: Optional[datetime] = None
    arrival_notice_date: Optional[datetime] = None
    tkm_date: Optional[datetime] = None
    eta_date: Optional[datetime] = None
    has_loading_photo: Optional[bool] = False
    has_local_charges: Optional[bool] = False
    has_tex: Optional[bool] = False
    notes: Optional[str] = None
    additional_info: Optional[str] = None

def verify_api_key(api_key: str = Header(None, alias="api-key")):
    if not api_key or api_key != API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")
    return api_key

@app.get("/")
async def root():
    return {"status": "ok", "service": "Margiana Logistics API"}

@app.post("/api/sync/order")
async def sync_order(order_data: OrderSyncData, api_key: str = Depends(verify_api_key)):
    try:
        logger.info(f"Syncing order: {order_data.order_number}")
        
        conn = get_db_connection()
        if not conn:
            raise HTTPException(status_code=500, detail="DB error")
        
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM orders WHERE order_number = %s", (order_data.order_number,))
        existing = cursor.fetchone()
        
        if existing:
            # UPDATE
            cursor.execute("""
                UPDATE orders SET
                    client_name = %s, container_count = %s, goods_type = %s,
                    route = %s, status = %s, sync_timestamp = NOW()
                WHERE order_number = %s RETURNING id
            """, (
                order_data.client_name, order_data.container_count, order_data.goods_type,
                order_data.route, order_data.status, order_data.order_number
            ))
        else:
            # INSERT
            cursor.execute("""
                INSERT INTO orders (
                    order_number, client_name, container_count, goods_type,
                    route, status, sync_timestamp, last_modified
                ) VALUES (%s, %s, %s, %s, %s, %s, NOW(), NOW()) RETURNING id
            """, (
                order_data.order_number, order_data.client_name, order_data.container_count,
                order_data.goods_type, order_data.route, order_data.status
            ))
        
        order_id = cursor.fetchone()['id']
        conn.commit()
        cursor.close()
        conn.close()
        
        logger.info(f"✅ Order {order_data.order_number} saved to DB")
        
        return {
            "status": "success",
            "order_number": order_data.order_number,
            "order_id": order_id
        }
        
    except Exception as e:
        logger.error(f"❌ Sync error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ========== ТЕЛЕГРАМ БОТ ==========
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    await update.message.reply_text(
        "🎉 *Добро пожаловать в Margiana Logistics!*\n\n"
        "Доступные команды:\n"
        "/start - это меню\n"
        "/orders - показать заказы\n"
        "/help - помощь",
        parse_mode=ParseMode.MARKDOWN
    )

async def orders_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /orders"""
    try:
        conn = get_db_connection()
        if not conn:
            await update.message.reply_text("❌ Ошибка базы данных")
            return
        
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM orders ORDER BY creation_date DESC LIMIT 5")
        orders = cursor.fetchall()
        cursor.close()
        conn.close()
        
        if not orders:
            await update.message.reply_text("📭 Нет заказов")
            return
        
        text = "📦 *Последние заказы:*\n\n"
        for order in orders:
            text += f"• {order['order_number']} - {order['client_name']}\n"
        
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
        
    except Exception as e:
        logger.error(f"Orders error: {e}")
        await update.message.reply_text("❌ Ошибка")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /help"""
    await update.message.reply_text(
        "📋 *Помощь:*\n\n"
        "Для WPF программы:\n"
        "API: https://ваш-проект.railway.app/api/sync/order\n"
        "Ключ: margiana_sync_key_2024_secure_change_this\n\n"
        "Команды бота:\n"
        "/start - меню\n"
        "/orders - список заказов\n"
        "/help - эта справка",
        parse_mode=ParseMode.MARKDOWN
    )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок"""
    logger.error(f"Bot error: {context.error}")

def run_bot():
    """Запуск Telegram бота"""
    if not TOKEN:
        logger.error("❌ TELEGRAM_BOT_TOKEN не найден!")
        return
    
    try:
        app_bot = Application.builder().token(TOKEN).build()
        
        app_bot.add_handler(CommandHandler("start", start_command))
        app_bot.add_handler(CommandHandler("orders", orders_command))
        app_bot.add_handler(CommandHandler("help", help_command))
        app_bot.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, 
                                         lambda u, c: u.message.reply_text("Используйте /help")))
        
        app_bot.add_error_handler(error_handler)
        
        logger.info("🤖 Бот запущен")
        app_bot.run_polling()
        
    except Exception as e:
        logger.error(f"❌ Bot startup error: {e}")

def run_api():
    """Запуск API сервера"""
    port = int(os.getenv('PORT', 8000))
    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="info")
    server = uvicorn.Server(config)
    server.run()

def main():
    """Запуск всего"""
    # Запускаем API в отдельном потоке
    api_thread = threading.Thread(target=run_api, daemon=True)
    api_thread.start()
    
    logger.info("✅ API сервер запущен")
    
    # Даем время API запуститься
    import time
    time.sleep(2)
    
    # Запускаем бота в основном потоке
    logger.info("🤖 Запуск Telegram бота...")
    run_bot()

if __name__ == "__main__":
    main()
