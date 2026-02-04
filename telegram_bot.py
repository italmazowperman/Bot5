import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
import psycopg2
from datetime import datetime
import pytz
from dotenv import load_dotenv
import pdfkit

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Подключение к базе данных
def get_db_connection():
    DATABASE_URL = os.getenv('DATABASE_URL')
    return psycopg2.connect(DATABASE_URL)

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    welcome_text = f"""
Привет, {user.first_name}! 👋

Я - бот Margiana Logistics для отслеживания грузов.

Доступные команды:
/orders - Список активных заказов
/status [номер] - Статус заказа
/report - Отчет в формате PDF
/alerts - Настройка уведомлений
/help - Помощь
    """
    await update.message.reply_text(welcome_text)

# Получить список заказов
async def get_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT order_number, client_name, status, tkm_date 
        FROM orders 
        WHERE status NOT IN ('Completed', 'Cancelled')
        ORDER BY creation_date DESC
        LIMIT 10
    """)
    
    orders = cur.fetchall()
    cur.close()
    conn.close()
    
    if not orders:
        await update.message.reply_text("Нет активных заказов.")
        return
    
    response = "📦 *Активные заказы:*\n\n"
    for order in orders:
        order_num, client, status, tkm_date = order
        tkm_info = f" | TKM: {tkm_date.strftime('%d.%m.%Y')}" if tkm_date else ""
        response += f"• *{order_num}* - {client}\n"
        response += f"  Статус: {status}{tkm_info}\n"
        response += f"  /status_{order_num.replace('-', '_')}\n\n"
    
    await update.message.reply_text(response, parse_mode='Markdown')

# Получить статус конкретного заказа
async def get_order_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    order_number = ' '.join(context.args)
    if not order_number:
        await update.message.reply_text("Укажите номер заказа: /status ORD-001")
        return
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT o.*, 
               COUNT(c.id) as container_count,
               STRING_AGG(c.container_number, ', ') as containers
        FROM orders o
        LEFT JOIN containers c ON o.id = c.order_id
        WHERE o.order_number = %s
        GROUP BY o.id
    """, (order_number,))
    
    order = cur.fetchone()
    cur.close()
    conn.close()
    
    if not order:
        await update.message.reply_text(f"Заказ {order_number} не найден.")
        return
    
    # Формируем ответ
    response = f"""
📋 *Заказ {order[1]}*

👤 Клиент: {order[2]}
📦 Контейнеров: {order[18] or 0}
🚚 Маршрут: {order[4]}
🏷️ Статус: {order[10]}
🎨 Цвет статуса: {order[11]}

📅 Даты:
• Создан: {order[12].strftime('%d.%m.%Y') if order[12] else '—'}
• ATD: {order[14].strftime('%d.%m.%Y') if order[14] else '—'}
• ETA: {order[25].strftime('%d.%m.%Y') if order[25] else '—'}
• Прибытие в Иран: {order[15].strftime('%d.%m.%Y') if order[15] else '—'}
• TKM: {order[22].strftime('%d.%m.%Y') if order[22] else '—'}

📝 Примечания: {order[27] or 'нет'}
    """
    
    if order[29]:  # контейнеры
        response += f"\n🚢 Контейнеры: {order[29]}"
    
    await update.message.reply_text(response, parse_mode='Markdown')

# Генерация PDF отчета
async def generate_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Получаем данные для отчета
        cur.execute("""
            SELECT 
                o.order_number,
                o.client_name,
                o.document_number,
                o.goods_type,
                COUNT(c.id) as container_count,
                SUM(c.weight) as total_weight,
                o.status,
                o.tkm_date,
                o.arrival_notice_date,
                o.has_loading_photo,
                o.has_local_charges,
                o.has_tex,
                STRING_AGG(c.container_number, ', ') as containers
            FROM orders o
            LEFT JOIN containers c ON o.id = c.order_id
            WHERE o.status NOT IN ('Cancelled')
            GROUP BY o.id
            ORDER BY o.order_number
        """)
        
        orders = cur.fetchall()
        cur.close()
        conn.close()
        
        # Генерируем HTML для PDF
        html_content = generate_html_report(orders)
        
        # Создаем PDF
        pdf_filename = f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        pdfkit.from_string(html_content, pdf_filename)
        
        # Отправляем PDF
        with open(pdf_filename, 'rb') as pdf_file:
            await update.message.reply_document(
                document=pdf_file,
                caption="📊 Отчет по заказам"
            )
        
        # Удаляем временный файл
        os.remove(pdf_filename)
        
    except Exception as e:
        logger.error(f"Error generating report: {e}")
        await update.message.reply_text("Ошибка при генерации отчета.")

def generate_html_report(orders):
    html = """
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; }
            h1 { color: #2C3E50; text-align: center; }
            table { width: 100%; border-collapse: collapse; margin-top: 20px; }
            th { background-color: #2C3E50; color: white; padding: 10px; text-align: left; }
            td { padding: 8px; border: 1px solid #ddd; }
            tr:nth-child(even) { background-color: #f2f2f2; }
            .status-active { color: green; font-weight: bold; }
            .status-completed { color: blue; }
            .checkbox { font-weight: bold; }
            .check-yes { color: green; }
            .check-no { color: red; }
        </style>
    </head>
    <body>
        <h1>Margiana Logistics - Отчет по заказам</h1>
        <p>Сгенерировано: """ + datetime.now().strftime('%d.%m.%Y %H:%M') + """</p>
        <table>
            <tr>
                <th>№ Заказа</th>
                <th>Клиент</th>
                <th>BL №</th>
                <th>Груз</th>
                <th>Конт.</th>
                <th>Вес (кг)</th>
                <th>Статус</th>
                <th>TKM</th>
                <th>AN</th>
                <th>Фото</th>
                <th>Расходы</th>
                <th>TLX</th>
            </tr>
    """
    
    for order in orders:
        photo_check = "✓" if order[9] else "✗"
        charges_check = "✓" if order[10] else "✗"
        tex_check = "✓" if order[11] else "✗"
        
        tkm_date = order[7].strftime('%d.%m.%Y') if order[7] else ""
        an_date = order[8].strftime('%d.%m.%Y') if order[8] else ""
        
        html += f"""
            <tr>
                <td>{order[0]}</td>
                <td>{order[1]}</td>
                <td>{order[2] or ''}</td>
                <td>{order[3] or ''}</td>
                <td>{order[4]}</td>
                <td>{order[5] or 0}</td>
                <td class="status-{order[6].lower()}">{order[6]}</td>
                <td>{tkm_date}</td>
                <td>{an_date}</td>
                <td class="checkbox {'check-yes' if order[9] else 'check-no'}">{photo_check}</td>
                <td class="checkbox {'check-yes' if order[10] else 'check-no'}">{charges_check}</td>
                <td class="checkbox {'check-yes' if order[11] else 'check-no'}">{tex_check}</td>
            </tr>
        """
    
    html += """
        </table>
    </body>
    </html>
    """
    
    return html

# Уведомления об изменениях
async def check_updates(context: ContextTypes.DEFAULT_TYPE):
    """Проверка изменений и отправка уведомлений"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Проверяем последние изменения (последний час)
        cur.execute("""
            SELECT o.order_number, o.status, o.tkm_date, 
                   o.updated_at, o.client_name
            FROM orders o
            WHERE o.updated_at > NOW() - INTERVAL '1 hour'
            ORDER BY o.updated_at DESC
        """)
        
        updates = cur.fetchall()
        cur.close()
        conn.close()
        
        if updates:
            for update in updates:
                message = f"""
🔄 *Обновление заказа!*

📦 Заказ: {update[0]}
👤 Клиент: {update[4]}
🔄 Новый статус: {update[1]}
📅 TKM дата: {update[2].strftime('%d.%m.%Y') if update[2] else 'не задана'}
⏰ Обновлено: {update[3].strftime('%H:%M')}
                """
                
                # Отправляем уведомления подписанным пользователям
                # Здесь нужно добавить логику для отправки конкретным пользователям
                
    except Exception as e:
        logger.error(f"Error checking updates: {e}")

# Настройка уведомлений
async def setup_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [
            InlineKeyboardButton("Новые заказы", callback_data="alert_new"),
            InlineKeyboardButton("Изменения статуса", callback_data="alert_status")
        ],
        [
            InlineKeyboardButton("TKM обновления", callback_data="alert_tkm"),
            InlineKeyboardButton("Все уведомления", callback_data="alert_all")
        ],
        [
            InlineKeyboardButton("Отключить все", callback_data="alert_none")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Выберите тип уведомлений:",
        reply_markup=reply_markup
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith("alert_"):
        alert_type = query.data.replace("alert_", "")
        await query.edit_message_text(f"✅ Уведомления '{alert_type}' настроены!")

# Команда помощи
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
📚 *Помощь по командам:*

/start - Начало работы
/orders - Список активных заказов (последние 10)
/status [номер] - Детальная информация по заказу
/report - Полный отчет в PDF
/alerts - Настройка уведомлений
/help - Эта справка

*Примеры:*
/status ORD-001 - информация по заказу ORD-001
/orders - список активных заказов

*По вопросам:* 
perman@margianalogistics.com
    """
    await update.message.reply_text(help_text, parse_mode='Markdown')

# Основная функция
def main():
    # Загрузка токена бота
    TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    if not TOKEN:
        raise ValueError("Не указан TELEGRAM_BOT_TOKEN в переменных окружения")
    
    # Создание приложения
    application = Application.builder().token(TOKEN).build()
    
    # Регистрация обработчиков команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("orders", get_orders))
    application.add_handler(CommandHandler("status", get_order_status))
    application.add_handler(CommandHandler("report", generate_report))
    application.add_handler(CommandHandler("alerts", setup_alerts))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # Настройка периодических задач (проверка обновлений каждые 5 минут)
    job_queue = application.job_queue
    job_queue.run_repeating(check_updates, interval=300, first=10)
    
    # Запуск бота
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
