"""Telegram link downloader with pluggable media sources."""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime
from pathlib import Path

from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters
from dotenv import load_dotenv

from download_index import DownloadIndex
from media_types import SourceError
from source_registry import SourceRegistry
from url_tools import extract_urls, title_hint_before_url
from douyin_source import DouyinSource
from pipixia_source import PipixiaSource
from tiktok_source import TikTokSource
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
# HTTP client request URLs include the Bot API token; keep them out of logs.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
LOGGER = logging.getLogger("bot")
# Read configuration next to this script.  Do not print the token or its value.
load_dotenv(SCRIPT_DIR / ".env")
DOWNLOAD_DIR = SCRIPT_DIR / "downloads"
DOWNLOAD_INDEX = DownloadIndex(DOWNLOAD_DIR / "index.json")
ALLOWED_USER_IDS = {int(value) for value in os.getenv("ALLOWED_USER_IDS", "").split(",") if value.strip()}
# Add each future platform implementation here.  The router keeps the bot and
# queue independent from whether a plugin downloads video, images, or text.
SOURCES = SourceRegistry(
    [XiaohongshuSource(), DouyinSource(), PipixiaSource(), TikTokSource()]
)
QUEUE_LOCK = asyncio.Lock()


def _authorised(update: Update) -> bool:
    return not ALLOWED_USER_IDS or (update.effective_user and update.effective_user.id in ALLOWED_USER_IDS)


async def handle_links(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    user_id = update.effective_user.id if update.effective_user else None
    chat_id = update.effective_chat.id if update.effective_chat else None
    if not _authorised(update):
        LOGGER.warning("Rejected unauthorized message chat_id=%s user_id=%s", chat_id, user_id)
        await message.reply_text("你没有使用此机器人的权限。")
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
        await message.reply_text(f"链接无效：不在允许列表中。\n当前允许：{whitelist}")
        return

    queue_text = f"发现 {len(supported_urls)} 个有效链接，已进入队列…"
    if invalid_urls:
        shown_urls = "\n".join(invalid_urls[:3])
        extra = "" if len(invalid_urls) <= 3 else f"\n另有 {len(invalid_urls) - 3} 条无效链接。"
        queue_text = f"以下链接无效，已跳过：\n{shown_urls}{extra}\n\n{queue_text}"
    status = await message.reply_text(queue_text)
    finished: list[str] = []
    failed: list[str] = []
    providers: set[str] = set()
    provider_notices: list[str] = []
    skipped_duplicates = 0
    LOGGER.info("Queued download batch chat_id=%s items=%d", chat_id, len(supported_urls))
    async with QUEUE_LOCK:
        LOGGER.info("Started download batch chat_id=%s items=%d", chat_id, len(supported_urls))
        for index, url in enumerate(supported_urls, start=1):
            await status.edit_text(f"正在处理 {index}/{len(supported_urls)}…")
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
                finished.extend(item.path.name for item in media)
                providers.update(item.provider for item in media)
                for item in media:
                    if item.provider_notice and item.provider_notice not in provider_notices:
                        provider_notices.append(item.provider_notice)
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
    if finished:
        lines.extend(f"✓ {name}" for name in finished[:10])
        if len(finished) > 10:
            lines.append(f"其余 {len(finished) - 10} 个文件已保存。")
    if failed:
        lines.extend(f"✗ {reason}" for reason in failed)
    if skipped_duplicates:
        lines.append(f"已跳过 {skipped_duplicates} 条已下载链接。")
    lines.append(f"保存位置：{DOWNLOAD_DIR}")
    await status.edit_text("\n".join(lines))
    LOGGER.info(
        "Finished download batch chat_id=%s files=%d failures=%d skipped_duplicates=%d",
        chat_id,
        len(finished),
        len(failed),
        skipped_duplicates,
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
    application = Application.builder().token(token).build()
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_links))
    try:
        application.run_polling(allowed_updates=Update.ALL_TYPES)
    finally:
        LOGGER.info("Bot process stopped")


if __name__ == "__main__":
    main()
