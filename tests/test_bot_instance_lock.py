import os
import uuid

import pytest

import bot


@pytest.mark.skipif(os.name != "nt", reason="Windows named mutexes are used by the bot")
def test_instance_lock_rejects_a_second_copy_with_the_same_token() -> None:
    token = f"test-token-{uuid.uuid4()}"
    first = bot.BotInstanceLock(token)
    second = bot.BotInstanceLock(token)

    assert first.acquire()
    try:
        assert not second.acquire()
    finally:
        first.release()

    assert second.acquire()
    second.release()


@pytest.mark.skipif(os.name != "nt", reason="Windows named mutexes are used by the bot")
def test_instance_lock_allows_different_bot_tokens() -> None:
    first = bot.BotInstanceLock(f"test-token-{uuid.uuid4()}")
    second = bot.BotInstanceLock(f"test-token-{uuid.uuid4()}")

    assert first.acquire()
    assert second.acquire()

    first.release()
    second.release()
