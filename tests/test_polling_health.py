from polling_health import PollingHealth


def test_polling_health_detects_a_stalled_connection() -> None:
    health = PollingHealth(last_activity=100.0)

    assert not health.is_stalled(120.0, now=219.9)
    assert health.is_stalled(120.0, now=220.0)


def test_polling_health_records_new_activity() -> None:
    health = PollingHealth(last_activity=100.0)
    health.record_activity(now=150.0)

    assert not health.is_stalled(120.0, now=269.9)
