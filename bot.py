import logging
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

LOG_FILE = os.path.join(os.path.dirname(__file__), "agent.log")
LOG_LEVEL = os.environ.get("LOG_LEVEL", "DEBUG").upper()


def setup_logging():
    root_logger = logging.getLogger("agent")
    root_logger.setLevel(getattr(logging, LOG_LEVEL, logging.DEBUG))

    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_fmt = logging.Formatter(
        "%(asctime)s │ %(levelname)-8s │ %(name)-16s │ %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(file_fmt)

    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(logging.INFO)
    console_fmt = logging.Formatter("[%(levelname)s] %(message)s")
    console_handler.setFormatter(console_fmt)

    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    return root_logger


logger = setup_logging()

import telebot
from agent import create_agent, chat, load_memory, save_memory

HELP_TEXT = (
    "🤖 <b>AI Agent — Telegram-бот</b>\n\n"
    "Я умею:\n"
    "• Искать информацию в интернете\n"
    "• Показывать погоду в любом городе\n"
    "• Показывать курс криптовалют и валют\n"
    "• Читать и записывать файлы\n"
    "• Выполнять команды в терминале\n"
    "• Делать HTTP-запросы к API\n"
    "• Генерировать QR-коды\n\n"
    "Просто напишите запрос на естественном языке!\n\n"
    "<b>Примеры:</b>\n"
    "→ Какая погода в Москве?\n"
    "→ Сколько стоит Bitcoin в USD?\n"
    "→ Курс доллара к рублю\n"
    "→ Сгенерируй QR-код для google.com\n\n"
    "<b>Команды:</b>\n"
    "/start — приветствие\n"
    "/help — эта справка\n"
    "/clear — очистить историю диалога\n"
    "/history — последние сообщения"
)

MEMORY_DIR = os.path.join(os.path.dirname(__file__), "user_memories")


def get_user_memory_file(user_id: int) -> str:
    os.makedirs(MEMORY_DIR, exist_ok=True)
    return os.path.join(MEMORY_DIR, f"{user_id}.json")


def load_user_memory(user_id: int) -> list[dict]:
    path = get_user_memory_file(user_id)
    return load_memory(path)


def save_user_memory(user_id: int, history: list[dict]) -> None:
    path = get_user_memory_file(user_id)
    save_memory(history, path)


def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.critical("TELEGRAM_BOT_TOKEN не установлен!")
        print("[ОШИБКА] TELEGRAM_BOT_TOKEN не установлен. Добавьте его в .env")
        sys.exit(1)

    logger.info("══════════ ЗАПУСК TELEGRAM BOT ══════════")

    try:
        agent = create_agent()
    except RuntimeError as e:
        logger.critical("Не удалось создать агента: %s", e)
        print(f"[ОШИБКА] {e}")
        sys.exit(1)

    bot = telebot.TeleBot(token, parse_mode="MarkdownV2")
    logger.info("Telegram-бот инициализирован")

    user_histories: dict[int, list[dict]] = {}

    def get_history(user_id: int) -> list[dict]:
        if user_id not in user_histories:
            user_histories[user_id] = load_user_memory(user_id)
            logger.info("Загружена история для user_id=%d (%d записей)", user_id, len(user_histories[user_id]))
        return user_histories[user_id]

    @bot.message_handler(commands=["start"])
    def handle_start(message):
        user = message.from_user
        logger.info("/start от %s (id=%d)", user.username or user.first_name, user.id)
        bot.reply_to(
            message,
            f"Привет, {_escape_md(user.first_name)}\\! 👋\n\n"
            f"Я — AI\\-агент с набором инструментов\\.\n"
            f"Напишите /help чтобы узнать мои возможности\\.",
        )

    @bot.message_handler(commands=["help"])
    def handle_help(message):
        logger.info("/help от user_id=%d", message.from_user.id)
        bot.reply_to(message, HELP_TEXT, parse_mode="HTML")

    @bot.message_handler(commands=["clear"])
    def handle_clear(message):
        uid = message.from_user.id
        logger.info("/clear от user_id=%d", uid)
        user_histories[uid] = []
        save_user_memory(uid, [])
        bot.reply_to(message, "🗑 История диалога очищена\\.")

    @bot.message_handler(commands=["history"])
    def handle_history(message):
        uid = message.from_user.id
        history = get_history(uid)
        if not history:
            bot.reply_to(message, "История пуста\\.")
            return
        lines = []
        for entry in history[-10:]:
            role = "👤" if entry["role"] == "user" else "🤖"
            content = entry["content"]
            if len(content) > 150:
                content = content[:150] + "..."
            lines.append(f"{role} {_escape_md(content)}")
        bot.reply_to(message, "\n\n".join(lines))

    @bot.message_handler(func=lambda m: True, content_types=["text"])
    def handle_message(message):
        uid = message.from_user.id
        user_text = message.text.strip()
        username = message.from_user.username or message.from_user.first_name

        logger.info("Сообщение от %s (id=%d): '%s'", username, uid, user_text[:200])

        typing_msg = bot.reply_to(message, "⏳ Думаю\\.\\.\\.")

        history = get_history(uid)

        try:
            response = chat(user_text, history, agent)
            save_user_memory(uid, history)

            qr_file = _extract_qr_path(response)
            if qr_file and os.path.exists(qr_file):
                bot.delete_message(typing_msg.chat.id, typing_msg.message_id)
                with open(qr_file, "rb") as photo:
                    bot.send_photo(message.chat.id, photo, caption=_escape_md(response), parse_mode="MarkdownV2", reply_to_message_id=message.message_id)
                return

            escaped = _escape_md(response)
            if len(escaped) > 4000:
                bot.delete_message(typing_msg.chat.id, typing_msg.message_id)
                for i in range(0, len(escaped), 4000):
                    bot.send_message(message.chat.id, escaped[i:i + 4000])
            else:
                bot.edit_message_text(
                    escaped,
                    chat_id=typing_msg.chat.id,
                    message_id=typing_msg.message_id,
                    parse_mode="MarkdownV2",
                )
        except Exception as e:
            logger.error("Ошибка обработки сообщения от user_id=%d: %s", uid, e, exc_info=True)
            bot.edit_message_text(
                f"❌ Произошла ошибка: {_escape_md(str(e))}",
                chat_id=typing_msg.chat.id,
                message_id=typing_msg.message_id,
                parse_mode="MarkdownV2",
            )

    logger.info("Запуск polling...")
    print("[OK] Telegram-бот запущен. Нажмите Ctrl+C для остановки.")
    try:
        bot.infinity_polling(logger_level=logging.WARNING)
    except KeyboardInterrupt:
        logger.info("Бот остановлен по Ctrl+C")
        print("\nБот остановлен.")


_MD_ESCAPE_CHARS = r"_*[]()~`>#+-=|{}.!\\"


def _escape_md(text: str) -> str:
    result = []
    for ch in text:
        if ch in _MD_ESCAPE_CHARS:
            result.append("\\")
        result.append(ch)
    return "".join(result)


import re

_QR_PATH_RE = re.compile(r"QR-код сохранён:\s*(.+\.png)")


def _extract_qr_path(response: str) -> str | None:
    m = _QR_PATH_RE.search(response)
    return m.group(1).strip() if m else None


if __name__ == "__main__":
    main()
