import json
import logging
import os
from datetime import datetime

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from langgraph.prebuilt import create_react_agent

from tools import ALL_TOOLS

load_dotenv()

logger = logging.getLogger("agent.core")

DEFAULT_MEMORY_FILE = os.path.join(os.path.dirname(__file__), "memory.json")

SYSTEM_PROMPT = """Ты — умный AI-ассистент с доступом к набору инструментов.

Твои возможности:
• get_weather — узнать погоду в любом городе
• get_crypto_price — узнать курс криптовалюты (bitcoin, ethereum и др.)
• web_search — поиск информации в интернете
• read_file / write_file — чтение и запись файлов
• run_terminal_command — выполнение команд в терминале (безопасно)
• http_request — HTTP-запросы к внешним API
• get_currency_rate — курсы обычных валют (EUR, USD, RUB и др.)
• generate_qr_code — генерация QR-кода из текста или URL

Правила:
1. Всегда выбирай наиболее подходящий инструмент для задачи.
2. Если запрос неоднозначен — задавай уточняющие вопросы.
3. Отвечай структурированно и понятно, на языке пользователя.
4. Если инструмент вернул ошибку — объясни пользователю что произошло.
5. Для погоды используй get_weather, для крипты — get_crypto_price.
6. Для курсов обычных валют (EUR, USD, RUB и т.д.) используй get_currency_rate.
7. Для генерации QR-кода используй generate_qr_code.
"""


def load_memory(memory_file: str | None = None) -> list[dict]:
    path = memory_file or DEFAULT_MEMORY_FILE
    logger.info("Загрузка памяти из %s", path)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            logger.info("Загружено %d записей из памяти", len(data))
            return data
        except (json.JSONDecodeError, IOError) as e:
            logger.error("Ошибка чтения %s: %s", path, e)
            return []
    logger.info("Файл памяти не найден, начинаем с пустой истории")
    return []


def save_memory(history: list[dict], memory_file: str | None = None) -> None:
    path = memory_file or DEFAULT_MEMORY_FILE
    logger.info("Сохранение памяти: %d записей → %s", len(history), path)
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
        logger.debug("Память сохранена успешно")
    except IOError as e:
        logger.error("Ошибка сохранения %s: %s", path, e)


def history_to_messages(history: list[dict]):
    messages = []
    for entry in history[-20:]:
        if entry["role"] == "user":
            messages.append(HumanMessage(content=entry["content"]))
        elif entry["role"] == "assistant":
            messages.append(AIMessage(content=entry["content"]))
    logger.debug("Конвертировано %d записей истории в messages", len(messages))
    return messages


def create_agent():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.critical("OPENAI_API_KEY не установлен!")
        raise RuntimeError(
            "OPENAI_API_KEY не установлен. Создайте файл .env с переменной OPENAI_API_KEY=sk-..."
        )

    model_name = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    logger.info("Создание агента: модель=%s", model_name)

    llm = ChatOpenAI(
        model=model_name,
        temperature=0.3,
        api_key=api_key,
    )
    logger.info("LLM инициализирован: %s, temperature=0.3", model_name)

    tool_names = [t.name for t in ALL_TOOLS]
    logger.info("Регистрация инструментов: %s", ", ".join(tool_names))

    agent = create_react_agent(
        model=llm,
        tools=ALL_TOOLS,
        prompt=SYSTEM_PROMPT,
    )

    logger.info("Агент создан успешно (create_react_agent)")
    return agent


def chat(user_input: str, history: list[dict], agent) -> str:
    logger.info("════════════════════════════════════════")
    logger.info("НОВЫЙ ЗАПРОС: '%s'", user_input[:200])
    logger.info("════════════════════════════════════════")

    chat_history = history_to_messages(history)
    logger.info("История чата: %d сообщений передано модели", len(chat_history))

    messages = chat_history + [HumanMessage(content=user_input)]

    logger.info("Отправка запроса в LLM...")
    try:
        result = agent.invoke({"messages": messages})
    except Exception as e:
        logger.error("Ошибка при вызове агента: %s", e, exc_info=True)
        raise

    logger.info("Ответ получен, всего %d сообщений в цепочке", len(result["messages"]))

    for i, m in enumerate(result["messages"]):
        msg_type = type(m).__name__
        if isinstance(m, AIMessage) and m.tool_calls:
            for tc in m.tool_calls:
                logger.info(
                    "  [%d] %s → вызов инструмента: %s(%s)",
                    i, msg_type, tc["name"], json.dumps(tc["args"], ensure_ascii=False)[:200],
                )
        elif isinstance(m, ToolMessage):
            content_preview = str(m.content)[:200]
            logger.info("  [%d] %s (tool=%s) → %s", i, msg_type, m.name, content_preview)
        elif isinstance(m, AIMessage):
            content_preview = str(m.content)[:200] if m.content else "(пусто)"
            logger.info("  [%d] %s → %s", i, msg_type, content_preview)
        else:
            logger.debug("  [%d] %s", i, msg_type)

    ai_messages = [
        m for m in result["messages"]
        if isinstance(m, AIMessage) and m.content and not m.tool_calls
    ]
    response = ai_messages[-1].content if ai_messages else "Нет ответа."
    logger.info("Финальный ответ (%d символов): %s...", len(response), response[:100])

    history.append({
        "role": "user",
        "content": user_input,
        "timestamp": datetime.now().isoformat(),
    })
    history.append({
        "role": "assistant",
        "content": response,
        "timestamp": datetime.now().isoformat(),
    })

    save_memory(history)
    logger.info("Запрос обработан, история: %d записей", len(history))
    return response
