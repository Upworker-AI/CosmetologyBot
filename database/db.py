import aiosqlite
from config import DATABASE_PATH
from datetime import datetime, timedelta
DATABASE_FILE = DATABASE_PATH

async def init_db():
    async with aiosqlite.connect(DATABASE_FILE) as db:
        with open("database/models.sql","r",encoding="utf-8") as file:
            schema = file.read()

        await db.executescript(schema)
        await db.commit()

async def get_categories():
    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row

        cursor = await db.execute(
            """
            SELECT category,  MIN(category_order) AS category_order
            FROM services
            WhERE is_active = 1
            GROUP BY category
            ORDER BY category_order, category
            """
        )
        rows = await cursor.fetchall()
        return rows

async def get_services_by_category(category: str):
    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row

        cursor = await db.execute(
            """
            SELECT id, title, price, duration_minutes
            FROM services
            WHERE category = ? AND is_active = 1
            ORDER BY sort_order, title
            """,
            (category,)
        )
        rows = await cursor.fetchall()
        return rows

async def get_service(service_id: int):
    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row

        cursor = await db.execute(
            """
            SELECT id, category, title, description, price, duration_minutes
            FROM services
            WHERE id = ? AND is_active = 1
            """,
            (service_id,)
        )
        row = await cursor.fetchone()
        return row

async def get_or_create_client(
    telegram_id: int,
    username: str | None,
    full_name: str | None,
    phone: str | None,
):
    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row

        cursor = await db.execute(
            """
            INSERT INTO clients
            (telegram_id, username, full_name, phone)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET
                username = excluded.username,
                full_name = excluded.full_name,
                phone = excluded.phone
            """,
            (telegram_id, username, full_name, phone)
        )
        await db.commit()

        cursor = await db.execute(
            """
            SELECT id
            FROM clients
            WHERE telegram_id = ?
            """,
            (telegram_id,)
        )
        client = await cursor.fetchone()

        return client["id"]


async def create_booking_request(
    client_id: int,
    client_telegram_id: int,
    service_id: int,
    preferred_date: str,
    preferred_time_slot: str,
    note: str | None,
    start_time: str | None = None,
    end_time: str | None = None,
):
    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row
        try:
            # Блокируем начало записи другими транзакциями.
            # Второй клиент будет ждать, пока первая заявка сохранится.
            await db.execute("BEGIN IMMEDIATE")

            # Для начала проверяем, что услуга существует.
            cursor = await db.execute(
                """
                SELECT duration_minutes
                FROM services
                WHERE id = ? AND is_active = 1
                """,
                (service_id,),
            )
            service = await cursor.fetchone()

            if service is None:
                raise ValueError("Услуга не найдена или неактивна.")

            # Для курсов дата и время могут уточняться отдельно.
            if preferred_date != "Дата уточняется":
                if not start_time or not end_time:
                    raise ValueError(
                        "Для записи необходимо указать время начала и окончания."
                    )

                # Поддерживаем оба формата даты.
                try:
                    date_obj = datetime.strptime(
                        preferred_date, "%d.%m.%Y"
                    ).date()
                except ValueError:
                    date_obj = datetime.strptime(
                        preferred_date, "%Y-%m-%d"
                    ).date()

                date_display = date_obj.strftime("%d.%m.%Y")
                date_iso = date_obj.isoformat()

                # Проверяем корректность времени.
                start_minutes = _to_minutes(start_time)
                end_minutes = _to_minutes(end_time)

                if end_minutes <= start_minutes:
                    raise ValueError("Время окончания должно быть позже начала.")

                duration = service["duration_minutes"]

                if end_minutes - start_minutes != duration:
                    raise ValueError(
                        "Продолжительность записи не совпадает с длительностью услуги."
                    )

                # Получаем время подготовки между клиентами.
                cursor = await db.execute(
                    """
                    SELECT preparation_minutes
                    FROM schedule_settings
                    WHERE id = 1
                    """
                )
                settings = await cursor.fetchone()
                preparation = (
                    settings["preparation_minutes"] if settings else 10
                )

                # Получаем все заявки, которые занимают время.
                cursor = await db.execute(
                    """
                    SELECT start_time, end_time
                    FROM booking_requests
                    WHERE preferred_date IN (?, ?)
                      AND status IN ('new', 'confirmed')
                      AND start_time IS NOT NULL
                      AND end_time IS NOT NULL
                    """,
                    (date_display, date_iso),
                )
                bookings = await cursor.fetchall()

                # Проверяем пересечение с каждой существующей записью.
                candidate_end = end_minutes + preparation

                for booking in bookings:
                    busy_start = _to_minutes(booking["start_time"])
                    busy_end = (
                        _to_minutes(booking["end_time"]) + preparation
                    )

                    if start_minutes < busy_end and busy_start < candidate_end:
                        raise ValueError(
                            "Это время уже занято. "
                            "Пожалуйста, выберите другое."
                        )

            # Если проверки пройдены, сохраняем заявку.
            cursor = await db.execute(
                """
                INSERT INTO booking_requests (
                    client_id,
                    client_telegram_id,
                    service_id,
                    preferred_date,
                    preferred_time_slot,
                    start_time,
                    end_time,
                    note
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    client_id,
                    client_telegram_id,
                    service_id,
                    preferred_date,
                    preferred_time_slot,
                    start_time,
                    end_time,
                    note,
                ),
            )

            booking_id = cursor.lastrowid
            await db.commit()

            return booking_id

        except Exception:
            await db.rollback()
            raise

async def update_booking_status(booking_id: int, status: str):
    async with aiosqlite.connect(DATABASE_FILE) as db:
        await db.execute(
            """
            UPDATE booking_requests
            SET status = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (status, booking_id)
        )
        await db.commit()

async def get_client_telegram_id(booking_id: int):
    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row

        cursor = await db.execute(
            """
            SELECT client_telegram_id
            FROM booking_requests
            WHERE id = ?
            """,
            (booking_id,)
        )
        row = await cursor.fetchone()
        return row["client_telegram_id"] if row else None

async def get_client_bookings(telegram_id: int):
    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row

        cursor = await db.execute(
            """
            SELECT
                br.id,
                br.preferred_date,
                br.preferred_time_slot,
                br.status,
                s.title AS service_title,
                s.price AS service_price
            FROM booking_requests br
            JOIN services s ON s.id = br.service_id
            WHERE br.client_telegram_id = ?
            ORDER BY br.created_at DESC
            LIMIT 10
            """,
            (telegram_id,)
        )

        return await cursor.fetchall()

async def get_client_by_telegram_id(telegram_id: int):
    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row

        cursor = await db.execute(
            """
            SELECT id, full_name, phone
            FROM clients
            WHERE telegram_id = ?
            """,
            (telegram_id,)
        )
        return await cursor.fetchone()


async def get_admin_bookings(
    status: str | None = None,
    service_id: int | None = None,
):
    """
    Возвращает заявки для админ-панели.
    status=None — заявки всех статусов.
    service_id=None — услуги всех типов.
    """
    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row

        query = """
            SELECT
                br.id,
                br.preferred_date,
                br.preferred_time_slot,
                br.status,
                br.note,
                br.created_at,
                br.client_telegram_id,
                c.full_name,
                c.phone,
                c.username,
                s.title AS service_title,
                s.price AS service_price,
                s.category AS service_category
            FROM booking_requests br
            LEFT JOIN clients c ON c.id = br.client_id
            LEFT JOIN services s ON s.id = br.service_id
            WHERE 1 = 1
        """
        params = []

        if status is not None:
            query += " AND br.status = ?"
            params.append(status)

        if service_id is not None:
            query += " AND br.service_id = ?"
            params.append(service_id)

        query += " ORDER BY br.created_at DESC, br.id DESC"

        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()

        # Даты записаны в формате ДД.ММ.ГГГГ,
        # поэтому сортируем их после преобразования.
        def sort_key(row):
            try:
                date_value = datetime.strptime(
                    row["preferred_date"], "%d.%m.%Y"
                )
            except (ValueError, TypeError):
                date_value = datetime.max

            return (date_value, row["preferred_time_slot"] or "")

        return sorted(rows, key=sort_key)


async def get_admin_booking_details(booking_id: int):
    """Возвращает полную карточку одной заявки."""
    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row

        cursor = await db.execute(
            """
            SELECT
                br.id,
                br.preferred_date,
                br.preferred_time_slot,
                br.status,
                br.note,
                br.created_at,
                br.updated_at,
                br.client_telegram_id,
                c.full_name,
                c.phone,
                c.username,
                s.title AS service_title,
                s.price AS service_price,
                s.category AS service_category,
                s.duration_minutes
            FROM booking_requests br
            LEFT JOIN clients c ON c.id = br.client_id
            LEFT JOIN services s ON s.id = br.service_id
            WHERE br.id = ?
            """,
            (booking_id,),
        )

        return await cursor.fetchone()


async def get_admin_services():
    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row

        cursor = await db.execute(
            """
            SELECT id, title, category
            FROM services
            ORDER BY category, title
            """
        )

        return await cursor.fetchall()



async def get_schedule_settings():
    """Получает настройки шага записи и времени подготовки."""
    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row

        cursor = await db.execute(
            """
            SELECT slot_step_minutes, preparation_minutes
            FROM schedule_settings
            WHERE id = 1
            """
        )
        row = await cursor.fetchone()

        if row is None:
            return {
                "slot_step_minutes": 15,
                "preparation_minutes": 10,
            }

        return dict(row)


async def get_working_hours(weekday: int):
    """Получает рабочие часы для дня недели."""
    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row

        cursor = await db.execute(
            """
            SELECT weekday, is_working, start_time, end_time
            FROM working_hours
            WHERE weekday = ?
            """,
            (weekday,),
        )
        row = await cursor.fetchone()

        return dict(row) if row else None

async def update_working_hours(
    weekday: int,
    is_working: int,
    start_time: str | None,
    end_time: str | None,
):
    """Создаёт или обновляет рабочие часы выбранного дня."""

    async with aiosqlite.connect(DATABASE_FILE) as db:
        await db.execute(
            """
            INSERT INTO working_hours (
                weekday,
                is_working,
                start_time,
                end_time
            )
            VALUES (?, ?, ?, ?)
            ON CONFLICT(weekday) DO UPDATE SET
                is_working = excluded.is_working,
                start_time = excluded.start_time,
                end_time = excluded.end_time
            """,
            (weekday, is_working, start_time, end_time),
        )

        await db.commit()


async def get_schedule_conflicts(
    weekday: int,
    is_working: int,
    start_time: str | None = None,
    end_time: str | None = None,
    check_break: bool = False,
    break_start: str | None = None,
    break_end: str | None = None,
    target_date: str | None = None,
):
    """
    Проверяет конфликты с будущими записями.

    check_break=False:
        Проверка изменения рабочих часов.

    check_break=True, target_date=None:
        Проверка еженедельного перерыва.
        Проверяются все будущие записи выбранного дня недели.

    check_break=True, target_date задана:
        Проверка разового перерыва.
        Проверяются записи только на выбранную дату.
    """

    today = datetime.now().date()

    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row

        # Получаем время подготовки после услуги
        cursor = await db.execute("""
            SELECT preparation_minutes
            FROM schedule_settings
            WHERE id = 1
        """)

        settings = await cursor.fetchone()

        preparation_minutes = (
            settings["preparation_minutes"]
            if settings else 10
        )

        # Получаем будущие активные записи
        cursor = await db.execute("""
            SELECT
                br.id,
                br.preferred_date,
                br.preferred_time_slot,
                br.start_time,
                br.end_time,
                br.status,
                c.full_name,
                s.title AS service_title
            FROM booking_requests br
            LEFT JOIN clients c ON c.id = br.client_id
            LEFT JOIN services s ON s.id = br.service_id
            WHERE br.status IN ('new', 'confirmed')
              AND br.preferred_date != 'Дата уточняется'
              AND br.start_time IS NOT NULL
              AND br.end_time IS NOT NULL
        """)

        bookings = await cursor.fetchall()

    conflicts = []

    # Преобразуем дату разового перерыва
    selected_date = None

    if check_break and target_date:
        selected_date = datetime.strptime(
            target_date, "%Y-%m-%d"
        ).date()

    # Преобразуем границы перерыва
    if check_break:
        if not break_start or not break_end:
            raise ValueError("Не указано время перерыва.")

        break_start_min = _to_minutes(break_start)
        break_end_min = _to_minutes(break_end)

        if break_end_min <= break_start_min:
            raise ValueError(
                "Окончание перерыва должно быть позже начала."
            )

    for booking in bookings:

        # Поддерживаем оба формата даты
        try:
            booking_date = datetime.strptime(
                booking["preferred_date"], "%d.%m.%Y"
            ).date()

        except (ValueError, TypeError):
            try:
                booking_date = datetime.strptime(
                    booking["preferred_date"], "%Y-%m-%d"
                ).date()

            except (ValueError, TypeError):
                continue

        # Прошедшие даты не проверяем
        if booking_date < today:
            continue

        # Проверка разового перерыва
        if check_break and selected_date is not None:
            if booking_date != selected_date:
                continue

        # Проверка еженедельного перерыва
        elif booking_date.weekday() != weekday:
            continue

        booking_start = _to_minutes(
            booking["start_time"]
        )

        booking_end = _to_minutes(
            booking["end_time"]
        )

        # -------------------------------
        # Проверка пересечения с перерывом
        # -------------------------------
        if check_break:

            # Учитываем подготовку после записи
            booking_end += preparation_minutes

            if (
                booking_start < break_end_min
                and booking_end > break_start_min
            ):
                conflicts.append(dict(booking))

            continue

        # -------------------------------
        # Проверка изменения рабочих часов
        # -------------------------------

        # Если день становится выходным,
        # любая активная запись конфликтует
        if not is_working:
            conflicts.append(dict(booking))
            continue

        if not start_time or not end_time:
            conflicts.append(dict(booking))
            continue

        work_start = _to_minutes(start_time)
        work_end = _to_minutes(end_time)

        if (
            booking_start < work_start
            or booking_end > work_end
        ):
            conflicts.append(dict(booking))

    return conflicts


async def get_working_breaks(weekday: int):
    """Получает регулярные перерывы для дня недели."""
    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row

        cursor = await db.execute(
            """
            SELECT id, start_time, end_time, title
            FROM working_breaks
            WHERE weekday = ?
            ORDER BY start_time
            """,
            (weekday,),
        )
        rows = await cursor.fetchall()

        return [dict(row) for row in rows]


async def get_date_breaks(date: str):
    """Получает перерывы для конкретной даты."""
    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row

        cursor = await db.execute(
            """
            SELECT id, start_time, end_time, title
            FROM date_breaks
            WHERE exception_date = ?
            ORDER BY start_time
            """,
            (date,),
        )
        rows = await cursor.fetchall()

        return [dict(row) for row in rows]


async def add_working_break(
    weekday: int,
    start_time: str,
    end_time: str,
    title: str = "Обед"
):
    # Проверяем корректность времени
    start = datetime.strptime(start_time, "%H:%M")
    end = datetime.strptime(end_time, "%H:%M")

    if end <= start:
        raise ValueError("Время окончания должно быть позже начала.")

    async with aiosqlite.connect(DATABASE_FILE) as db:
        # Проверяем пересечение с другими перерывами
        cursor = await db.execute(
            """
            SELECT id
            FROM working_breaks
            WHERE weekday = ?
              AND start_time < ?
              AND end_time > ?
            """,
            (weekday, end_time, start_time)
        )

        if await cursor.fetchone():
            raise ValueError("Этот перерыв пересекается с существующим.")

        cursor = await db.execute(
            """
            INSERT INTO working_breaks
                (weekday, start_time, end_time, title)
            VALUES (?, ?, ?, ?)
            """,
            (weekday, start_time, end_time, title)
        )

        await db.commit()
        return cursor.lastrowid


async def delete_working_break(break_id: int):
    async with aiosqlite.connect(DATABASE_FILE) as db:
        cursor = await db.execute(
            "DELETE FROM working_breaks WHERE id = ?",
            (break_id,)
        )

        await db.commit()
        return cursor.rowcount > 0


async def add_date_break(
    date: str,
    start_time: str,
    end_time: str,
    title: str = "Обед"
):
    # Проверяем дату и время
    datetime.strptime(date, "%Y-%m-%d")

    start = datetime.strptime(start_time, "%H:%M")
    end = datetime.strptime(end_time, "%H:%M")

    if end <= start:
        raise ValueError("Время окончания должно быть позже начала.")

    async with aiosqlite.connect(DATABASE_FILE) as db:
        cursor = await db.execute(
            """
            SELECT id
            FROM date_breaks
            WHERE exception_date = ?
              AND start_time < ?
              AND end_time > ?
            """,
            (date, end_time, start_time)
        )

        if await cursor.fetchone():
            raise ValueError("Этот перерыв пересекается с существующим.")

        cursor = await db.execute(
            """
            INSERT INTO date_breaks
                (exception_date, start_time, end_time, title)
            VALUES (?, ?, ?, ?)
            """,
            (date, start_time, end_time, title)
        )

        await db.commit()
        return cursor.lastrowid


async def delete_date_break(break_id: int):
    async with aiosqlite.connect(DATABASE_FILE) as db:
        cursor = await db.execute(
            "DELETE FROM date_breaks WHERE id = ?",
            (break_id,)
        )

        await db.commit()
        return cursor.rowcount > 0



def _to_minutes(value: str) -> int:
    """Переводит время HH:MM в минуты от начала суток."""
    hour, minute = map(int, value.split(":"))
    return hour * 60 + minute


def _to_time(minutes: int) -> str:
    """Переводит минуты от начала суток в HH:MM."""
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _ranges_overlap(
    start1: int,
    end1: int,
    start2: int,
    end2: int,
) -> bool:
    """Проверяет пересечение двух временных промежутков."""
    return start1 < end2 and start2 < end1


async def get_available_slots(
    selected_date: str,
    service_id: int,
) -> list[str]:

    try:
        date_obj = datetime.strptime(
            selected_date, "%d.%m.%Y"
        ).date()
    except ValueError:
        try:
            date_obj = datetime.strptime(
                selected_date, "%Y-%m-%d"
            ).date()
        except ValueError:
            raise ValueError(
                "Дата должна быть в формате ДД.ММ.ГГГГ "
                "или ГГГГ-ММ-ДД."
            )

    date_iso = date_obj.isoformat()
    date_display = date_obj.strftime("%d.%m.%Y")
    weekday = date_obj.weekday()

    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row

        # Получаем длительность услуги.
        cursor = await db.execute(
            """
            SELECT duration_minutes
            FROM services
            WHERE id = ? AND is_active = 1
            """,
            (service_id,),
        )
        service = await cursor.fetchone()

        if not service:
            return []

        duration = service["duration_minutes"]

        if not duration or duration <= 0:
            return []

        # Получаем обычные рабочие часы.
        cursor = await db.execute(
            """
            SELECT is_working, start_time, end_time
            FROM working_hours
            WHERE weekday = ?
            """,
            (weekday,),
        )
        weekly_hours = await cursor.fetchone()

        # Получаем исключение для конкретной даты.
        cursor = await db.execute(
            """
            SELECT is_working, start_time, end_time
            FROM schedule_exceptions
            WHERE exception_date = ?
            """,
            (date_iso,),
        )
        exception = await cursor.fetchone()

        # Особая дата переопределяет обычный график.
        if exception:
            if not exception["is_working"]:
                return []

            work_start = exception["start_time"]
            work_end = exception["end_time"]
        else:
            if not weekly_hours or not weekly_hours["is_working"]:
                return []

            work_start = weekly_hours["start_time"]
            work_end = weekly_hours["end_time"]

        if not work_start or not work_end:
            return []

        work_start_min = _to_minutes(work_start)
        work_end_min = _to_minutes(work_end)

        if work_start_min >= work_end_min:
            return []

        # Получаем шаг слотов и время подготовки.
        cursor = await db.execute(
            """
            SELECT slot_step_minutes, preparation_minutes
            FROM schedule_settings
            WHERE id = 1
            """
        )
        settings = await cursor.fetchone()

        step = settings["slot_step_minutes"] if settings else 15
        preparation = (
            settings["preparation_minutes"] if settings else 10
        )

        if step <= 0 or preparation < 0:
            raise ValueError("Некорректные настройки расписания.")

        # Собираем все перерывы для дня недели.
        cursor = await db.execute(
            """
            SELECT start_time, end_time
            FROM working_breaks
            WHERE weekday = ?
            """,
            (weekday,),
        )
        breaks = await cursor.fetchall()

        # Добавляем перерывы, заданные для конкретной даты.
        cursor = await db.execute(
            """
            SELECT start_time, end_time
            FROM date_breaks
            WHERE exception_date = ?
            """,
            (date_iso,),
        )
        date_breaks = await cursor.fetchall()

        breaks = list(breaks) + list(date_breaks)

        break_ranges = [
            (_to_minutes(row["start_time"]),
             _to_minutes(row["end_time"]))
            for row in breaks
        ]

        # Получаем занятые интервалы активных заявок.
        # Учитываем только записи, у которых уже есть точное время.
        cursor = await db.execute(
            """
            SELECT start_time, end_time
            FROM booking_requests
            WHERE preferred_date IN (?, ?)
              AND status IN ('new', 'confirmed')
              AND start_time IS NOT NULL
              AND end_time IS NOT NULL
            """,
            (date_display, date_iso),
        )
        bookings = await cursor.fetchall()

    busy_ranges = []

    for booking in bookings:
        start = _to_minutes(booking["start_time"])
        end = _to_minutes(booking["end_time"])

        if start >= end:
            continue

        # После существующей записи резервируем время на подготовку.
        busy_ranges.append((start, end + preparation))

    # Формируем доступные варианты с заданным шагом.
    available = []
    candidate = work_start_min

    while candidate + duration <= work_end_min:
        appointment_end = candidate + duration
        blocked_end = appointment_end + preparation

        # Не разрешаем пересечение с перерывами.
        overlaps_break = any(
            _ranges_overlap(
                candidate,
                blocked_end,
                break_start,
                break_end,
            )
            for break_start, break_end in break_ranges
        )

        # Не разрешаем пересечение с другими заявками.
        overlaps_booking = any(
            _ranges_overlap(
                candidate,
                blocked_end,
                busy_start,
                busy_end,
            )
            for busy_start, busy_end in busy_ranges
        )

        if not overlaps_break and not overlaps_booking:
            available.append(_to_time(candidate))

        candidate += step

    return available

