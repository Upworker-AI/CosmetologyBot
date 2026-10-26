import asyncio
import aiosqlite

from config import DATABASE_PATH


async def check_services():
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row

        cursor = await db.execute("SELECT * FROM services")
        rows = await cursor.fetchall()

        print(f"Всего услуг: {len(rows)}")

        for row in rows:
            print(
                f"{row['id']}. {row['category']} | "
                 "{row['title']} | {row['price']} | "
                 "{row['duration_minutes']} мин | порядок {row['sort_order']}"
            )


asyncio.run(check_services())