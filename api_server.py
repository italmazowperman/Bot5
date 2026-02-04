import os
import logging
from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from datetime import datetime
from pydantic import BaseModel
from typing import Optional
from dotenv import load_dotenv
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

# Создаем FastAPI приложение
app = FastAPI(title="Margiana Logistics API")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Подключение к Supabase
def get_db_connection():
    try:
        database_url = os.getenv('DATABASE_URL')
        if not database_url:
            database_url = "postgresql://postgres.neypmeacztdapjfrnzgu:margiana0011@aws-1-eu-north-1.pooler.supabase.com:6543/postgres"
        
        conn = psycopg2.connect(database_url, cursor_factory=RealDictCursor)
        return conn
    except Exception as e:
        logger.error(f"Database connection error: {e}")
        return None

# API ключ
API_KEY = os.getenv('SYNC_API_KEY', 'margiana_sync_key_2024_secure_change_this')

# Модели данных
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

# Проверка API ключа
def verify_api_key(api_key: str = Header(None, alias="api-key")):
    if not api_key or api_key != API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")
    return api_key

# Эндпоинты
@app.get("/")
async def root():
    return {"status": "ok", "service": "Margiana Logistics API"}

@app.get("/api/health")
async def health_check():
    return {"status": "ok"}

@app.get("/api/test-db")
async def test_db():
    try:
        conn = get_db_connection()
        if not conn:
            return {"status": "error", "message": "No database connection"}
        
        cursor = conn.cursor()
        cursor.execute("SELECT version()")
        version = cursor.fetchone()
        cursor.close()
        conn.close()
        
        return {"status": "success", "version": version['version']}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/sync/order")
async def sync_order(order_data: OrderSyncData, api_key: str = Depends(verify_api_key)):
    try:
        logger.info(f"Syncing order: {order_data.order_number}")
        
        conn = get_db_connection()
        if not conn:
            raise HTTPException(status_code=500, detail="Database connection failed")
        
        cursor = conn.cursor()
        
        # Проверяем существование заказа
        cursor.execute("SELECT id FROM orders WHERE order_number = %s", (order_data.order_number,))
        existing = cursor.fetchone()
        
        if existing:
            # Обновляем
            update_query = """
            UPDATE orders SET
                client_name = %s, container_count = %s, goods_type = %s,
                route = %s, transit_port = %s, document_number = %s,
                chinese_transport_company = %s, iranian_transport_company = %s,
                status = %s, status_color = %s, creation_date = %s,
                loading_date = %s, departure_date = %s, arrival_iran_date = %s,
                truck_loading_date = %s, arrival_turkmenistan_date = %s,
                client_receiving_date = %s, arrival_notice_date = %s,
                tkm_date = %s, eta_date = %s, has_loading_photo = %s,
                has_local_charges = %s, has_tex = %s, notes = %s,
                additional_info = %s, sync_timestamp = NOW(), last_modified = NOW()
            WHERE order_number = %s RETURNING id
            """
            
            cursor.execute(update_query, (
                order_data.client_name, order_data.container_count, order_data.goods_type,
                order_data.route, order_data.transit_port, order_data.document_number,
                order_data.chinese_transport_company, order_data.iranian_transport_company,
                order_data.status, order_data.status_color, order_data.creation_date,
                order_data.loading_date, order_data.departure_date, order_data.arrival_iran_date,
                order_data.truck_loading_date, order_data.arrival_turkmenistan_date,
                order_data.client_receiving_date, order_data.arrival_notice_date,
                order_data.tkm_date, order_data.eta_date, order_data.has_loading_photo,
                order_data.has_local_charges, order_data.has_tex, order_data.notes,
                order_data.additional_info, order_data.order_number
            ))
        else:
            # Создаем новый
            insert_query = """
            INSERT INTO orders (
                order_number, client_name, container_count, goods_type, route,
                transit_port, document_number, chinese_transport_company,
                iranian_transport_company, status, status_color, creation_date,
                loading_date, departure_date, arrival_iran_date, truck_loading_date,
                arrival_turkmenistan_date, client_receiving_date, arrival_notice_date,
                tkm_date, eta_date, has_loading_photo, has_local_charges, has_tex,
                notes, additional_info, sync_timestamp, last_modified
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW()
            ) RETURNING id
            """
            
            cursor.execute(insert_query, (
                order_data.order_number, order_data.client_name, order_data.container_count,
                order_data.goods_type, order_data.route, order_data.transit_port,
                order_data.document_number, order_data.chinese_transport_company,
                order_data.iranian_transport_company, order_data.status, order_data.status_color,
                order_data.creation_date, order_data.loading_date, order_data.departure_date,
                order_data.arrival_iran_date, order_data.truck_loading_date,
                order_data.arrival_turkmenistan_date, order_data.client_receiving_date,
                order_data.arrival_notice_date, order_data.tkm_date, order_data.eta_date,
                order_data.has_loading_photo, order_data.has_local_charges, order_data.has_tex,
                order_data.notes, order_data.additional_info
            ))
        
        order_id = cursor.fetchone()['id']
        conn.commit()
        cursor.close()
        conn.close()
        
        logger.info(f"Order {order_data.order_number} synced successfully")
        
        return {
            "status": "success",
            "message": "Order synced",
            "order_number": order_data.order_number,
            "order_id": order_id
        }
        
    except Exception as e:
        logger.error(f"Error in sync_order: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/orders")
async def get_orders(limit: int = 100, api_key: str = Depends(verify_api_key)):
    try:
        conn = get_db_connection()
        if not conn:
            raise HTTPException(status_code=500, detail="Database connection failed")
        
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM orders ORDER BY creation_date DESC LIMIT %s", (limit,))
        orders = cursor.fetchall()
        cursor.close()
        conn.close()
        
        return {"status": "success", "count": len(orders), "orders": orders}
        
    except Exception as e:
        logger.error(f"Error in get_orders: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    port = int(os.getenv('PORT', 8000))
    logger.info(f"Starting API server on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
