# Guide OS Context

Guide OS is a Telegram bot for tourist guides.

MVP features:
- Calendar
- Add Tour
- Income
- Stats
- Delete Tour
- Day Off

Stack:
- Python
- aiogram
- SQLite
- Railway

Architecture:
- handlers: Telegram UX
- services: business logic
- database: DB access
- keyboards: Telegram buttons
- states: FSM
- utils: helpers

Main rule:
Build only MVP. No marketplace, no AI, no Google Calendar, no CRM.