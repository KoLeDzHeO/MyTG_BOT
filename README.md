# MyTG_BOT

Телеграм-бот, отвечающий на сообщения с помощью OpenAI и Groq.

## Режимы запроса (`.` и `..`)
- `. вопрос` — Groq LLaMA-3-70B в стиле матершинника.
- `.. вопрос` — OpenAI GPT-4o, отвечает вежливо и структурированно.
- Если `REQUIRE_PREFIX=false`, точка не обязательна и по умолчанию используется Groq.

## Переменные окружения
| Переменная | Назначение |
| --- | --- |
| `TELEGRAM_TOKEN` | токен бота |
| `OPENAI_API_KEY` | ключ OpenAI |
| `GROQ_API_KEY` | ключ Groq |
| `WEBHOOK_URL` | URL вебхука (опц.) |
| `WEBHOOK_SECRET` | секрет вебхука (опц.) |
| `PORT` | порт вебсервера |
| `MODEL_DOT` | модель OpenAI для короткого режима |
| `MODEL_DDOT` | модель OpenAI для полного режима |
| `GROQ_MODEL` | модель Groq |
| `MAX_TOKENS_GROQ` | предел токенов для Groq |
| `MAX_TOKENS_DOT` | предел токенов для короткого режима OpenAI |
| `MAX_TOKENS_DDOT` | предел токенов для полного режима OpenAI |
| `MAX_PROMPT_CHARS` | максимальная длина входного сообщения |
| `MAX_REPLY_CHARS` | максимальная длина ответа |
| `REQUIRE_PREFIX` | требовать ли префикс `.`/`..` |
| `DIALOG_HISTORY_LEN` | сколько пар реплик хранить в истории |
| `LOG_CHAT_ID` | чат для логов (опц.) |
| `LOG_FORMAT` | формат логов: `plain` или `json` |

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
