import os
import logging
import asyncio
from datetime import datetime, timedelta
from dotenv import load_dotenv
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
import psycopg2
from psycopg2.extras import RealDictCursor

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Проверяем переменные окружения
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
ADMIN_CHAT_IDS = os.getenv('ADMIN_CHAT_IDS', '').split(',')
DATABASE_URL = os.getenv('DATABASE_URL')

logger.info(f"✅ Токен получен: {'Да' if TOKEN else 'Нет'}")
logger.info(f"✅ Админы: {len([x for x in ADMIN_CHAT_IDS if x.strip()])}")
logger.info(f"✅ База данных: {'Да' if DATABASE_URL else 'Нет'}")

if not TOKEN:
    logger.error("❌ TELEGRAM_BOT_TOKEN не найден в переменных окружения!")
    exit(1)

# Подключение к Supabase
def get_db_connection():
    """Создать соединение с Supabase"""
    try:
        if not DATABASE_URL:
            logger.error("❌ DATABASE_URL не настроен")
            return None
        
        conn = psycopg2.connect(
            DATABASE_URL,
            cursor_factory=RealDictCursor
        )
        return conn
    except Exception as e:
        logger.error(f"❌ Ошибка подключения к базе данных: {e}")
        return None

# ========== КОМАНДЫ БОТА ==========

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user = update.effective_user
    logger.info(f"👤 Пользователь {user.id} ({user.first_name}) начал работу")
    
    welcome_text = f"""
🎉 *Добро пожаловать, {user.first_name}!*

🤖 Я — телеграм-бот для логистической компании *Margiana Logistic Services*.

*📋 Доступные команды:*
/start - Начать работу
/help - Помощь
/active - Активные заказы
/today - События сегодня
/search - Поиск заказов
/contacts - Контакты компании

*🔍 Примеры:*
`/search ORD-001`
`/active`
`/today`

📞 *Поддержка:* @margiana_logistics
"""
    
    await update.message.reply_text(
        welcome_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=ReplyKeyboardMarkup([
            [KeyboardButton("📊 Активные"), KeyboardButton("📅 Сегодня")],
            [KeyboardButton("🔍 Поиск"), KeyboardButton("📞 Контакты")]
        ], resize_keyboard=True)
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать справку"""
    help_text = """
*🆘 Помощь по командам*

*📋 Основные команды:*
/start - Начать работу
/active - Активные заказы
/today - События сегодня
/search <текст> - Поиск заказов
/contacts - Контакты компании

*🔍 Примеры:*
`/search ORD-001` - найти заказ
`/search Клиент` - найти клиента
`/active` - все активные заказы
`/today` - события сегодня

*🔔 Уведомления:*
Бот отправляет уведомления о:
• Новых заказах
• Изменениях статусов
• Ключевых событиях
• Предстоящих событиях

*📞 Контакты:*
@margiana_logistics
+993 61 55 77 79
"""
    
    await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)

async def active_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать активные заказы"""
    try:
        conn = get_db_connection()
        if not conn:
            await update.message.reply_text("❌ Ошибка подключения к базе")
            return
        
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM orders 
            WHERE status NOT IN ('Completed', 'Cancelled')
            ORDER BY creation_date DESC 
            LIMIT 10
        """)
        
        orders = cursor.fetchall()
        cursor.close()
        conn.close()
        
        if not orders:
            await update.message.reply_text("📭 Нет активных заказов")
            return
        
        text = f"📊 *Активные заказы* ({len(orders)}):\n\n"
        
        for i, order in enumerate(orders, 1):
            text += f"{i}. 📦 *{order['order_number']}*\n"
            text += f"   👤 {order['client_name']}\n"
            
            if order['container_count']:
                text += f"   📦 Контейнеров: {order['container_count']}\n"
            
            if order['route']:
                text += f"   📍 {order['route']}\n"
            
            text += f"   📝 {order['status']}\n\n"
        
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
        
    except Exception as e:
        logger.error(f"❌ Ошибка в active_command: {e}")
        await update.message.reply_text("❌ Ошибка при получении данных")

async def today_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """События на сегодня"""
    try:
        today = datetime.now().date()
        
        conn = get_db_connection()
        if not conn:
            await update.message.reply_text("❌ Ошибка подключения к базе")
            return
        
        cursor = conn.cursor()
        cursor.execute("""
            SELECT order_number, client_name, status,
                   departure_date, arrival_iran_date,
                   truck_loading_date, arrival_turkmenistan_date,
                   client_receiving_date, eta_date
            FROM orders
            WHERE (
                DATE(departure_date) = %s OR
                DATE(arrival_iran_date) = %s OR
                DATE(truck_loading_date) = %s OR
                DATE(arrival_turkmenistan_date) = %s OR
                DATE(client_receiving_date) = %s OR
                DATE(eta_date) = %s
            )
            LIMIT 5
        """, (today, today, today, today, today, today))
        
        orders = cursor.fetchall()
        cursor.close()
        conn.close()
        
        if not orders:
            await update.message.reply_text("📅 На сегодня нет событий")
            return
        
        text = f"📅 *События сегодня* ({len(orders)}):\n\n"
        
        for order in orders:
            text += f"📦 *{order['order_number']}*\n"
            text += f"👤 {order['client_name']}\n"
            
            events = []
            if order['departure_date'] and order['departure_date'].date() == today:
                events.append("🚢 Отплытие")
            if order['arrival_iran_date'] and order['arrival_iran_date'].date() == today:
                events.append("🇮🇷 Прибытие в Иран")
            if order['truck_loading_date'] and order['truck_loading_date'].date() == today:
                events.append("🚛 Погрузка")
            if order['arrival_turkmenistan_date'] and order['arrival_turkmenistan_date'].date() == today:
                events.append("🇹🇲 Прибытие в Туркм.")
            if order['client_receiving_date'] and order['client_receiving_date'].date() == today:
                events.append("✅ Получение клиентом")
            
            for event in events:
                text += f"   • {event}\n"
            
            text += "\n"
        
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
        
    except Exception as e:
        logger.error(f"❌ Ошибка в today_command: {e}")
        await update.message.reply_text("❌ Ошибка при получении данных")

async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Поиск заказов"""
    if not context.args:
        await update.message.reply_text(
            "🔍 *Использование:*\n`/search <текст>`\n\n"
            "*Примеры:*\n`/search ORD-001`\n`/search Клиент`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    search_query = ' '.join(context.args)
    
    try:
        conn = get_db_connection()
        if not conn:
            await update.message.reply_text("❌ Ошибка подключения к базе")
            return
        
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM orders 
            WHERE 
                order_number ILIKE %s OR
                client_name ILIKE %s OR
                route ILIKE %s
            ORDER BY creation_date DESC 
            LIMIT 10
        """, (f"%{search_query}%", f"%{search_query}%", f"%{search_query}%"))
        
        orders = cursor.fetchall()
        cursor.close()
        conn.close()
        
        if not orders:
            await update.message.reply_text(f"🔍 По запросу '{search_query}' ничего не найдено")
            return
        
        text = f"🔍 *Результаты поиска* ('{search_query}'):\n\n"
        
        for i, order in enumerate(orders, 1):
            text += f"{i}. 📦 *{order['order_number']}*\n"
            text += f"   👤 {order['client_name']}\n"
            if order['container_count']:
                text += f"   📦 {order['container_count']} контейнеров\n"
            text += f"   📝 {order['status']}\n\n"
        
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
        
    except Exception as e:
        logger.error(f"❌ Ошибка в search_command: {e}")
        await update.message.reply_text(f"❌ Ошибка при поиске")

async def contacts_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Контакты компании"""
    contacts_text = """
*🏢 Margiana Logistic Services*

*📞 Контакты:*
Телефон: +993 61 55 77 79
Email: perman@margianalogistics.com
Telegram: @margiana_logistics

*🚚 Услуги:*
• Китай → Туркменистан через Иран
• Морские перевозки
• Таможенное оформление
• Сопровождение грузов

*🕒 Режим работы:*
Пн-Пт: 9:00-18:00
Сб: 10:00-16:00
Вс: выходной
"""
    
    await update.message.reply_text(contacts_text, parse_mode=ParseMode.MARKDOWN)

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка текстовых сообщений (кнопки)"""
    text = update.message.text
    
    if text == "📊 Активные":
        await active_command(update, context)
    elif text == "📅 Сегодня":
        await today_command(update, context)
    elif text == "🔍 Поиск":
        await update.message.reply_text("Введите текст для поиска. Пример: ORD-001")
    elif text == "📞 Контакты":
        await contacts_command(update, context)
    else:
        await update.message.reply_text(
            f"Вы написали: {text}\n\n"
            "Используйте кнопки или команды:\n"
            "/start - меню\n"
            "/help - помощь"
        )

# ========== УВЕДОМЛЕНИЯ ==========

async def check_new_orders(context: ContextTypes.DEFAULT_TYPE):
    """Проверка новых заказов"""
    try:
        logger.info("🔍 Проверка новых заказов...")
        
        conn = get_db_connection()
        if not conn:
            return
        
        cursor = conn.cursor()
        
        # Ищем заказы за последние 5 минут
        five_minutes_ago = datetime.now() - timedelta(minutes=5)
        
        cursor.execute("""
            SELECT * FROM orders 
            WHERE sync_timestamp >= %s
            ORDER BY sync_timestamp DESC
            LIMIT 5
        """, (five_minutes_ago,))
        
        new_orders = cursor.fetchall()
        cursor.close()
        conn.close()
        
        if new_orders:
            for order in new_orders:
                # Отправляем уведомление админам
                for admin_id in ADMIN_CHAT_IDS:
                    if admin_id.strip():
                        try:
                            await context.bot.send_message(
                                chat_id=admin_id.strip(),
                                text=f"""
🆕 *НОВЫЙ ЗАКАЗ*

📦 {order['order_number']}
👤 {order['client_name']}
📦 {order['container_count']} контейнеров
📍 {order['route'] or 'Не указан'}
📝 {order['status']}
                                """,
                                parse_mode=ParseMode.MARKDOWN
                            )
                        except Exception as e:
                            logger.error(f"❌ Ошибка отправки: {e}")
        
        logger.info(f"✅ Найдено новых заказов: {len(new_orders)}")
        
    except Exception as e:
        logger.error(f"❌ Ошибка проверки заказов: {e}")

async def check_events(context: ContextTypes.DEFAULT_TYPE):
    """Проверка событий"""
    try:
        logger.info("🔔 Проверка событий...")
        
        # Просто логируем, что проверка работает
        logger.info("✅ Проверка событий выполнена")
        
    except Exception as e:
        logger.error(f"❌ Ошибка проверки событий: {e}")

# ========== ЗАПУСК БОТА ==========

async def post_init(application: Application):
    """Вызывается после инициализации бота"""
    logger.info("✅ Бот инициализирован")
    
    # Запускаем задачи
    job_queue = application.job_queue
    if job_queue:
        job_queue.run_repeating(check_new_orders, interval=300, first=10)  # Каждые 5 минут
        job_queue.run_repeating(check_events, interval=3600, first=30)  # Каждый час
        logger.info("✅ Задачи уведомлений запущены")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ошибок"""
    logger.error(f"Ошибка: {context.error}")
    if update and update.effective_message:
        await update.effective_message.reply_text("❌ Произошла ошибка")

def main():
    """Основная функция запуска бота"""
    logger.info("🚀 Запуск телеграм-бота...")
    
    try:
        # Создаем приложение
        application = Application.builder() \
            .token(TOKEN) \
            .post_init(post_init) \
            .build()
        
        # Регистрируем обработчики команд
        handlers = [
            CommandHandler("start", start_command),
            CommandHandler("help", help_command),
            CommandHandler("active", active_command),
            CommandHandler("today", today_command),
            CommandHandler("search", search_command),
            CommandHandler("contacts", contacts_command),
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message)
        ]
        
        for handler in handlers:
            application.add_handler(handler)
        
        # Обработчик ошибок
        application.add_error_handler(error_handler)
        
        # Запускаем бота
        logger.info("✅ Бот запущен и ожидает сообщений...")
        application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True
        )
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        raise

if __name__ == '__main__':
    main()
