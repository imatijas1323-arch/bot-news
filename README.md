# Туда и обратно — AI-бот для ветки «Новости»

Проект: Telegram AI-бот для существующего проекта «Туда и обратно».

Бот помогает вести Telegram-ветку/топик «Новости»: раз в день находит одну сильную новость по темам движения, путешествий, спорта, outdoor, экипировки и стиля, переписывает ее в авторском формате и отправляет админу на подтверждение. После ручного одобрения бот публикует пост в нужную Telegram-ветку.

## Главная идея

Это не обычный RSS-агрегатор и не бот, который публикует все подряд. Нужна мини-редакция внутри Telegram: система сама собирает материалы, отсеивает слабые новости, выбирает релевантные темы, переписывает текст в едином стиле проекта и показывает админу только достойные черновики.

Главный принцип:

> Лучше не опубликовать ничего, чем опубликовать слабую новость.

## Что делает MVP

- Читает RSS-ленты из заранее заданного списка источников.
- Убирает дубли по URL.
- Делает первичный keyword-фильтр по темам проекта.
- Отправляет подходящие кандидаты AI-куратору для оценки релевантности.
- Генерирует короткий пост на русском языке в стиле «Туда и обратно».
- Присылает черновик админу в Telegram.
- Показывает кнопки «Опубликовать», «Пропустить», «Переписать».
- После подтверждения публикует пост в Telegram-группу и конкретную ветку «Новости».
- Хранит найденные, отклоненные, сгенерированные и опубликованные материалы в SQLite.

## Тематика

Рабочая формулировка редакционной ДНК:

> Новости о движении, путешествиях, спорте, экипировке и культуре людей, которые не сидят на месте.

Подходящие темы:

- спорт как культура, а не только результат;
- путешествия, маршруты, экспедиции, города;
- outdoor, приключения, горы, трейлы, вода, дорога;
- бег, плавание, велосипед, endurance, Ironman, UTMB;
- экипировка, функциональная одежда, techwear, streetwear;
- бренды и коллаборации: Salomon, Hoka, On, Nike, Adidas, Arc'teryx, Oakley, Garmin, Whoop, Strava, Rapha, District Vision и близкие по духу;
- технологии для спорта, путешествий и активного образа жизни;
- визуальная культура движения: форма, материалы, силуэты, городская среда.

Не публикуем:

- политику и конфликтную повестку;
- желтую прессу, сплетни и скандалы ради скандалов;
- обычные спортивные результаты без культурного или спортивного смысла;
- ставки, казино, крипту и сомнительную рекламу;
- кликбейт и формулировки вроде «шок», «срочно», «невероятно»;
- слишком локальные новости без интереса для аудитории;
- повторы одной и той же новости из разных источников.

## Формат поста

- Язык: русский.
- Длина: обычно 400-900 символов.
- Структура: заголовок, что произошло, почему это интересно аудитории «Туда и обратно».
- Источник: ссылка не добавляется в текст поста.
- Эмодзи: не используются.
- Хэштеги: не используются на старте.
- Тон: авторский, современный, живой, немного журнальный, без пафоса и канцелярита.

Пример структуры:

```text
Заголовок

Коротко: что произошло.

Почему это интересно для аудитории «Туда и обратно».
```

## Публикационный режим

- Частота публикаций: 1 пост в день.
- Проверка источников: каждые 3-4 часа или по расписанию.
- Черновики: до 3 вариантов в день.
- Порог качества: `MIN_AI_SCORE = 8`.
- Автопубликация: выключена на старте.
- Правило качества: если за день нет сильной новости, бот ничего не публикует.

## Модерация

Бот отправляет админу черновик:

```text
Найден черновик для ветки «Новости»:

[заголовок]
[текст поста]
```

Кнопки:

- «Опубликовать» — отправить пост в целевую Telegram-ветку.
- «Пропустить» — отклонить материал.
- «Переписать» — сгенерировать новую версию текста.

## Техническая архитектура

MVP разрабатывается как Python-сервис для деплоя на Amvera.

Основной стек:

- Python;
- aiogram 3.x для Telegram;
- APScheduler или cron на стороне Amvera для расписания;
- feedparser для RSS;
- httpx или aiohttp для HTTP-запросов;
- SQLite для MVP-хранилища;
- сменный AI-клиент через `.env`;
- Amvera для хостинга.

Ключевой технический момент: публикация идет не просто в `chat_id`, а в конкретную форумную ветку Telegram через `message_thread_id`.

```python
sendMessage(
    chat_id=TARGET_CHAT_ID,
    message_thread_id=NEWS_THREAD_ID,
    text=generated_post,
)
```

## Планируемая структура проекта

```text
news_bot/
├── main.py
├── config.py
├── bot.py
├── scheduler.py
├── rss_reader.py
├── filter.py
├── curator.py
├── writer.py
├── publisher.py
├── storage.py
├── ai_client.py
├── prompts/
│   ├── curator_prompt.txt
│   ├── writer_prompt.txt
│   └── rewrite_prompt.txt
├── data/
│   └── bot.db
├── requirements.txt
├── amvera.yml
└── .env.example
```

## Переменные окружения

Для запуска понадобятся:

```env
BOT_TOKEN=...
ADMIN_CHAT_ID=...
TARGET_CHAT_ID=...
NEWS_THREAD_ID=...

AI_PROVIDER=gemini
AI_MODEL=gemini-flash-or-flash-lite
AI_FALLBACK_PROVIDER=openrouter
AI_FALLBACK_MODEL=qwen-or-deepseek-free-model

MAX_POSTS_PER_DAY=1
MAX_DRAFTS_PER_DAY=3
MAX_CANDIDATES_PER_RUN=10
NEWS_CHECK_INTERVAL_HOURS=4
MIN_AI_SCORE=8
AUTO_PUBLISH=false
SHOW_SOURCE_LINK=false
ALLOW_EMOJI=false
ALLOW_HASHTAGS=false
```

## AI-стратегия

AI используется в двух местах:

1. Куратор оценивает новость и возвращает JSON с решением, оценкой, категорией и причиной.
2. Автор переписывает принятую новость в готовый Telegram-пост.

На старте практичный вариант — Gemini Flash / Flash-Lite через Gemini API Free Tier. Альтернативы и fallback: Qwen через OpenRouter `:free`, Amvera LLM Inference, Groq/Qwen как тестовый или дешевый вариант.

Провайдер должен быть сменным через `.env`, чтобы можно было переключиться без переписывания бизнес-логики.

## Программные проверки текста

После генерации поста бот должен проверить:

- нет ли URL в тексте;
- укладывается ли текст в лимит длины;
- нет ли эмодзи;
- нет ли хэштегов;
- нет ли запрещенных шаблонных фраз;
- есть ли заголовок;
- достаточно ли высокий AI-score.

Если проверка не пройдена, текст нужно переписать или не показывать админу.

## База данных MVP

Основная таблица: `articles`.

Поля:

- `id`;
- `original_title`;
- `original_url`;
- `source_name`;
- `category`;
- `image_url`;
- `status`;
- `ai_score`;
- `generated_text`;
- `created_at`;
- `updated_at`;
- `published_at`.

Статусы:

- `found`;
- `filtered`;
- `drafted`;
- `approved`;
- `published`;
- `skipped`;
- `rejected`.

Источник хранится в базе, даже если не показывается читателю. Это нужно для дедупликации, проверки спорных материалов и анализа качества источников.

## Что не входит в MVP

- сложная веб-админка;
- автопубликация без подтверждения;
- парсинг сайтов без RSS;
- генерация изображений;
- аналитика охватов и реакций;
- обучение модели;
- мультиязычность.

## Дорожная карта

1. Получить `BOT_TOKEN`, `ADMIN_CHAT_ID`, `TARGET_CHAT_ID`, `NEWS_THREAD_ID`.
2. Проверить, что бот может писать в ветку «Новости».
3. Сделать чтение RSS, дедупликацию, storage и ручной запуск `/check_now`.
4. Подключить AI-куратора и AI-автора.
5. Добавить Telegram-модерацию с кнопками.
6. Настроить деплой на Amvera.
7. Провести неделю теста: максимум 1 пост в день, фиксировать лучшие источники и темы.

## Финальное решение

Делаем Python-бота на Amvera, который раз в день помогает выбрать одну сильную новость для ветки «Новости» проекта «Туда и обратно». На старте работает только ручная модерация. Источник не показывается читателю, но сохраняется в базе. AI-провайдер делается сменным, чтобы начать с бесплатного или дешевого варианта и при необходимости быстро переключиться на другой endpoint.


План действий: MVP Telegram AI-бота «Туда и обратно / Новости»
Summary
Собираем Python-сервис для Amvera, который живет постоянно, читает RSS по расписанию, выбирает 1 сильную новость в день, генерирует русский пост без ссылки на источник и отправляет админу на модерацию. После кнопки «Опубликовать» бот публикует текст в конкретную Telegram forum-ветку через message_thread_id.

Опорные факты: Telegram sendMessage поддерживает message_thread_id для forum topic/supergroup; aiogram 3.x тоже имеет параметр message_thread_id; Amvera для Python Pip ожидает requirements.txt и amvera.yml; SQLite на Amvera нужно хранить в /data, а не в репозиторной data; Amvera cron работает в UTC, но для этого MVP лучше APScheduler внутри постоянно работающего бота; Gemini Free Tier есть, но точные активные лимиты надо смотреть в AI Studio, OpenRouter :free дает 20 RPM и 50/1000 запросов в день в зависимости от купленных кредитов. Источники: Telegram Bot API (core.telegram.org), message_thread_id (core.telegram.org), aiogram sendMessage (docs.aiogram.dev), Amvera Python/requirements (docs.amvera.ru), Amvera SQLite /data (docs.amvera.ru), Amvera secrets (docs.amvera.ru), Gemini limits (ai.google.dev), Gemini pricing/free tier (ai.google.dev), OpenRouter limits (openrouter.ai).

Key Decisions
Стек: Python 3.11 или 3.12, aiogram 3.x, APScheduler, feedparser, httpx, pydantic-settings, sqlite3, pytest.
Хостинг: Amvera как один long-running Python процесс; расписание внутри процесса через APScheduler, чтобы callback-кнопки работали без отдельного веб-сервера.
База: SQLite файл по умолчанию /data/news_bot.db на Amvera и локальный fallback ./data/news_bot.db.
AI: основной провайдер gemini, модель по умолчанию gemini-3.1-flash-lite или актуальная Flash-Lite из AI Studio; fallback через OpenAI-compatible adapter для OpenRouter/Amvera LLM Inference.
Публикация: всегда через TARGET_CHAT_ID + NEWS_THREAD_ID; для диагностики добавить команду /whereami, которая показывает chat.id и message_thread_id.
Модерация: только ADMIN_CHAT_ID; кнопки publish, skip, rewrite; автопубликация выключена.
Implementation Plan
Подготовить каркас проекта: news_bot/, prompts/, tests/, requirements.txt, amvera.yml, .env.example, README.md.
Реализовать конфиг: загрузка env-переменных, валидация обязательных ключей, лимиты MAX_POSTS_PER_DAY=1, MAX_DRAFTS_PER_DAY=3, MAX_CANDIDATES_PER_RUN=10, MIN_AI_SCORE=8, NEWS_CHECK_INTERVAL_HOURS=4.
Реализовать SQLite storage: таблица articles, уникальный индекс по original_url, статусы found/filtered/drafted/approved/published/skipped/rejected, сохранение текста, score, источника и timestamps.
Реализовать RSS pipeline: список источников в конфиге/файле, чтение через feedparser, нормализация title/url/summary/date/source, дедупликация по URL, keyword-фильтр по тематике движения, спорта, outdoor, travel, gear, brands.
Реализовать AI-слой: единый интерфейс curate(article) -> decision/score/category/reason и write(article) -> post_text; Gemini adapter отдельно, OpenAI-compatible adapter для OpenRouter/Amvera отдельно; retries/backoff на 429/5xx.
Вынести промпты в файлы: curator_prompt.txt, writer_prompt.txt, rewrite_prompt.txt; требовать JSON от куратора и чистый текст поста от автора.
Реализовать post validation: запрет URL, эмодзи, хэштегов, запрещенных фраз, пустого заголовка; лимит 400-900 символов как целевой, жесткий верхний лимит 1200 для аварийной отсечки.
Реализовать Telegram bot: /start, /help, /whereami, /check_now; отправка черновика админу с inline-кнопками; обработчики callback-кнопок; публикация в TARGET_CHAT_ID и NEWS_THREAD_ID.
Реализовать scheduler: каждые 4 часа запускать поиск кандидатов; в день показывать админу не больше 3 черновиков; не публиковать автоматически; учитывать уже опубликованные посты за текущую дату.
Подготовить деплой: amvera.yml с Python Pip, requirements.txt с pinned-версиями, PYTHONUNBUFFERED=1, секреты в Amvera UI, база в /data/news_bot.db.
Провести Telegram-разведку: создать бота через BotFather, добавить в группу, дать права писать, отправить сообщение в ветку «Новости», вызвать /whereami, записать TARGET_CHAT_ID и NEWS_THREAD_ID.
Провести неделю теста: запускать /check_now, смотреть качество источников, пополнять allowlist/blacklist, корректировать промпты и MIN_AI_SCORE.
Test Plan
Unit tests: config validation, URL dedupe, keyword filter, JSON parsing куратора, post validation, SQLite status transitions.
Integration tests with mocks: RSS reader на fixture feeds, AI adapters на fake responses, Telegram publisher на fake bot client.
Manual Telegram tests: /whereami в личке, группе и нужной ветке; черновик админу; Опубликовать; Пропустить; Переписать; проверка публикации именно в «Новости».
Deployment checks on Amvera: сборка проходит, зависимости установлены, секреты читаются, /data/news_bot.db создается в постоянном хранилище, логи видны без буферизации.
Acceptance criteria: бот за один ручной запуск находит кандидаты, не дублирует URL, показывает админу максимум 3 черновика, публикует только после подтверждения, не вставляет ссылку/эмодзи/хэштеги в пост.
Assumptions
Стартуем с чистой папки проекта, существующего кода нет.
Первый релиз делаем без веб-админки, без изображений, без парсинга сайтов без RSS и без автопубликации.
Основной AI на старте — Gemini Flash-Lite; если в AI Studio лимиты/доступ не подходят, переключаем .env на OpenRouter :free или Amvera LLM Inference без изменения бизнес-логики.
Все токены и ключи хранятся в секретах Amvera, не в репозитории.
Время расписания считаем в Москве на уровне приложения; если когда-нибудь перейдем на Amvera Cron Jobs, пересчитываем расписание в UTC.

## Текущее состояние реализации

В папке уже собран первый рабочий каркас MVP:

- `news_bot/main.py` — точка входа long-running Telegram-бота;
- `news_bot/bot.py` — команды `/start`, `/help`, `/whereami`, `/stats`, `/check_now` и callback-кнопки;
- `news_bot/curator.py` — pipeline RSS → keyword filter → AI curator → AI writer → validation;
- `news_bot/storage.py` — SQLite-хранилище со статусами и дедупликацией по URL;
- `news_bot/ai_client.py` — Gemini, OpenAI-compatible/OpenRouter и `stub`-клиент для smoke-тестов;
- `prompts/` — промпты куратора, автора и редактора;
- `prompts/editor_profile.txt` — редакционный профиль, собранный по архиву ручных постов и подключенный к отбору/написанию;
- `.env.example`, `requirements.txt`, `amvera.yml` — базовая подготовка к локальному запуску и деплою.

### Локальный запуск

```bash
cd '/Users/a1/tudaiobratno/bot new publish'
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Для первого Telegram-smoke-test можно поставить в `.env`:

```env
AI_PROVIDER=stub
```

После заполнения `BOT_TOKEN`, `ADMIN_CHAT_ID`, `TARGET_CHAT_ID` и `NEWS_THREAD_ID`:

```bash
python -m news_bot.main
```

### Telegram-разведка

1. Добавить бота в группу.
2. Дать право писать сообщения.
3. В нужной ветке «Новости» отправить `/whereami`.
4. Скопировать `chat.id` в `TARGET_CHAT_ID`, а `message_thread_id` в `NEWS_THREAD_ID`.
5. В личке с ботом или от имени админа вызвать `/check_now`.

### Проверки

```bash
python -m compileall news_bot tests
python -m pytest -q
python -m news_bot.check_ai
```

В текущем системном Python зависимости из `requirements.txt` могут быть не установлены, поэтому полноценный `pytest` ожидает активированное окружение с установленными зависимостями.

### Перед реальным запуском

Токен Telegram-бота нужно перевыпустить через BotFather, если он где-либо отправлялся в чат. После перевыпуска заменить `BOT_TOKEN` в `.env` и секретах Amvera.

Для проверки реального AI:

```env
AI_PROVIDER=gemini
GEMINI_API_KEY=...
GEMINI_API_KEYS=...,...  # optional резервные ключи через запятую
```

или:

```env
AI_PROVIDER=openrouter
OPENROUTER_API_KEY=...
AI_MODEL=qwen/qwen3-30b-a3b:free
```

Затем:

```bash
python -m news_bot.check_ai
```
