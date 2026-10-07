from url_tools import extract_urls, title_hint_before_url


def test_extract_urls_preserves_order_and_removes_duplicates() -> None:
    text = (
        "First: https://xhslink.cn/o/first, "
        "then https://v.douyin.com/second/. "
        "again https://xhslink.cn/o/first"
    )

    assert extract_urls(text) == [
        "https://xhslink.cn/o/first",
        "https://v.douyin.com/second/",
    ]


def test_title_hint_uses_the_last_label_on_the_same_line() -> None:
    text = "\u3010previous\u3011\n\u3010Current title\u3011 https://v.douyin.com/example/"
    url = "https://v.douyin.com/example/"

    assert title_hint_before_url(text, url) == "Current title"


def test_title_hint_ignores_labels_on_another_line() -> None:
    text = "\u3010previous\u3011\nhttps://v.douyin.com/example/"

    assert title_hint_before_url(text, "https://v.douyin.com/example/") is None

