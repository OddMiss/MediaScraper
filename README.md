# Telegram 媒体下载机器人

一个运行在 Windows 本机的 Telegram 群聊机器人。它会自动识别普通群消息中的链接，将支持的链接按出现顺序串行下载到本地。

> 注意：请只保存你拥有权利下载的公开内容，并遵守各平台规则与适用法律。

当前已接入：

- 小红书视频：`xiaohongshu.com`、`xhslink.com`、`xhslink.cn`

机器人完成消息会始终标注实际使用的获取源。
- 抖音视频：`douyin.com`、`v.douyin.com`、`iesdouyin.com`
- 皮皮虾视频：`pipix.com`、`h5.pipix.com`、`pipixia.com`
- TikTok 视频：`tiktok.com`、`vm.tiktok.com`、`vt.tiktok.com`、`tiktokv.com`

项目采用来源插件架构，后续可扩展图文、视频、音频或文字内容，不需要改动 Telegram 消息处理与下载队列。

## 工作方式

```text
Telegram 群消息
  → 提取全部 HTTP(S) 链接
  → 找到支持该域名的来源插件
  → 进入全局串行队列
  → 解析媒体并下载到 ./downloads
  → 在群内汇报每个文件的结果
```

同一条消息中的多个链接、不同用户发送的链接，都会按队列顺序依次处理，避免同时下载导致网络、平台或磁盘压力过大。

每个成功下载的原始链接会写入 `downloads/index.json`，其中包含平台名称、下载时间和生成的文件名。同一链接再次出现时，机器人会跳过下载并在结果中提示，避免重复保存；仅在文件完整保存成功后才会写入索引。

## 安装与启动

要求：Windows、Python 3.11 或更新版本。

1. 获取项目并进入目录：

   ```powershell
   git clone https://github.com/<你的用户名>/VideoScraper.git
   cd VideoScraper
   ```

2. 安装依赖：

   ```powershell
   python -m pip install -r requirements.txt
   ```

3. 将 `.env.example` 复制为 `.env`，填入 Telegram BotFather 提供的 token：

   ```env
   TELEGRAM_BOT_TOKEN=替换为你的机器人Token
   ```

   可选：仅允许指定用户使用机器人。

   ```env
   ALLOWED_USER_IDS=123456789,987654321
   ```

   留空或不设置 `ALLOWED_USER_IDS` 即不限制用户。

4. 启动：

   ```powershell
   .\videoscraper.bat
   ```

   `videoscraper.bat` 会启动机器人主程序；关闭该窗口即可停止服务。

媒体固定保存到项目目录下的 `downloads` 文件夹，无需配置绝对路径。

## 日志

每次启动会在项目目录的 `logs` 文件夹创建一个新的 UTF-8 日志文件，名称为启动时间戳（例如 `20261007_111639_123456.log`）。日志同时显示在启动窗口中。

Python 业务日志会记录：

- 机器人启动、停止、下载目录、已注册来源及访问控制是否开启；
- 收到消息后的链接总数、白名单命中数、无效链接数及未授权访问；
- 批次进入队列、开始处理、每条链接处理完成或失败；
- URL 被路由到哪个来源插件；
- HelloTik / SaveTik 解析请求与结果摘要（媒体数量、是否取得标题）；
- 文件下载开始、HTTP 状态、声明大小、实际写入字节数、保存的文件名；
- 解析、网络或本地写入异常的错误信息与 Python 堆栈。

为避免泄露凭据，Telegram Bot API 的 HTTP 请求日志被限制为警告级别；日志不会输出机器人 token。下载失败时产生的 `.part` 临时文件会被自动删除。

如果 VPN 或代理短暂断开，Telegram 轮询会自动重试；这类 `NetworkError` 仅以警告写入日志，不会输出完整异常堆栈。

## 群内使用

直接在群里发送带链接的普通消息，不需要命令前缀：

```text
这两个都下载：
https://xhslink.cn/o/7S02kFsPuJn
https://xhslink.cn/o/67C7RoWf5fZ
```

也可直接粘贴抖音 App 的整段分享文本，机器人会自动抽取其中的链接：

```text
7.64 复制打开抖音，看看【作者的作品】 https://v.douyin.com/39SY8WZGBH8/ :8pm Z@z.te FhO:/ 04/22
```

机器人会回复处理进度与下载结果。为使机器人能收到普通群消息，请将其设为群管理员；否则 Telegram 的群隐私模式可能只转发命令消息。

链接采用白名单机制。当前仅允许上述已接入平台的域名；不在白名单内的链接会被提示为无效。白名单会随已注册的平台插件自动更新。

若平台没有返回作品标题，机器人会尝试使用同一行分享文本中、链接前最后一个 `【…】` 的内容作为文件名。例如抖音分享文本中的 `【青岛大军车行～军哥的作品】` 会保存为 `青岛大军车行～军哥的作品.mp4`；没有此类提示时才使用北京时间戳。

## 项目结构

```text
bot.py                 Telegram 消息入口、权限校验、全局串行队列
url_tools.py           从普通文本提取并去重 HTTP(S) 链接
source_registry.py     按 URL 选择已注册的平台插件
media_types.py         插件通用接口与视频/图片/文字结果类型
storage.py             安全命名、同名避让、通用流式保存
download_index.py      已成功下载链接的持久化去重索引
downloader.py          旧版单一小红书调用接口的兼容入口
xiaohongshu_source.py  小红书来源插件
douyin_source.py        抖音来源插件
pipixia_source.py       皮皮虾来源插件
tiktok_source.py        TikTok 来源插件
savetik_client.py       SaveTik 网页解析客户端
hellotik_client.py     HelloTik 多平台解析协议客户端
videoscraper.bat       Windows 启动入口
.env.example           可公开提交的配置模板
requirements.txt       运行依赖
requirements-dev.txt   开发与测试依赖
tests/                 无需网络与真实 Token 的单元测试
.github/workflows/     GitHub Actions 自动校验
downloads/             本地下载结果（运行时自动创建）
downloads/index.json   已成功下载的链接、平台、时间及文件名索引
logs/                  每次启动生成一个时间戳日志文件
```

## 开发与提交

开发环境可安装测试依赖并执行本地校验：

```powershell
python -m pip install -r requirements-dev.txt
python -m compileall -q .
python -m pytest
```

推送至 GitHub 后，`CI` 工作流会在 Python 3.11 环境中执行相同的语法检查与单元测试。新增平台的接入约定见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 新增平台接入

每个平台实现一个来源插件，并在 `bot.py` 的 `SOURCES` 中注册。插件必须满足两个方法：

- `matches(url) -> bool`：判断该插件是否支持此链接。
- `download(url, destination, title_hint=None) -> list[DownloadedMedia]`：下载一个或多个产物，返回统一的结果列表。`title_hint` 是消息中链接前的 `【…】` 文本，可在平台没有标题时作为文件名后备。

### 最小视频插件示例

新建 `example_source.py`：

```python
from pathlib import Path
from urllib.parse import urlparse

from media_types import DownloadedMedia, MediaKind
from storage import available_path, stream_to_file


class ExampleSource:
    name = "example"

    def matches(self, url: str) -> bool:
        host = (urlparse(url).hostname or "").lower()
        return host == "example.com" or host.endswith(".example.com")

    def download(
        self, url: str, destination: Path, title_hint: str | None = None
    ) -> list[DownloadedMedia]:
        # 在此调用目标平台允许的解析方式，取得标题与媒体 URL。
        title = "示例视频"
        media_url = "https://cdn.example.com/video.mp4"
        target = available_path(destination, title, ".mp4")
        stream_to_file(media_url, target)
        return [DownloadedMedia(MediaKind.VIDEO, target, title, url)]
```

然后在 `bot.py` 注册：

```python
from example_source import ExampleSource

SOURCES = SourceRegistry([
    XiaohongshuSource(),
    ExampleSource(),
])
```

机器人会自动识别 `example.com` 链接并进入现有串行队列。

### 图文与文字内容

一个插件可以返回多个结果，所以图文笔记可依次返回多张图片与视频；纯文字可先将内容写入 `.txt`，再返回 `MediaKind.TEXT`：

```python
return [
    DownloadedMedia(MediaKind.IMAGE, image_path, title, url),
    DownloadedMedia(MediaKind.IMAGE, second_image_path, title, url),
    DownloadedMedia(MediaKind.TEXT, article_path, title, url),
]
```

文件名统一交由 `storage.available_path()` 生成。它会清理 Windows 非法字符、标题为空时使用北京时间戳，并在重名时自动追加序号。

## 当前平台实现

小红书、抖音与皮皮虾来源插件通过 `hellotik_client.py` 解析公开分享链接；TikTok 来源插件通过 `savetik_client.py` 调用 SaveTik 网页的公开解析接口。两类插件都会将返回的视频 CDN 地址保存至本地。TikTok 支持完整作品链接及 `vm.tiktok.com`、`vt.tiktok.com` 等短链。

HelloTik 网页协议可能更新；若出现“未取得解析票据”或解密错误，需要更新 `hellotik_client.py` 内的当前协议字段。

请只下载你有权保存的内容。已支持平台的链接会被发送给对应的解析服务。


## 常见问题

- **机器人不回应普通链接**：确认机器人是群管理员，并确认本机 `videoscraper.bat` 正在运行。
- **提示暂不支持该来源**：该域名尚未注册来源插件。
- **下载完成但找不到文件**：在项目根目录的 `downloads` 中查看；机器人最后一条状态消息也会给出保存目录。
