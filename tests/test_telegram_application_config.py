import bot

from polling_health import PollingHealth


def test_polling_uses_a_second_connection_for_recovery() -> None:
    application = bot.build_application("123:ABC", PollingHealth())
    try:
        request = application.bot._request[0]
        pool = request._client._transport._pool

        assert pool._max_connections == bot.TELEGRAM_GET_UPDATES_CONNECTION_POOL_SIZE
    finally:
        bot.POLLING_HEALTH_BY_BOT.pop(id(application.bot), None)


def test_polling_restart_keeps_the_event_loop_open() -> None:
    class FakeApplication:
        kwargs: dict[str, object]

        def run_polling(self, **kwargs: object) -> None:
            self.kwargs = kwargs

    application = FakeApplication()

    bot.run_application(application)  # type: ignore[arg-type]

    assert application.kwargs["close_loop"] is False
    assert application.kwargs["bootstrap_retries"] == -1
