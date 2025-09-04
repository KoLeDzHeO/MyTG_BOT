# Changelog

- Graceful shutdown via PTB lifecycle hooks; resources close cleanly.
- Removed direct asyncio.run calls to avoid event loop errors.
- Startup and shutdown logs report DB and TMDb client status.
- Startup verifies DB and TMDb key; logs "Bot started" with DB=ok TMDb=ok.
- Unique constraint handling logs unknown names and retries short-id collisions.
- `/add` validates year range with clearer hints and returns error IDs on failures.
- TMDb errors (401/429/5xx) log status codes with response snippets.
- Fallback English genres are marked with `(en)`; success logs include genres.
- Export stub and logs now include movie title and year for easier checks.
