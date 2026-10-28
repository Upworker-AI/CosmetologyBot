import asyncio

from database.db import init_db
import aiosqlite

from config import DATABASE_PATH

SERVICES = [
    ("Уход за лицом", "Ультразвуковая чистка", "Глубокое очищение пор и обновление кожи", "1 000 ₽", 90, 1),
    ("Уход за лицом", "Классический массаж лица", "Расслабление и лимфа", "700 ₽", 60, 2),
    ("Уход за лицом", "Массаж по Жаке", "Интенсивный и ритмичный, настоящая тренировка для лица", "600 ₽", 50, 3),
    ("Курс", "Курс массажа из 5 сеансов", "Мягкий старт, первые изменения", "3 200 ₽", 5 * 60, 1),
    ("Курс", "Курс массажа из 10 сеансов", "Глубокий и устойчивый результат", "6 000 ₽", 10 * 60, 2),
    ("Консультации", "Первичная консультация", "Осмотр и подбор программы ухода", "500 ₽", 30, 1),
]

async def seed_services():
    await init_db()

    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.executemany(
            """
            INSERT INTO services
            (category, title, description, price, duration_minutes, sort_order) 
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            SERVICES
        )
        await db.commit()

    print("Услуги добавлены.")

if __name__ == "__main__":
    asyncio.run(seed_services())
