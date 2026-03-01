# AI Agent — Терминальный и Telegram-помощник

Локальный AI-агент на базе OpenAI и LangChain, который понимает задачи на естественном языке, самостоятельно выбирает нужный инструмент и возвращает структурированный ответ.

Работает в двух режимах: **CLI** (терминал) и **Telegram-бот**.

## Возможности

| Инструмент | Описание |
|---|---|
| **Web Search** | Поиск информации в интернете через DuckDuckGo |
| **Weather** | Погода в любом городе (Open-Meteo API) |
| **Crypto Price** | Курс криптовалют — Bitcoin, Ethereum и др. (CoinGecko API) |
| **Currency Rate** | Курс обычных валют — USD, EUR, RUB и 150+ других (ExchangeRate API) |
| **QR Code** | Генерация QR-кодов из текста, URL, Wi-Fi и т.д. |
| **File I/O** | Чтение и запись файлов |
| **Terminal** | Выполнение терминальных команд (с блокировкой опасных) |
| **HTTP Request** | Произвольные GET/POST запросы к API |

Все API бесплатные и не требуют ключей (кроме OpenAI).

## Структура проекта

```
agent/
├── agent.py           # ядро агента (LangChain + LangGraph + память)
├── tools.py           # все инструменты
├── run.py             # CLI-интерфейс (терминал)
├── bot.py             # Telegram-бот (pyTelegramBotAPI)
├── memory.json        # история CLI-диалога
├── user_memories/     # истории Telegram-пользователей
├── qr_codes/          # сгенерированные QR-коды
├── agent.log          # подробные логи
├── requirements.txt   # зависимости
└── .env               # ключи API
```

## Быстрый старт

### 1. Клонирование и настройка окружения

```bash
cd agent
py -3.11 -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Настройка ключей

Отредактируйте файл `.env`:

```env
OPENAI_API_KEY=sk-ваш-ключ
OPENAI_MODEL=gpt-4o-mini
TELEGRAM_BOT_TOKEN=ваш-токен-от-BotFather
```

- `OPENAI_API_KEY` — получите на [platform.openai.com](https://platform.openai.com/)
- `OPENAI_MODEL` — модель OpenAI (`gpt-4o-mini`, `gpt-4o`, `gpt-3.5-turbo`)
- `TELEGRAM_BOT_TOKEN` — получите у [@BotFather](https://t.me/BotFather) в Telegram

### 3. Запуск

**Терминальный режим:**

```bash
python run.py
```

**Telegram-бот:**

```bash
python bot.py
```

## Использование

### CLI-режим

```
Вы: Какая погода в Москве?
AI: Погода в Москве:
      Температура: -3.2 °C
      Ветер: 12 км/ч
      Условия: Пасмурно

Вы: Сколько стоит Bitcoin в USD?
AI: Курс bitcoin: 85432.50 USD

Вы: Курс доллара к рублю
AI: Курсы Доллар США (USD) на Sat, 01 Mar 2026:
      1 USD = 89.50 RUB (Российский рубль)

Вы: Сгенерируй QR-код для https://google.com
AI: QR-код сохранён: D:\...\agent\qr_codes\qr_https___google_com.png

Вы: Найди информацию о LangChain
AI: (результаты поиска из DuckDuckGo)
```

**Команды CLI:**

| Команда | Описание |
|---|---|
| `/help` | Список возможностей |
| `/clear` | Очистить историю диалога |
| `/history` | Последние сообщения |
| `/log` | Показать последние строки лога |
| `/log 50` | Показать 50 строк лога |
| `/exit` | Выход |

### Telegram-бот

| Команда | Описание |
|---|---|
| `/start` | Приветствие |
| `/help` | Справка |
| `/clear` | Очистить историю |
| `/history` | Последние сообщения |
| Любой текст | Запрос к AI-агенту |

QR-коды отправляются как изображения прямо в чат.
У каждого пользователя своя изолированная история диалога.

## Логирование

Все действия агента записываются в `agent.log`:

- Какой инструмент был вызван и с какими параметрами
- Ответы внешних API
- Цепочка рассуждений модели
- Ошибки с полным traceback

Уровень логирования настраивается через переменную окружения:

```bash
set LOG_LEVEL=DEBUG
python run.py
```

## Контекстная память

- **CLI** — единый файл `memory.json`, загружается при каждом запуске
- **Telegram** — файл на каждого пользователя в `user_memories/{user_id}.json`
- Агент помнит последние 20 сообщений и использует их как контекст

## Зависимости

- Python 3.11+
- openai
- langchain + langchain-openai + langchain-core + langgraph
- duckduckgo-search
- requests
- python-dotenv
- pyTelegramBotAPI
- qrcode[pil]
