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
- Added `/list` command to show recently added movies with status icons.
- `/add` now auto-adds only on strict title match and shows clean similar-title dialogs otherwise.
- `/add` suggestions tighten short-word matching, swap series hints for part requests, and drop the auto-add button from similar dialogs.
- `/add` now requires a year and shows a dedicated hint when it is missing or invalid.
  <!-- removed: `/list` no longer displays genres to keep the list clean -->
- Added `/help` command to show available commands.
