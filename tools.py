import io
import json
import logging
import os
import subprocess

import qrcode
import requests
from langchain.tools import tool
from duckduckgo_search import DDGS

logger = logging.getLogger("agent.tools")


# ─── Weather ────────────────────────────────────────────────────────────────────

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

WMO_CODES = {
    0: "Ясно", 1: "Преимущественно ясно", 2: "Переменная облачность",
    3: "Пасмурно", 45: "Туман", 48: "Изморозь",
    51: "Лёгкая морось", 53: "Морось", 55: "Сильная морось",
    61: "Небольшой дождь", 63: "Дождь", 65: "Сильный дождь",
    66: "Ледяной дождь", 67: "Сильный ледяной дождь",
    71: "Небольшой снег", 73: "Снег", 75: "Сильный снег",
    77: "Снежная крупа", 80: "Ливень", 81: "Умеренный ливень",
    82: "Сильный ливень", 85: "Снегопад", 86: "Сильный снегопад",
    95: "Гроза", 96: "Гроза с градом", 99: "Гроза с сильным градом",
}


def _geocode(city: str) -> tuple[float, float, str]:
    logger.info("Geocoding: запрос координат для города '%s'", city)
    resp = requests.get(GEOCODING_URL, params={"name": city, "count": 1, "language": "ru"}, timeout=10)
    resp.raise_for_status()
    results = resp.json().get("results")
    if not results:
        logger.warning("Geocoding: город '%s' не найден", city)
        raise ValueError(f"Город «{city}» не найден")
    loc = results[0]
    lat, lon, name = loc["latitude"], loc["longitude"], loc.get("name", city)
    logger.info("Geocoding: '%s' → lat=%.4f, lon=%.4f", name, lat, lon)
    return lat, lon, name


@tool
def get_weather(city: str) -> str:
    """Получить текущую погоду в указанном городе. Принимает название города на любом языке."""
    logger.info("─── TOOL: get_weather(city='%s') ───", city)
    try:
        lat, lon, resolved_name = _geocode(city)
        logger.info("Запрос погоды: lat=%.4f, lon=%.4f", lat, lon)
        resp = requests.get(
            FORECAST_URL,
            params={"latitude": lat, "longitude": lon, "current_weather": True},
            timeout=10,
        )
        resp.raise_for_status()
        cw = resp.json()["current_weather"]
        logger.debug("Ответ API погоды: %s", json.dumps(cw, ensure_ascii=False))
        condition = WMO_CODES.get(cw.get("weathercode", -1), "Неизвестно")
        result = (
            f"Погода в {resolved_name}:\n"
            f"  Температура: {cw['temperature']} °C\n"
            f"  Ветер: {cw['windspeed']} км/ч\n"
            f"  Условия: {condition}"
        )
        logger.info("get_weather → OK: %.1f°C, %s", cw["temperature"], condition)
        return result
    except Exception as e:
        logger.error("get_weather → ОШИБКА: %s", e, exc_info=True)
        return f"Ошибка при получении погоды: {e}"


# ─── Crypto ─────────────────────────────────────────────────────────────────────

COINGECKO_URL = "https://api.coingecko.com/api/v3/simple/price"


@tool
def get_crypto_price(coin: str, currency: str = "usd") -> str:
    """Узнать текущий курс криптовалюты. coin — id монеты (bitcoin, ethereum и т.д.), currency — валюта (usd, eur, rub)."""
    logger.info("─── TOOL: get_crypto_price(coin='%s', currency='%s') ───", coin, currency)
    try:
        resp = requests.get(
            COINGECKO_URL,
            params={"ids": coin.lower(), "vs_currencies": currency.lower()},
            timeout=10,
        )
        logger.debug("CoinGecko HTTP %d", resp.status_code)
        resp.raise_for_status()
        data = resp.json()
        logger.debug("CoinGecko ответ: %s", json.dumps(data, ensure_ascii=False))
        if coin.lower() not in data:
            logger.warning("Криптовалюта '%s' не найдена в ответе", coin)
            return f"Криптовалюта «{coin}» не найдена. Используйте id из CoinGecko (bitcoin, ethereum, ...)"
        price = data[coin.lower()][currency.lower()]
        logger.info("get_crypto_price → OK: %s = %s %s", coin, price, currency.upper())
        return f"Курс {coin}: {price} {currency.upper()}"
    except Exception as e:
        logger.error("get_crypto_price → ОШИБКА: %s", e, exc_info=True)
        return f"Ошибка при получении курса: {e}"


# ─── Web Search ─────────────────────────────────────────────────────────────────

@tool
def web_search(query: str) -> str:
    """Поиск информации в интернете через DuckDuckGo. Принимает поисковый запрос."""
    logger.info("─── TOOL: web_search(query='%s') ───", query)
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=5))
        logger.info("web_search → найдено %d результатов", len(results))
        if not results:
            logger.warning("web_search → пустой результат")
            return "По запросу ничего не найдено."
        lines = []
        for i, r in enumerate(results, 1):
            logger.debug("  Результат %d: %s", i, r.get("title", ""))
            lines.append(f"{i}. {r['title']}\n   {r['href']}\n   {r['body']}")
        return "\n\n".join(lines)
    except Exception as e:
        logger.error("web_search → ОШИБКА: %s", e, exc_info=True)
        return f"Ошибка поиска: {e}"


# ─── File I/O ───────────────────────────────────────────────────────────────────

@tool
def read_file(file_path: str) -> str:
    """Прочитать содержимое файла по указанному пути."""
    logger.info("─── TOOL: read_file(path='%s') ───", file_path)
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        logger.info("read_file → OK: %d символов прочитано", len(content))
        if len(content) > 4000:
            logger.warning("read_file → файл обрезан (>4000 символов)")
            return content[:4000] + "\n\n... (файл обрезан, слишком большой)"
        return content if content else "(файл пуст)"
    except Exception as e:
        logger.error("read_file → ОШИБКА: %s", e, exc_info=True)
        return f"Ошибка чтения файла: {e}"


@tool
def write_file(file_path: str, content: str) -> str:
    """Записать текст в файл по указанному пути. Перезаписывает файл."""
    logger.info("─── TOOL: write_file(path='%s', len=%d) ───", file_path, len(content))
    try:
        os.makedirs(os.path.dirname(file_path) or ".", exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info("write_file → OK: %d символов записано", len(content))
        return f"Файл '{file_path}' успешно записан ({len(content)} символов)."
    except Exception as e:
        logger.error("write_file → ОШИБКА: %s", e, exc_info=True)
        return f"Ошибка записи файла: {e}"


# ─── Terminal ───────────────────────────────────────────────────────────────────

BLOCKED_COMMANDS = {"rm -rf /", "format", "del /s /q", "shutdown", "reboot", "mkfs"}


@tool
def run_terminal_command(command: str) -> str:
    """Выполнить команду в терминале (безопасно). Опасные команды блокируются."""
    logger.info("─── TOOL: run_terminal_command(cmd='%s') ───", command)
    cmd_lower = command.strip().lower()
    for blocked in BLOCKED_COMMANDS:
        if blocked in cmd_lower:
            logger.warning("Команда ЗАБЛОКИРОВАНА: '%s'", command)
            return f"Команда заблокирована по соображениям безопасности: {command}"
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=os.getcwd(),
        )
        output = result.stdout.strip()
        errors = result.stderr.strip()
        logger.info("run_terminal_command → exit_code=%d", result.returncode)
        if output:
            logger.debug("stdout: %s", output[:500])
        if errors:
            logger.debug("stderr: %s", errors[:500])
        parts = []
        if output:
            parts.append(f"Вывод:\n{output}")
        if errors:
            parts.append(f"Ошибки:\n{errors}")
        if not parts:
            parts.append("(команда выполнена без вывода)")
        parts.append(f"Код завершения: {result.returncode}")
        return "\n".join(parts)
    except subprocess.TimeoutExpired:
        logger.error("run_terminal_command → TIMEOUT (30 сек)")
        return "Команда превысила лимит времени (30 сек)."
    except Exception as e:
        logger.error("run_terminal_command → ОШИБКА: %s", e, exc_info=True)
        return f"Ошибка выполнения команды: {e}"


# ─── HTTP Request ───────────────────────────────────────────────────────────────

@tool
def http_request(url: str, method: str = "GET") -> str:
    """Выполнить HTTP-запрос к указанному URL. method — GET или POST."""
    logger.info("─── TOOL: http_request(url='%s', method='%s') ───", url, method)
    try:
        if method.upper() == "POST":
            resp = requests.post(url, timeout=15)
        else:
            resp = requests.get(url, timeout=15)
        logger.info("http_request → HTTP %d, %d байт", resp.status_code, len(resp.content))
        resp.raise_for_status()
        text = resp.text
        if len(text) > 4000:
            logger.warning("http_request → ответ обрезан (>4000 символов)")
            text = text[:4000] + "\n\n... (ответ обрезан)"
        return f"HTTP {resp.status_code}:\n{text}"
    except Exception as e:
        logger.error("http_request → ОШИБКА: %s", e, exc_info=True)
        return f"Ошибка HTTP-запроса: {e}"


# ─── Currency Exchange ──────────────────────────────────────────────────────────

EXCHANGE_API_URL = "https://open.er-api.com/v6/latest"

CURRENCY_NAMES = {
    "USD": "Доллар США", "EUR": "Евро", "RUB": "Российский рубль",
    "GBP": "Фунт стерлингов", "JPY": "Японская иена", "CNY": "Китайский юань",
    "CHF": "Швейцарский франк", "TRY": "Турецкая лира", "KZT": "Казахстанский тенге",
    "BYN": "Белорусский рубль", "UAH": "Украинская гривна", "PLN": "Польский злотый",
    "CZK": "Чешская крона", "SEK": "Шведская крона", "NOK": "Норвежская крона",
    "CAD": "Канадский доллар", "AUD": "Австралийский доллар", "BRL": "Бразильский реал",
    "INR": "Индийская рупия", "KRW": "Южнокорейская вона", "AED": "Дирхам ОАЭ",
    "GEL": "Грузинский лари", "AMD": "Армянский драм", "UZS": "Узбекский сум",
}


@tool
def get_currency_rate(base: str, targets: str = "USD,EUR,RUB") -> str:
    """Получить курс обычной валюты. base — базовая валюта (например USD, EUR, RUB). targets — целевые валюты через запятую (например 'USD,EUR,RUB'). Коды валют — ISO 4217."""
    logger.info("─── TOOL: get_currency_rate(base='%s', targets='%s') ───", base, targets)
    try:
        base_upper = base.strip().upper()
        target_list = [t.strip().upper() for t in targets.split(",") if t.strip()]
        target_list = [t for t in target_list if t != base_upper]

        if not target_list:
            return f"Укажите хотя бы одну целевую валюту, отличную от {base_upper}."

        url = f"{EXCHANGE_API_URL}/{base_upper}"
        resp = requests.get(url, timeout=10)
        logger.debug("ExchangeRate API HTTP %d", resp.status_code)
        resp.raise_for_status()
        data = resp.json()

        if data.get("result") != "success":
            logger.warning("ExchangeRate API ошибка: %s", data.get("error-type", "unknown"))
            return f"Не удалось получить курсы для {base_upper}. Проверьте код валюты (ISO 4217)."

        all_rates = data.get("rates", {})
        logger.debug("ExchangeRate API: получено %d курсов", len(all_rates))

        rates = {code: all_rates[code] for code in target_list if code in all_rates}
        missing = [code for code in target_list if code not in all_rates]
        if missing:
            logger.warning("Не найдены курсы для: %s", ", ".join(missing))

        if not rates:
            available = ", ".join(sorted(all_rates.keys())[:20])
            return f"Валюты {', '.join(target_list)} не найдены. Доступные: {available}..."

        date = data.get("time_last_update_utc", "?").split(" 00:")[0]
        base_name = CURRENCY_NAMES.get(base_upper, base_upper)
        lines = [f"Курсы {base_name} ({base_upper}) на {date}:"]
        for code, rate in sorted(rates.items()):
            name = CURRENCY_NAMES.get(code, code)
            lines.append(f"  1 {base_upper} = {rate} {code} ({name})")
        if missing:
            lines.append(f"\nНе найдены: {', '.join(missing)}")

        logger.info("get_currency_rate → OK: %d курсов", len(rates))
        return "\n".join(lines)
    except Exception as e:
        logger.error("get_currency_rate → ОШИБКА: %s", e, exc_info=True)
        return f"Ошибка при получении курса валют: {e}"


# ─── QR Code ────────────────────────────────────────────────────────────────────

QR_OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "qr_codes")


@tool
def generate_qr_code(data: str, filename: str = "") -> str:
    """Сгенерировать QR-код из текста или URL. data — содержимое QR-кода (текст, ссылка, и т.д.). filename — имя файла (необязательно)."""
    logger.info("─── TOOL: generate_qr_code(data='%s', filename='%s') ───", data[:100], filename)
    try:
        os.makedirs(QR_OUTPUT_DIR, exist_ok=True)

        if not filename:
            safe_name = "".join(c if c.isalnum() else "_" for c in data[:30])
            filename = f"qr_{safe_name}.png"
        if not filename.endswith(".png"):
            filename += ".png"

        filepath = os.path.join(QR_OUTPUT_DIR, filename)

        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=4,
        )
        qr.add_data(data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        img.save(filepath)

        logger.info("generate_qr_code → OK: %s", filepath)
        return f"QR-код сохранён: {filepath}\nСодержимое: {data}"
    except Exception as e:
        logger.error("generate_qr_code → ОШИБКА: %s", e, exc_info=True)
        return f"Ошибка генерации QR-кода: {e}"


# ─── Реестр всех инструментов ───────────────────────────────────────────────────

ALL_TOOLS = [
    get_weather,
    get_crypto_price,
    web_search,
    read_file,
    write_file,
    run_terminal_command,
    http_request,
    get_currency_rate,
    generate_qr_code,
]
