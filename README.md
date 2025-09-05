# MyTG_BOT

Телеграм-бот, отвечающий на сообщения с помощью OpenAI и Groq.

## Режимы запроса (`.` и `..`)
- `. вопрос` — Groq LLaMA-3-70B в стиле матершинника.
- `.. вопрос` — OpenAI GPT-4o, отвечает вежливо и структурированно.
- Если `REQUIRE_PREFIX=false`, префикс не обязателен. В этом случае используется провайдер из переменной
<code>DEFAULT_PROVIDER</code> (<code>groq</code> или <code>openai</code>). По умолчанию — <code>groq</code>.

## Переменные окружения
| Переменная | Назначение |
| --- | --- |
| `BOT_TOKEN` | токен бота |
| `OPENAI_API_KEY` | ключ OpenAI |
| `GROQ_API_KEY` | ключ Groq |
| `WEBHOOK_URL` | URL вебхука (опц.) |
| `WEBHOOK_SECRET` | секрет вебхука (опц.) |
| `PORT` | порт вебсервера |
| `MODEL_OPENAI` | модель OpenAI |
| `MODEL_GROQ` | модель Groq |
| `MAX_TOKENS_OPENAI` | предел токенов для OpenAI |
| `MAX_TOKENS_GROQ` | предел токенов для Groq |
| `MAX_PROMPT_CHARS` | максимальная длина входного сообщения |
| `MAX_REPLY_CHARS` | максимальная длина ответа |
| `REQUIRE_PREFIX` | требовать ли префикс `.`/`..` |
| `DEFAULT_PROVIDER` | провайдер по умолчанию без префикса: `groq` или `openai` |
| `DIALOG_HISTORY_LEN` | сколько пар реплик хранить в истории |
| `LOG_CHAT_ID` | чат для логов (опц.) |
| `LOG_FORMAT` | формат логов: `plain` или `json` |
| `DATABASE_URL` | строка подключения к PostgreSQL |
| `TMDB_KEY` | API ключ TMDb |
| `LANG_FALLBACKS` | языки фоллбэка TMDb, через запятую |
| `MEGA_URL` | ссылка на полный архив (опц.) |

Антиспам отключён и не поддерживается.

## Безопасность
⚠️ Никогда не храните ключи в коде или репозитории. Используйте только переменные окружения (Railway → Settings → Variables или локальный `.env`).

## Пример запуска

```bash
docker run \
  -e TELEGRAM_TOKEN=123:ABC \
  -e OPENAI_API_KEY=your-openai-key \
  -e GROQ_API_KEY=your-groq-key \
  mytg_bot:latest
```

На Railway переменные задаются в разделе **Settings → Variables**:

```
TELEGRAM_TOKEN=123:ABC
OPENAI_API_KEY=your-openai-key
GROQ_API_KEY=your-groq-key
```

## Проверка команды /add

### Локально
1. Создайте `.env` и задайте `BOT_TOKEN`, `DATABASE_URL`, `TMDB_KEY` (опц. `LANG_FALLBACKS=ru,en`).
2. Установите зависимости: `pip install -r requirements.txt`.
3. Запустите бота: `python main.py`.
4. В Telegram отправьте: `/add Интерстеллар 2014`.
5. При отсутствии обязательных переменных при запуске будет выведено имя переменной и подсказка, как её указать.

### Railway
1. В разделе **Settings → Variables** добавьте `BOT_TOKEN`, `DATABASE_URL`, `TMDB_KEY`.
2. Задеплойте образ; в логах должно появиться `Bot started`.
3. Проверьте команду `/add` в чате.
4. Если какая-либо из переменных не задана, бот завершится с ошибкой и подскажет, какую переменную добавить.

## Команда /list

Показывает последние 30 фильмов со статусами. Если фильмов больше и задана `MEGA_URL`, добавляется ссылка на полный архив.
