# Issue #559

fix: name 'positioning_survey_handlers' is not defined in telegram_worker.py

## Bug
When handling callback queries, telegram_worker.py fails with:
`name 'positioning_survey_handlers' is not defined`

## Root cause
Lazy import in telegram_worker.py line 81:
`from backend.bot.handlers import positioning_survey as positioning_survey_handlers`
This import fails at runtime, possibly due to circular import or namespace issue.

## File
`backend/workers/telegram_worker.py` line 81 & 687

## Suggested fix
Move import to top of file or use try/except guard.
