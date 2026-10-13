import asyncio

import bot
from telegram.error import NetworkError


def test_telegram_call_retries_transient_network_errors() -> None:
    attempts = 0

    async def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise NetworkError("temporary outage")
        return "sent"

    original_delay = bot.TELEGRAM_MESSAGE_RETRY_DELAY_SECONDS
    bot.TELEGRAM_MESSAGE_RETRY_DELAY_SECONDS = 0
    try:
        result = asyncio.run(bot.retry_telegram_call(operation, "test message"))
    finally:
        bot.TELEGRAM_MESSAGE_RETRY_DELAY_SECONDS = original_delay

    assert result == "sent"
    assert attempts == 3
