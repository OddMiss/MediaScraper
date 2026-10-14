"""Telegram link downloader with pluggable media sources."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections.abc import Awaitable, Callable
from datetime import datetime
from pathlib import Path
from typing import Any, TypeVar

from telegram import Message, Update
from telegram.error import NetworkError
from telegram.ext import Application, ContextTypes, ExtBot, MessageHandler, filters
from telegram.request import HTTPXRequest
from dotenv import load_dotenv

from download_index import DownloadIndex
from media_types import SourceError
from polling_health import PollingHealth
from source_registry import SourceRegistry
from url_tools import extract_urls, title_hint_before_url
from douyin_source import DouyinSource
from netease_music_source import NeteaseMusicSource
from pipixia_source import PipixiaSource
from tiktok_source import TikTokSource
from x_twitter_source import XTwitterSource
from xiaohongshu_source import XiaohongshuSource

SCRIPT_DIR = Path(__file__).resolve().parent
LOG_DIR = SCRIPT_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_PATH = LOG_DIR / f"{datetime.now():%Y%m%d_%H%M%S_%f}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
    ],
)


class _TelegramNetworkLogFilter(logging.Filter):
    """Replace expected Telegram reconnection tracebacks with concise warnings."""

    def filter(self, record: logging.LogRecord) -> bool:
        if (
            record.name == "telegram.ext"
            and record.getMessage().startswith("Network Retry Loop (Bootstrap")
        ):
            record.levelno = logging.WARNING
            record.levelname = "WARNING"
            record.msg = (
                "Telegram connection is unavailable during startup; retrying automatically."
            )
            record.args = ()
            record.exc_info = None
            record.exc_text = None
        elif (
            record.name == "telegram.ext.Updater"
            and record.getMessage().startswith(
                "Error while calling `get_updates` one more time to mark all fetched updates."
            )
        ):
            # This request only acknowledges the final polling offset during a
            # reconnect shutdown. The Telegram library already suppresses its
            # failure, so avoid writing a misleading full traceback to logs.
            record.levelno = logging.WARNING
            record.levelname = "WARNING"
            record.msg = (
                "Telegram polling cleanup could not finish during reconnect; "
                "continuing with the new connection."
            )
            record.args = ()
            record.exc_info = None
            record.exc_text = None
        return True


for _handler in logging.getLogger().handlers:
    _handler.addFilter(_TelegramNetworkLogFilter())

# HTTP client request URLs include the Bot API token; keep them out of logs.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
# The polling watchdog runs every 30 seconds.  Keep APScheduler's routine
# start/success messages out of the log while retaining warnings and errors.
logging.getLogger("apscheduler.executors").setLevel(logging.WARNING)
LOGGER = logging.getLogger("bot")
# Read configuration next to this script.  Do not print the token or its value.
load_dotenv(SCRIPT_DIR / ".env")
DOWNLOAD_DIR = SCRIPT_DIR / "downloads"
DOWNLOAD_INDEX = DownloadIndex(DOWNLOAD_DIR / "index.json")
ALLOWED_USER_IDS = {int(value) for value in os.getenv("ALLOWED_USER_IDS", "").split(",") if value.strip()}
# Add each future platform implementation here.  The router keeps the bot and
# queue independent from whether a plugin downloads video, images, or text.
SOURCES = SourceRegistry(
    [
        XiaohongshuSource(),
        DouyinSource(),
        PipixiaSource(),
        TikTokSource(),
        XTwitterSource(),
        NeteaseMusicSource(),
    ]
)
QUEUE_LOCK = asyncio.Lock()
POLLING_HEALTH_BY_BOT: dict[int, PollingHealth] = {}
POLLING_HEALTH_CHECK_SECONDS = 30
POLLING_STALL_SECONDS = 120
POLLING_RESTART_DELAY_SECONDS = 5
# Telegram gives getUpdates a one-connection pool by default.  Keep a second
# connection available so the updater can finish an interrupted long poll
# while its shutdown/restart request is in progress.
TELEGRAM_GET_UPDATES_CONNECTION_POOL_SIZE = 2
TELEGRAM_MESSAGE_RETRY_ATTEMPTS = 3
TELEGRAM_MESSAGE_RETRY_DELAY_SECONDS = 2
Result = TypeVar("Result")


class TrackingExtBot(ExtBot):
    """Record polling activity so a hung proxy connection can be detected."""

    async def get_updates(self, *args: Any, **kwargs: Any) -> tuple[Update, ...]:
        health = POLLING_HEALTH_BY_BOT.get(id(self))
        updates = await super().get_updates(*args, **kwargs)
        if health:
            health.record_success()
        return updates


async def monitor_polling_health(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Rebuild the application if no polling request succeeds for too long."""
    health = context.application.bot_data["polling_health"]
    if not isinstance(health, PollingHealth) or not health.is_stalled(POLLING_STALL_SECONDS):
        return

    polling_task = getattr(context.application.updater, "_Updater__polling_task", None)
    task_state = "ended" if polling_task and polling_task.done() else "stalled"
    health.restart_requested = True
    LOGGER.warning(
        "Telegram polling has not succeeded for at least %s seconds (%s); rebuilding the connection.",
        POLLING_STALL_SECONDS,
        task_state,
    )
    context.application.stop_running()


async def retry_telegram_call(
    operation: Callable[[], Awaitable[Result]], description: str
) -> Result | None:
    """Retry a transient outbound Telegram request without dropping its work item."""
    for attempt in range(1, TELEGRAM_MESSAGE_RETRY_ATTEMPTS + 1):
        try:
            return await operation()
        except NetworkError as exc:
            if attempt == TELEGRAM_MESSAGE_RETRY_ATTEMPTS:
                LOGGER.warning(
                    "Telegram %s failed after %d attempts: %s",
                    description,
                    attempt,
                    exc,
                )
                return None
            delay = TELEGRAM_MESSAGE_RETRY_DELAY_SECONDS * attempt
            LOGGER.warning(
                "Telegram %s failed (attempt %d/%d): %s; retrying in %s seconds.",
                description,
                attempt,
                TELEGRAM_MESSAGE_RETRY_ATTEMPTS,
                exc,
                delay,
            )
            await asyncio.sleep(delay)
    return None


async def reply_with_retry(message: Message, text: str, description: str) -> Message | None:
    return await retry_telegram_call(lambda: message.reply_text(text), description)


async def update_status_with_retry(status: Message | None, text: str) -> Message | None:
    if status is None:
        return None
    updated = await retry_telegram_call(
        lambda: status.edit_text(text),
        "download status update",
    )
    return status if updated is not None else None


async def handle_application_error(
    update: object, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Keep transient Telegram polling failures out of the error traceback."""
    if isinstance(context.error, NetworkError):
        LOGGER.warning(
            "Telegram connection failed temporarily; polling will retry automatically: %s",
            context.error,
        )
        return
    LOGGER.exception("Unhandled Telegram application error", exc_info=context.error)


def _authorised(update: Update) -> bool:
    return not ALLOWED_USER_IDS or (update.effective_user and update.effective_user.id in ALLOWED_USER_IDS)


async def handle_links(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    user_id = update.effective_user.id if update.effective_user else None
    chat_id = update.effective_chat.id if update.effective_chat else None
    if not _authorised(update):
        LOGGER.warning("Rejected unauthorized message chat_id=%s user_id=%s", chat_id, user_id)
        await reply_with_retry(message, "你没有使用此机器人的权限。", "permission reply")
        return
    urls = extract_urls(message.text or "")
    if not urls:
        LOGGER.debug("Ignored text message without links chat_id=%s user_id=%s", chat_id, user_id)
        return

    supported_urls = [url for url in urls if SOURCES.supports(url)]
    invalid_urls = [url for url in urls if not SOURCES.supports(url)]
    LOGGER.info(
        "Received links chat_id=%s user_id=%s message_id=%s total=%d supported=%d invalid=%d",
        chat_id,
        user_id,
        message.message_id,
        len(urls),
        len(supported_urls),
        len(invalid_urls),
    )
    if not supported_urls:
        LOGGER.warning("Rejected message with no whitelisted links chat_id=%s", chat_id)
        whitelist = "、".join(SOURCES.whitelist())
        await reply_with_retry(
            message,
            f"链接无效：不在允许列表中。\n当前允许：{whitelist}",
            "invalid-link reply",
        )
        return

    queue_text = f"发现 {len(supported_urls)} 个有效链接，已进入队列…"
    if invalid_urls:
        shown_urls = "\n".join(invalid_urls[:3])
        extra = "" if len(invalid_urls) <= 3 else f"\n另有 {len(invalid_urls) - 3} 条无效链接。"
        queue_text = f"以下链接无效，已跳过：\n{shown_urls}{extra}\n\n{queue_text}"
    status = await reply_with_retry(message, queue_text, "queue-status reply")
    if status is None:
        LOGGER.warning(
            "Could not send queue status chat_id=%s; continuing download without a status message.",
            chat_id,
        )
    finished: list[str] = []
    failed: list[str] = []
    providers: set[str] = set()
    provider_notices: list[str] = []
    item_notices: list[str] = []
    skipped_duplicates = 0
    LOGGER.info("Queued download batch chat_id=%s items=%d", chat_id, len(supported_urls))
    async with QUEUE_LOCK:
        LOGGER.info("Started download batch chat_id=%s items=%d", chat_id, len(supported_urls))
        for index, url in enumerate(supported_urls, start=1):
            status = await update_status_with_retry(
                status,
                f"正在处理 {index}/{len(supported_urls)}…",
            )
            try:
                platform = SOURCES.source_name(url)
                if DOWNLOAD_INDEX.contains(url):
                    skipped_duplicates += 1
                    LOGGER.info(
                        "Skipped duplicate item chat_id=%s index=%d platform=%s",
                        chat_id,
                        index,
                        platform,
                    )
                    continue
                title_hint = title_hint_before_url(message.text or "", url)
                LOGGER.info(
                    "Starting item chat_id=%s index=%d/%d title_hint=%s",
                    chat_id,
                    index,
                    len(supported_urls),
                    bool(title_hint),
                )
                media = await asyncio.to_thread(
                    SOURCES.download, url, DOWNLOAD_DIR, title_hint
                )
                DOWNLOAD_INDEX.record(url, platform, media)
                finished.extend(
                    str(item.path.relative_to(DOWNLOAD_DIR)) for item in media
                )
                providers.update(item.provider for item in media)
                for item in media:
                    if item.provider_notice and item.provider_notice not in provider_notices:
                        provider_notices.append(item.provider_notice)
                    if item.notice and item.notice not in item_notices:
                        item_notices.append(item.notice)
                LOGGER.info(
                    "Completed item chat_id=%s index=%d files=%s",
                    chat_id,
                    index,
                    [item.path.name for item in media],
                )
            except SourceError as exc:
                failed.append(f"第 {index} 条：{exc}")
                LOGGER.warning("Item failed chat_id=%s index=%d reason=%s", chat_id, index, exc)
            except Exception:
                LOGGER.exception("Unexpected item failure chat_id=%s index=%d", chat_id, index)
                failed.append(f"第 {index} 条：网络或下载服务异常")

    lines = [f"处理完成：{len(finished)} 个文件"]
    if providers:
        lines.append(f"获取源：{'、'.join(sorted(providers))}")
    lines.extend(provider_notices)
    lines.extend(item_notices)
    if finished:
        lines.extend(f"✓ {name}" for name in finished[:10])
        if len(finished) > 10:
            lines.append(f"其余 {len(finished) - 10} 个文件已保存。")
    if failed:
        lines.extend(f"✗ {reason}" for reason in failed)
    if skipped_duplicates:
        lines.append(f"已跳过 {skipped_duplicates} 条已下载链接。")
    lines.append(f"保存位置：{DOWNLOAD_DIR}")
    final_text = "\n".join(lines)
    status = await update_status_with_retry(status, final_text)
    if status is None:
        await reply_with_retry(message, final_text, "final download result reply")
    LOGGER.info(
        "Finished download batch chat_id=%s files=%d failures=%d skipped_duplicates=%d",
        chat_id,
        len(finished),
        len(failed),
        skipped_duplicates,
    )


def build_application(token: str, health: PollingHealth) -> Application:
    bot = TrackingExtBot(
        token,
        get_updates_request=HTTPXRequest(
            connection_pool_size=TELEGRAM_GET_UPDATES_CONNECTION_POOL_SIZE,
        ),
    )
    POLLING_HEALTH_BY_BOT[id(bot)] = health
    application = Application.builder().bot(bot).build()
    application.bot_data["polling_health"] = health
    application.add_error_handler(handle_application_error)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_links))
    if application.job_queue is None:
        raise RuntimeError("Telegram polling watchdog requires the job-queue dependency.")
    application.job_queue.run_repeating(
        monitor_polling_health,
        interval=POLLING_HEALTH_CHECK_SECONDS,
        first=POLLING_HEALTH_CHECK_SECONDS,
        name="polling-health-monitor",
    )
    return application


def run_application(application: Application) -> None:
    """Run one polling lifecycle without closing the reusable event loop."""
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        bootstrap_retries=-1,
        # The watchdog deliberately starts a fresh application after a stalled
        # connection. Keeping this loop open lets the next polling lifecycle
        # reuse it instead of failing with "RuntimeError: Event loop is closed".
        close_loop=False,
    )


def main() -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("请先设置 TELEGRAM_BOT_TOKEN 环境变量。")
    LOGGER.info(
        "Starting bot download_dir=%s log_file=%s sources=%s access_restricted=%s",
        DOWNLOAD_DIR,
        LOG_PATH,
        [source.name for source in SOURCES.sources],
        bool(ALLOWED_USER_IDS),
    )
    while True:
        health = PollingHealth()
        application = build_application(token, health)
        try:
            run_application(application)
        finally:
            POLLING_HEALTH_BY_BOT.pop(id(application.bot), None)

        if not health.restart_requested:
            LOGGER.info("Bot process stopped")
            break
        LOGGER.warning(
            "Restarting Telegram application in %s seconds.",
            POLLING_RESTART_DELAY_SECONDS,
        )
        time.sleep(POLLING_RESTART_DELAY_SECONDS)


if __name__ == "__main__":
    main()
