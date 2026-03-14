# Telegram Python IM API

Python adaptation of the Telegram module with a structure similar to `channels/im_api/qq`.

## Structure

- `telegram/api.py`: Telegram send/download helpers
- `telegram/context.py`: inbound message context
- `telegram/gateway.py`: long-polling gateway wrapper
- `telegram/bot.py`: bot dispatcher
- `main.py`: runnable sample

## Notes

Uses long polling via `python-telegram-bot`.
