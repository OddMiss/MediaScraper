import logging

import bot
from telegram.error import TimedOut


def test_polling_cleanup_traceback_is_reduced_to_a_warning() -> None:
    record = logging.LogRecord(
        name="telegram.ext.Updater",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg=(
            "Error while calling `get_updates` one more time to mark all fetched updates. "
            "Suppressing error to ensure graceful shutdown."
        ),
        args=(),
        exc_info=(RuntimeError, RuntimeError("temporary network outage"), None),
    )

    assert bot._TelegramNetworkLogFilter().filter(record)
    assert record.levelno == logging.WARNING
    assert record.exc_info is None
    assert record.getMessage() == (
        "Telegram polling cleanup could not finish during reconnect; "
        "continuing with the new connection."
    )


def test_unrelated_updater_error_is_not_hidden() -> None:
    record = logging.LogRecord(
        name="telegram.ext.Updater",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="Unexpected updater error",
        args=(),
        exc_info=(RuntimeError, RuntimeError("bug"), None),
    )

    assert bot._TelegramNetworkLogFilter().filter(record)
    assert record.levelno == logging.ERROR
    assert record.exc_info is not None


def test_reconnect_pool_timeout_task_traceback_is_reduced_to_a_warning() -> None:
    error = TimedOut("Pool timeout: All connections in the connection pool are occupied.")
    record = logging.LogRecord(
        name="asyncio",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="Task exception was never retrieved",
        args=(),
        exc_info=(TimedOut, error, None),
    )

    assert bot._TelegramNetworkLogFilter().filter(record)
    assert record.levelno == logging.WARNING
    assert record.exc_info is None
    assert record.getMessage() == (
        "Telegram polling task ended while waiting for a reconnect connection; "
        "continuing with the restart."
    )
