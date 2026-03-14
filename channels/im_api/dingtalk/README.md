# DingTalk Python IM API

Python adaptation of the DingTalk channel module with a structure similar to `channels/im_api/qq`.

## Structure

- `dingtalk/auth.py`: access token cache
- `dingtalk/api.py`: DingTalk HTTP API helpers
- `dingtalk/context.py`: inbound message context
- `dingtalk/message_utils.py`: message parsing helpers
- `dingtalk/dedup.py`: in-memory dedup store
- `dingtalk/gateway.py`: optional stream gateway wrapper
- `dingtalk/bot.py`: bot dispatcher
- `main.py`: runnable sample

## Notes

Inbound stream mode needs an extra SDK:

```bash
pip install dingtalk-stream
```

Without that SDK, outbound send can still work if `sessionWebhook` metadata is provided.
