CREATE TABLE IF NOT EXISTS clients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER UNIQUE NOT NULL,
    username TEXT,
    full_name TEXT,
    phone TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS services (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    price TEXT NOT NULL,
    duration_minutes INTEGER,
    is_active INTEGER DEFAULT 1,
    sort_order INTEGER DEFAULT 0,
    category_order INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS booking_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id INTEGER NOT NULL REFERENCES clients(id),
    client_telegram_id INTEGER,
    service_id INTEGER NOT NULL REFERENCES services(id),
    preferred_date TEXT NOT NULL,
    preferred_time_slot TEXT NOT NULL,
    start_time TEXT,
    end_time TEXT,
    note TEXT,
    status TEXT NOT NULL DEFAULT 'new',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS admins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER UNIQUE NOT NULL,
    name TEXT,
    role TEXT DEFAULT 'owner'
);



-- Рабочие часы на каждый день недели.
-- weekday: 0 — понедельник, 6 — воскресенье.
CREATE TABLE IF NOT EXISTS working_hours (
    weekday INTEGER PRIMARY KEY CHECK (weekday BETWEEN 0 AND 6),
    is_working INTEGER NOT NULL DEFAULT 0,
    start_time TEXT,
    end_time TEXT
);

-- Перерывы, повторяющиеся каждую неделю.
CREATE TABLE IF NOT EXISTS working_breaks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    weekday INTEGER NOT NULL CHECK (weekday BETWEEN 0 AND 6),
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    title TEXT
);

-- Особые даты: выходной или изменённые рабочие часы.
CREATE TABLE IF NOT EXISTS schedule_exceptions (
    exception_date TEXT PRIMARY KEY,
    is_working INTEGER NOT NULL DEFAULT 0,
    start_time TEXT,
    end_time TEXT,
    note TEXT
);

-- Перерывы, действующие только в конкретную дату.
CREATE TABLE IF NOT EXISTS date_breaks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    exception_date TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    title TEXT
);

-- Общие настройки расчёта времени.
CREATE TABLE IF NOT EXISTS schedule_settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    slot_step_minutes INTEGER NOT NULL DEFAULT 15,
    preparation_minutes INTEGER NOT NULL DEFAULT 10
);

-- Начальные настройки: шаг 15 минут, подготовка 10 минут.
INSERT OR IGNORE INTO schedule_settings (
    id,
    slot_step_minutes,
    preparation_minutes
)
VALUES (1, 15, 10);

-- Создаём настройки для всех дней недели.
-- Пока рабочие дни не включены: их нужно будет настроить.
INSERT OR IGNORE INTO working_hours (
    weekday,
    is_working,
    start_time,
    end_time
)
VALUES
    (0, 1, "09:00", "15:00"),
    (1, 0, NULL, NULL),
    (2, 0, NULL, NULL),
    (3, 0, NULL, NULL),
    (4, 0, NULL, NULL),
    (5, 0, NULL, NULL),
    (6, 0, NULL, NULL);

INSERT INTO working_breaks(
    weekday,
    start_time,
    end_time,
    title
)
VALUES (
    0,
    "13:00",
    "14:00",
    "Обед"
);