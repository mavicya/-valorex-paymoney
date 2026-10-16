# 🤖 Affiliate & Earn Bot — Повний Гайд

---

## 📁 Структура проекту

```
affiliate_bot/
├── main.py                        ← Точка входу, збирає все разом
├── config.py                      ← Всі налаштування через .env
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── .env.example                   ← Шаблон змінних середовища
│
├── database/
│   ├── models.py                  ← ORM-моделі (User, Task, VIPSubscription, …)
│   └── engine.py                  ← AsyncEngine + session factory
│
├── services/
│   └── vip_service.py             ← Бізнес-логіка VIP (activate / revoke / expire)
│
└── bot/
    ├── states.py                  ← Всі FSM-стани (TaskFlow, WithdrawFlow, …)
    ├── middlewares/
    │   └── auth.py                ← Авто-реєстрація юзера, блок banned
    ├── keyboards/
    │   ├── main_menu.py           ← Reply-клавіатура головного меню
    │   └── vip.py                 ← Inline-клавіатури VIP
    ├── handlers/
    │   ├── start.py               ← /start + обробка реферального посилання
    │   ├── tasks.py               ← 📋 Завдання + FSM підтвердження
    │   ├── vip.py                 ← ⭐ VIP Завдання + оплата Stars/balance
    │   ├── profile.py             ← 👤 Профіль + VIP-таймер
    │   ├── withdrawals.py         ← 💳 Вивід коштів (FSM)
    │   └── admin.py               ← Адмін-команди + верифікація завдань
    └── utils/
        └── scheduler.py           ← APScheduler — скидання прострочених VIP
```

---

## ⚙️ Крок 1 — Отримати Bot Token

1. Відкрийте [@BotFather](https://t.me/BotFather) у Telegram.
2. Відправте `/newbot`, задайте ім'я та username.
3. Скопіюйте токен виду `7123456789:AAF...`.

---

## ⚙️ Крок 2 — Налаштувати .env

```bash
cp .env.example .env
```

Відкрийте `.env` та заповніть:

```env
BOT_TOKEN=7123456789:AAF...         # Токен від BotFather
ADMIN_IDS=[123456789]               # Ваш Telegram ID (знайти: @userinfobot)

DB_URL=postgresql+asyncpg://postgres:password@db:5432/affiliate_bot
REDIS_URL=redis://redis:6379/0
```

VIP-ціни вже виставлені за замовчуванням — змінюйте за потреби.

---

## 🐳 Крок 3 — Запуск через Docker (рекомендовано)

```bash
docker compose up --build -d
```

Це підніме три контейнери: **PostgreSQL**, **Redis**, **Bot**.

Перевірити логи:
```bash
docker compose logs -f bot
```

---

## 🐍 Крок 4 — Або ручний запуск (без Docker)

**Вимоги:** Python 3.11+, PostgreSQL 14+, Redis 7+

```bash
# 1. Встановити залежності
pip install -r requirements.txt

# 2. Переконайтесь що PostgreSQL і Redis запущені локально
# У .env вкажіть:
#   DB_URL=postgresql+asyncpg://postgres:password@localhost:5432/affiliate_bot
#   REDIS_URL=redis://localhost:6379/0

# 3. Запустити бота (таблиці створяться автоматично)
python main.py
```

---

## 🛡 Крок 5 — Налаштувати Telegram Stars (для VIP-оплати)

1. У [@BotFather](https://t.me/BotFather) → вашого бота → **Edit Bot → Payments**.
2. Оберіть **Telegram Stars** як провайдера.
3. Більше нічого не потрібно — бот вже обробляє `pre_checkout_query` та `successful_payment`.

---

## 👮 Адмін-команди

| Команда | Що робить |
|---------|-----------|
| `/stats` | Статистика: юзери, VIP, виводи, перевірки |
| `/balance [id] [+-sum]` | Змінити баланс юзера |
| `/vip [id] [days]` | Видати VIP (days=0 → забрати) |
| `/vipstatus [id]` | Перевірити VIP-статус юзера |
| `/broadcast` | Масова розсилка всім юзерам |

Адміни автоматично отримують сповіщення про:
- 📋 Нові підтвердження завдань (з кнопками ✅/❌)
- 💳 Нові заявки на вивід

---

## 🔄 Як працює VIP (flow)

```
Юзер натискає ⭐ VIP Завдання
        │
        ├── is_vip = True  →  Показати список VIP-завдань
        │
        └── is_vip = False →  Лок-екран + тарифи [1д / 7д / 30д]
                                        │
                            ┌───────────┴───────────┐
                      💳 З балансу            ⭐ Telegram Stars
                            │                       │
                   ACID-транзакція          send_invoice (XTR)
                   списання UAH             → pre_checkout_query
                            │               → successful_payment
                            └───────┬───────┘
                                    ▼
                          activate_vip() в БД
                          is_vip=True, vip_expires_at+=N days
                          запис у vip_subscriptions (аудит)
                                    │
                          APScheduler кожні 10 хв
                          перевіряє vip_expires_at
                          → is_vip=False якщо прострочено
```

---

## 🗄 Таблиці бази даних

| Таблиця | Призначення |
|---------|-------------|
| `users` | Юзери: баланс, `is_vip`, `vip_expires_at` |
| `vip_subscriptions` | Аудит кожної VIP-оплати |
| `tasks` | Завдання: `is_vip_only`, ліміти, посилання |
| `task_submissions` | Підтвердження: статус pending/approved/rejected |
| `withdrawals` | Заявки на вивід |
| `referrals` | Реферальні зв'язки |

---

## 🚀 Production-checklist

- [ ] Замінити `init_db()` на Alembic міграції
- [ ] Налаштувати HTTPS webhook замість polling
- [ ] Додати rate-limiting (flood control) у middleware
- [ ] Налаштувати логування у файл / sentry
- [ ] Перевірити `MIN_ACCOUNT_AGE_DAYS` anti-fraud
