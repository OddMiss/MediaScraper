# 参与开发

感谢你为 VideoScraper 增加平台、修复问题或改进文档。

## 本地准备

1. 复制 `.env.example` 为 `.env`，并填入自己的 Telegram Bot Token；不要提交 `.env`。
2. 安装开发依赖：`python -m pip install -r requirements-dev.txt`。
3. 执行校验：`python -m compileall -q .` 与 `python -m pytest`。

## 新增平台来源

每个平台来源保持一个独立的 `*_source.py` 文件，实现 `MediaSource` 约定：

- 声明稳定的平台名称 `name` 与允许匹配的域名集合 `hosts`；
- `matches(url)` 仅接受本平台域名；
- `download(url, destination, title_hint)` 返回 `list[DownloadedMedia]`；
- 使用 `storage.available_path()` 生成文件名、使用 `storage.stream_to_file()` 保存媒体；
- 解析失败时抛出面向用户的 `SourceError`，不要吞掉异常；
- 在返回结果中填写实际处理服务的 `provider`。若切换服务，填写 `provider_notice`，机器人会将变化告知用户。

最后在 `bot.py` 的 `SOURCES` 中注册新插件，并为域名匹配、链接提取或文件命名增加相应测试。

## 提交约定

- 不提交 `.env`、下载媒体、日志、访问令牌或真实用户信息。
- 保持改动聚焦，避免顺手格式化无关文件。
- 新功能请同步更新 `README.md` 的支持平台和使用说明。
- 仅处理你拥有保存权限的公开内容，并遵守平台规则及适用法律。

