
import asyncio
import aiosqlite

from database.db import init_db
from config import DATABASE_PATH


SERVICES = [
    ("Уход за лицом", "Ультразвуковая чистка", "Глубокое очищение пор и обновление кожи", "1 000 ₽", 90, 1, 2),
    ("Уход за лицом", "Классический массаж лица", "Расслабление и лимфа", "700 ₽", 60, 2, 2),
    ("Уход за лицом", "Массаж по Жаке", "Интенсивный и ритмичный, настоящая тренировка для лица", "600 ₽", 50, 3, 2),
    ("Курс", "Курс массажа из 5 сеансов", "Мягкий старт, первые изменения", "3 200 ₽", 5 * 60, 1, 3),
    ("Курс", "Курс массажа из 10 сеансов", "Глубокий и устойчивый результат", "6 000 ₽", 10 * 60, 2, 3),
    ("Консультации", "Первичная консультация", "Осмотр и подбор программы ухода", "500 ₽", 30, 1, 1),
]


# Понедельник = 0, воскресенье = 6.
# Пример графика: понедельник–пятница 09:00–18:00,
# суббота и воскресенье — выходные.
WORKING_HOURS = [
    (0, 1, "09:00", "18:00"),  # Понедельник
    (1, 1, "09:00", "18:00"),  # Вторник
    (2, 1, "09:00", "18:00"),  # Среда
    (3, 1, "09:00", "18:00"),  # Четверг
    (4, 1, "09:00", "18:00"),  # Пятница
    (5, 0, None, None),        # Суббота
    (6, 0, None, None),        # Воскресенье
]


async def seed_services(db):
    """Добавляет услуги, не создавая дубликаты при повторном запуске."""
    for service in SERVICES:
        await db.execute(
            """
            INSERT INTO services (
                category,
                title,
                description,
                price,
                duration_minutes,
                sort_order,
                category_order
            )
            SELECT ?, ?, ?, ?, ?, ?, ?
            WHERE NOT EXISTS (
                SELECT 1
                FROM services
                WHERE category = ? AND title = ?
            )
            """,
            (*service, service[0], service[1])
        )


async def seed_schedule(db):
    """Заполняет начальные настройки расписания."""

    # Устанавливаем рабочие часы на все дни недели.
    # Важно: этот блок задаёт начальный график и перезаписывает
    # часы работы при каждом запуске seed.py.
    await db.executemany(
        """
        UPDATE working_hours
        SET is_working = ?,
            start_time = ?,
            end_time = ?
        WHERE weekday = ?
        """,
        [
            (is_working, start_time, end_time, weekday)
            for weekday, is_working, start_time, end_time
            in WORKING_HOURS
        ]
    )

    # Добавляем обед в понедельник, только если такого перерыва ещё нет.
    BREAKS = [
        (0, "13:00", "14:00", "Обед"),
        (1, "13:00", "14:00", "Обед"),
        (2, "13:00", "14:00", "Обед"),
        (3, "13:00", "14:00", "Обед"),
        (4, "13:00", "14:00", "Обед"),
        (5, "13:00", "15:00", "Обед"),
        (6, "13:00", "15:00", "Обед"),
    ]

    await db.executemany(
        """
        INSERT INTO working_breaks (
            weekday,
            start_time,
            end_time,
            title
        )
        SELECT ?, ?, ?, ?
        WHERE NOT EXISTS (
            SELECT 1
            FROM working_breaks
            WHERE weekday = ?
              AND start_time = ?
              AND end_time = ?
              AND title = ?
        )
        """,
        [
            (weekday, start_time, end_time, title,
             weekday, start_time, end_time, title)
            for weekday, start_time, end_time, title in BREAKS
        ]
    )

    # Настройки временных слотов.
    await db.execute(
        """
        INSERT OR IGNORE INTO schedule_settings (
            id,
            slot_step_minutes,
            preparation_minutes
        )
        VALUES (1, 15, 10)
        """
    )


async def main():
    # Создаём таблицы, если их ещё нет.
    await init_db()

    async with aiosqlite.connect(DATABASE_PATH) as db:
        await seed_services(db)
        await seed_schedule(db)
        await db.commit()

    print("Услуги и начальное расписание добавлены.")


if __name__ == "__main__":
    asyncio.run(main())
