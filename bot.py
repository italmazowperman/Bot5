import os
import logging
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)
from supabase import create_client, Client
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer
from reportlab.lib import colors
from reportlab.lib.units import cm

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Конфигурация
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://your-project.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "your-supabase-key")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "your-telegram-bot-token")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x]

# Инициализация Supabase
try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    logger.info("Supabase client initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize Supabase: {e}")
    supabase = None

# Команды бота
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user = update.effective_user
    
    welcome_text = f"""
👋 Привет, {user.first_name}!

Я - бот для отслеживания логистических заказов компании Margiana Logistic Services.

📋 **Доступные команды:**
/orders - Список активных заказов
/completed - Завершенные заказы (последние 30 дней)
/status [статус] - Заказы по статусу
/missing_photos - Заказы без фото загрузки
/upcoming - Предстоящие события
/report - Получить отчет в PDF
/help - Помощь

🔔 Бот автоматически уведомляет о ключевых событиях.
"""
    
    await update.message.reply_text(welcome_text)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    help_text = """
📖 **Помощь по командам:**

**Основные команды:**
/orders - Показать активные заказы
/completed - Завершенные заказы за 30 дней
/status [статус] - Фильтр по статусу
    Пример: /status "In Transit CHN-IR"
/missing_photos - Заказы без фото загрузки
/upcoming - События на ближайшие 7 дней
/report - Создать PDF отчет

**Для администраторов:**
/stats - Статистика системы
/notify [текст] - Отправить уведомление всем пользователям
"""
    await update.message.reply_text(help_text)

async def show_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать активные заказы"""
    if not supabase:
        await update.message.reply_text("❌ Ошибка подключения к базе данных")
        return
    
    try:
        thirty_days_ago = (datetime.now() - timedelta(days=30)).isoformat()
        
        response = supabase.table("cloud_sync_log")\
            .select("*")\
            .neq("event_type", "ORDER_DELETED")\
            .gte("created_at", thirty_days_ago)\
            .order("created_at", desc=True)\
            .execute()
        
        if not response.data:
            await update.message.reply_text("📭 Активных заказов не найдено")
            return
        
        # Группируем по order_id
        orders_dict = {}
        for event in response.data:
            order_id = event.get('order_id')
            if order_id and order_id not in orders_dict:
                orders_dict[order_id] = event
        
        # Формируем сообщение
        message_lines = ["📋 **Активные заказы:**\n"]
        
        for idx, (order_id, latest_event) in enumerate(list(orders_dict.items())[:10], 1):
            event_data = latest_event.get('event_data', {})
            
            if isinstance(event_data, str):
                try:
                    event_data = json.loads(event_data)
                except:
                    event_data = {}
            
            order_info = f"""
{idx}. **Заказ #{latest_event.get('order_number', order_id)}**
   👤 Клиент: {event_data.get('client', 'Не указан')}
   📦 Контейнеров: {event_data.get('containers', 0)}
   📍 Статус: {event_data.get('status', 'Неизвестен')}
   🕐 Обновлен: {latest_event.get('created_at', '')[:10]}
"""
            message_lines.append(order_info)
        
        if len(orders_dict) > 10:
            message_lines.append(f"\n... и еще {len(orders_dict) - 10} заказов")
        
        full_message = "\n".join(message_lines)
        await update.message.reply_text(full_message, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Ошибка получения заказов: {e}")
        await update.message.reply_text("❌ Ошибка при получении данных")

async def show_completed_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать завершенные заказы за 30 дней"""
    if not supabase:
        await update.message.reply_text("❌ Ошибка подключения к базе данных")
        return
    
    try:
        thirty_days_ago = (datetime.now() - timedelta(days=30)).isoformat()
        
        response = supabase.table("cloud_sync_log")\
            .select("*")\
            .gte("created_at", thirty_days_ago)\
            .order("created_at", desc=True)\
            .execute()
        
        if not response.data:
            await update.message.reply_text("✅ Нет завершенных заказов за последние 30 дней")
            return
        
        # Ищем заказы со статусом Completed
        completed_orders = []
        for event in response.data:
            event_data = event.get('event_data', '{}')
            if isinstance(event_data, str):
                if '"status":"Completed"' in event_data:
                    completed_orders.append(event)
            elif isinstance(event_data, dict):
                if event_data.get('status') == 'Completed':
                    completed_orders.append(event)
        
        if not completed_orders:
            await update.message.reply_text("✅ Нет завершенных заказов за последние 30 дней")
            return
        
        message_lines = ["✅ **Завершенные заказы (30 дней):**\n"]
        
        for idx, event in enumerate(completed_orders[:10], 1):
            event_data = event.get('event_data', {})
            if isinstance(event_data, str):
                try:
                    event_data = json.loads(event_data)
                except:
                    event_data = {}
            
            order_info = f"""
{idx}. **#{event.get('order_number', event.get('order_id', 'N/A'))}**
   👤 {event_data.get('client', 'Клиент')}
   📅 {event.get('created_at', '')[:10]}
"""
            message_lines.append(order_info)
        
        if len(completed_orders) > 10:
            message_lines.append(f"\n... и еще {len(completed_orders) - 10} заказов")
        
        full_message = "\n".join(message_lines)
        await update.message.reply_text(full_message, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text("❌ Ошибка при получении данных")

async def filter_by_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Фильтр заказов по статусу"""
    if not supabase:
        await update.message.reply_text("❌ Ошибка подключения к базе данных")
        return
    
    if not context.args:
        await update.message.reply_text(
            "ℹ️ Использование: /status [статус]\n"
            "Пример: /status \"In Transit\"\n\n"
            "Доступные статусы:\n"
            "• New\n• In Progress\n• In Transit\n• Completed\n• Cancelled"
        )
        return
    
    status_query = " ".join(context.args)
    
    try:
        thirty_days_ago = (datetime.now() - timedelta(days=30)).isoformat()
        
        response = supabase.table("cloud_sync_log")\
            .select("*")\
            .gte("created_at", thirty_days_ago)\
            .order("created_at", desc=True)\
            .execute()
        
        if not response.data:
            await update.message.reply_text(f"📭 Заказов со статусом '{status_query}' не найдено")
            return
        
        # Фильтруем по статусу
        filtered_orders = []
        for event in response.data:
            event_data = event.get('event_data', '{}')
            if isinstance(event_data, str):
                if status_query.lower() in event_data.lower():
                    filtered_orders.append(event)
            elif isinstance(event_data, dict):
                if status_query.lower() in str(event_data.get('status', '')).lower():
                    filtered_orders.append(event)
        
        if not filtered_orders:
            await update.message.reply_text(f"📭 Заказов со статусом '{status_query}' не найдено")
            return
        
        message_lines = [f"🔍 **Заказы со статусом '{status_query}':**\n"]
        
        for idx, event in enumerate(filtered_orders[:10], 1):
            event_data = event.get('event_data', {})
            if isinstance(event_data, str):
                try:
                    event_data = json.loads(event_data)
                except:
                    event_data = {}
            
            order_info = f"""
{idx}. **#{event.get('order_number', event.get('order_id', 'N/A'))}**
   👤 {event_data.get('client', 'Клиент')}
   📅 {event.get('created_at', '')[:10]}
"""
            message_lines.append(order_info)
        
        if len(filtered_orders) > 10:
            message_lines.append(f"\n... и еще {len(filtered_orders) - 10} заказов")
        
        full_message = "\n".join(message_lines)
        await update.message.reply_text(full_message, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Ошибка фильтрации: {e}")
        await update.message.reply_text("❌ Ошибка при фильтрации")

async def show_missing_photos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать заказы без фото загрузки"""
    if not supabase:
        await update.message.reply_text("❌ Ошибка подключения к базе данных")
        return
    
    try:
        thirty_days_ago = (datetime.now() - timedelta(days=30)).isoformat()
        
        response = supabase.table("cloud_sync_log")\
            .select("*")\
            .gte("created_at", thirty_days_ago)\
            .order("created_at", desc=True)\
            .execute()
        
        if not response.data:
            await update.message.reply_text("📭 Данных не найдено")
            return
        
        # Ищем события с упоминанием фото
        orders_without_photos = []
        for event in response.data:
            event_data_str = str(event.get('event_data', ''))
            if 'photo' in event_data_str.lower() and ('missing' in event_data_str.lower() or 'false' in event_data_str.lower()):
                orders_without_photos.append(event)
        
        if not orders_without_photos:
            await update.message.reply_text("✅ Все заказы имеют фото загрузки!")
            return
        
        message_lines = ["📷 **Заказы без фото загрузки:**\n"]
        
        for idx, event in enumerate(orders_without_photos[:10], 1):
            event_data = event.get('event_data', {})
            if isinstance(event_data, str):
                try:
                    event_data = json.loads(event_data)
                except:
                    event_data = {}
            
            order_info = f"""
{idx}. **#{event.get('order_number', event.get('order_id', 'N/A'))}**
   👤 {event_data.get('client', 'Клиент')}
   📅 {event.get('created_at', '')[:10]}
"""
            message_lines.append(order_info)
        
        if len(orders_without_photos) > 10:
            message_lines.append(f"\n... и еще {len(orders_without_photos) - 10} заказов")
        
        full_message = "\n".join(message_lines)
        await update.message.reply_text(full_message, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text("❌ Ошибка при получении данных")

async def show_upcoming_events(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать предстоящие события"""
    if not supabase:
        await update.message.reply_text("❌ Ошибка подключения к базе данных")
        return
    
    try:
        today = datetime.now().date().isoformat()
        next_week = (datetime.now() + timedelta(days=7)).date().isoformat()
        
        response = supabase.table("cloud_sync_log")\
            .select("*")\
            .gte("created_at", today)\
            .lte("created_at", next_week)\
            .order("created_at")\
            .execute()
        
        if not response.data:
            await update.message.reply_text("📅 Нет предстоящих событий на ближайшую неделю")
            return
        
        message_lines = ["📅 **Предстоящие события (7 дней):**\n"]
        
        for event in response.data[:10]:
            event_data = event.get('event_data', {})
            if isinstance(event_data, str):
                try:
                    event_data = json.loads(event_data)
                except:
                    event_data = {}
            
            event_info = f"""
📌 **Заказ: #{event.get('order_number', event.get('order_id', 'N/A'))}**
   📅 Дата: {event.get('created_at', '')[:10]}
   📝 Тип: {event.get('event_type', 'Событие')}
"""
            message_lines.append(event_info)
        
        if len(response.data) > 10:
            message_lines.append(f"\n... и еще {len(response.data) - 10} событий")
        
        full_message = "\n".join(message_lines)
        await update.message.reply_text(full_message, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text("❌ Ошибка при получении данных")

async def generate_pdf_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Создать PDF отчет"""
    if not supabase:
        await update.message.reply_text("❌ Ошибка подключения к базе данных")
        return
    
    try:
        await update.message.reply_text("📊 Формирую отчет... Это займет несколько секунд.")
        
        # Создаем временный файл
        filename = f"/tmp/report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        
        # Создаем документ
        doc = SimpleDocTemplate(filename, pagesize=A4)
        story = []
        
        # Стили
        styles = getSampleStyleSheet()
        
        # Заголовок
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=16,
            textColor=colors.HexColor('#2C3E50'),
            spaceAfter=30
        )
        
        story.append(Paragraph("Margiana Logistic Services", title_style))
        story.append(Paragraph(f"Отчет от {datetime.now().strftime('%d.%m.%Y %H:%M')}", styles['Normal']))
        story.append(Spacer(1, 20))
        
        # Получаем данные
        thirty_days_ago = (datetime.now() - timedelta(days=30)).isoformat()
        
        response = supabase.table("cloud_sync_log")\
            .select("*")\
            .gte("created_at", thirty_days_ago)\
            .order("created_at", desc=True)\
            .execute()
        
        # Статистика
        total_events = len(response.data) if response.data else 0
        
        # Добавляем статистику
        story.append(Paragraph("Общая статистика:", styles['Heading2']))
        stats_data = [
            ["Показатель", "Значение"],
            ["Всего событий (30 дней)", str(total_events)],
            ["Сгенерирован", datetime.now().strftime('%d.%m.%Y %H:%M')]
        ]
        
        stats_table = Table(stats_data, colWidths=[10*cm, 6*cm])
        stats_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2C3E50')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        
        story.append(stats_table)
        story.append(Spacer(1, 30))
        
        # Последние события
        story.append(Paragraph("Последние события:", styles['Heading2']))
        
        events_data = [["Дата", "Тип события", "Заказ"]]
        
        for event in response.data[:15]:  # Последние 15 событий
            events_data.append([
                event.get('created_at', '')[:10],
                event.get('event_type', '')[:20],
                event.get('order_number', str(event.get('order_id', '')))[:15]
            ])
        
        events_table = Table(events_data, colWidths=[3*cm, 5*cm, 4*cm])
        events_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#34495E')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 8),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
            ('BACKGROUND', (0, 1), (-1, -1), colors.whitesmoke),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('FONTSIZE', (0, 1), (-1, -1), 7),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.lightgrey])
        ]))
        
        story.append(events_table)
        
        # Создаем PDF
        doc.build(story)
        
        # Отправляем файл пользователю
        with open(filename, 'rb') as file:
            await update.message.reply_document(
                document=file,
                caption=f"📄 Отчет от {datetime.now().strftime('%d.%m.%Y')}",
                filename=f"Отчет_{datetime.now().strftime('%d.%m.%Y')}.pdf"
            )
        
        # Удаляем временный файл
        os.remove(filename)
        
    except Exception as e:
        logger.error(f"Ошибка создания PDF: {e}")
        await update.message.reply_text("❌ Ошибка при создании отчета")

async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать статистику (только для администраторов)"""
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("⛔ Эта команда только для администраторов")
        return
    
    if not supabase:
        await update.message.reply_text("❌ Ошибка подключения к базе данных")
        return
    
    try:
        # Статистика событий
        response = supabase.table("cloud_sync_log").select("id", count="exact").execute()
        events_count = response.count if hasattr(response, 'count') else 0
        
        # Статистика за последние 7 дней
        week_ago = (datetime.now() - timedelta(days=7)).isoformat()
        weekly_response = supabase.table("cloud_sync_log")\
            .select("event_type")\
            .gte("created_at", week_ago)\
            .execute()
        
        weekly_stats = {}
        if weekly_response.data:
            for event in weekly_response.data:
                event_type = event.get('event_type', 'UNKNOWN')
                weekly_stats[event_type] = weekly_stats.get(event_type, 0) + 1
        
        # Формируем сообщение
        stats_text = f"""
📊 **Статистика системы:**

📈 **События:**
• Всего событий: {events_count}
• За последние 7 дней: {len(weekly_response.data) if weekly_response.data else 0}

📅 **Активность за неделю:**
"""
        
        for event_type, count in sorted(weekly_stats.items(), key=lambda x: x[1], reverse=True)[:10]:
            stats_text += f"• {event_type}: {count}\n"
        
        await update.message.reply_text(stats_text, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Ошибка статистики: {e}")
        await update.message.reply_text("❌ Ошибка при получении статистики")

async def send_notification(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправить уведомление всем пользователям (администратор)"""
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("⛔ Эта команда только для администраторов")
        return
    
    if not context.args:
        await update.message.reply_text("ℹ️ Использование: /notify [текст уведомления]")
        return
    
    notification_text = " ".join(context.args)
    
    try:
        # Здесь можно добавить логику отправки уведомлений
        # Пока просто подтвердим получение команды
        await update.message.reply_text(
            f"✅ Команда принята. Текст уведомления:\n\n{notification_text}"
        )
        
    except Exception as e:
        logger.error(f"Ошибка отправки уведомлений: {e}")
        await update.message.reply_text("❌ Ошибка при отправке уведомлений")

async def handle_unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик неизвестных команд"""
    await update.message.reply_text(
        "❓ Неизвестная команда. Используйте /help для списка команд."
    )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок"""
    logger.error(f"Ошибка при обработке обновления {update}: {context.error}")
    
    if update and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "❌ Произошла ошибка при обработке команды. Пожалуйста, попробуйте позже."
            )
        except:
            pass

def main():
    """Запуск бота"""
    if not TELEGRAM_TOKEN:
        logger.error("Токен Telegram бота не установлен!")
        return
    
    # Создаем приложение
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Добавляем обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("orders", show_orders))
    application.add_handler(CommandHandler("completed", show_completed_orders))
    application.add_handler(CommandHandler("status", filter_by_status))
    application.add_handler(CommandHandler("missing_photos", show_missing_photos))
    application.add_handler(CommandHandler("upcoming", show_upcoming_events))
    application.add_handler(CommandHandler("report", generate_pdf_report))
    application.add_handler(CommandHandler("stats", show_stats))
    application.add_handler(CommandHandler("notify", send_notification))
    
    # Обработчик неизвестных команд
    application.add_handler(MessageHandler(filters.COMMAND, handle_unknown))
    
    # Обработчик ошибок
    application.add_error_handler(error_handler)
    
    # Запускаем бота
    logger.info("Бот запущен...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()