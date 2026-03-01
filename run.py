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
    console_fmt = logging.Formatter(
        "[%(levelname)s] %(message)s",
    )
    console_handler.setFormatter(console_fmt)

    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    return root_logger


logger = setup_logging()

from agent import create_agent, chat, load_memory, save_memory

BANNER = r"""
╔══════════════════════════════════════════════════════════╗
║               AI AGENT — Терминальный помощник           ║
║                                                          ║
║  Команды:                                                ║
║    /help    — список возможностей                        ║
║    /clear   — очистить историю диалога                   ║
║    /history — показать последние сообщения                ║
║    /exit    — выход                                       ║
║    /log     — показать последние строки лога              ║
╚══════════════════════════════════════════════════════════╝
"""

HELP_TEXT = """
Я умею:
  • Искать информацию в интернете (web search)
  • Показывать погоду в любом городе
  • Показывать курс криптовалют (Bitcoin, Ethereum и др.)
  • Читать и записывать файлы
  • Выполнять команды в терминале
  • Делать HTTP-запросы к API

Просто напишите запрос на естественном языке!

Примеры:
  → Какая погода в Москве?
  → Сколько стоит Bitcoin в USD?
  → Найди информацию о Python 3.12
  → Прочитай файл config.txt
  → Выполни команду dir

Логирование:
  Подробные логи записываются в agent.log
  Команда /log показывает последние записи
"""


def show_log_tail(n: int = 20):
    if not os.path.exists(LOG_FILE):
        print("[Лог-файл пуст]\n")
        return
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()
    tail = lines[-n:]
    print(f"\n── Последние {len(tail)} строк из agent.log ──")
    for line in tail:
        print(f"  {line.rstrip()}")
    print()


def main():
    print(BANNER)
    logger.info("══════════ ЗАПУСК AI AGENT ══════════")
    logger.info("Python: %s", sys.version)
    logger.info("CWD: %s", os.getcwd())
    logger.info("Лог-файл: %s", LOG_FILE)
    logger.info("Уровень логирования: %s", LOG_LEVEL)

    try:
        executor = create_agent()
    except RuntimeError as e:
        logger.critical("Не удалось создать агента: %s", e)
        print(f"\n[ОШИБКА] {e}")
        sys.exit(1)

    history = load_memory()
    logger.info("Загружено %d сообщений из памяти", len(history))
    print(f"[Загружено {len(history)} сообщений из памяти]")
    print(f"[Логи: {LOG_FILE}]\n")
    print("Введите запрос (или /help для помощи):\n")

    while True:
        try:
            user_input = input("Вы: ").strip()
        except (KeyboardInterrupt, EOFError):
            logger.info("Завершение по Ctrl+C / EOF")
            print("\n\nДо встречи!")
            break

        if not user_input:
            continue

        if user_input.lower() == "/exit":
            logger.info("Завершение по команде /exit")
            print("\nДо встречи!")
            break

        if user_input.lower() == "/help":
            print(HELP_TEXT)
            continue

        if user_input.lower() == "/clear":
            history.clear()
            save_memory(history)
            logger.info("История очищена пользователем")
            print("[История очищена]\n")
            continue

        if user_input.lower() == "/history":
            if not history:
                print("[История пуста]\n")
            else:
                for entry in history[-10:]:
                    role = "Вы" if entry["role"] == "user" else "AI"
                    ts = entry.get("timestamp", "")
                    content = entry["content"]
                    if len(content) > 200:
                        content = content[:200] + "..."
                    print(f"  [{ts}] {role}: {content}")
                print()
            continue

        if user_input.lower().startswith("/log"):
            parts = user_input.split()
            n = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 30
            show_log_tail(n)
            continue

        print()
        try:
            response = chat(user_input, history, executor)
            print(f"AI: {response}\n")
        except KeyboardInterrupt:
            logger.warning("Запрос прерван пользователем (Ctrl+C)")
            print("\n[Запрос прерван]\n")
        except Exception as e:
            logger.error("Необработанная ошибка: %s", e, exc_info=True)
            print(f"[ОШИБКА] {e}\n")


if __name__ == "__main__":
    main()
