from freshness_check import latest_period, next_state_entry, verdict


def test_state_only_moves_when_content_changes():
    seeded = next_state_entry(None, "a", "2026-11-16", "2026-11-23")
    assert seeded == {"hash": "a", "changed_at": "2026-11-16"}  # seeded from modifiedTime
    assert next_state_entry(seeded, "a", "2026-11-23", "2026-11-23") == seeded  # weekly rewrite, same data
    assert next_state_entry(seeded, "b", "2026-11-23", "2026-11-23")["changed_at"] == "2026-11-23"
    # edited Wednesday, checked the following Monday: the edit date wins, not the run date
    assert next_state_entry(seeded, "b", "2026-11-18", "2026-11-23")["changed_at"] == "2026-11-18"
    assert next_state_entry(seeded, "b", "", "2026-11-23")["changed_at"] == "2026-11-23"


def test_verdict():
    assert verdict(0, 0, None, "2024-12-02") == "UNTRACKED"
    assert verdict(2, 0, "2026-11-16", "2024-12-02") == "STALE"
    assert verdict(2, 1, "2026-11-16", "2024-12-02") == "STALE"  # stale wins over a missing source
    assert verdict(2, 0, "2026-10-20", "2026-10-26") == "OK"
    assert verdict(2, 0, "2026-10-26", "2026-10-26") == "OK"  # same day counts as published
    assert verdict(2, 1, "2026-10-20", "2026-10-26") == "NO ACCESS"
    assert verdict(1, 1, None, "2026-10-26") == "NO ACCESS"


def test_latest_period_ignores_other_columns_and_ragged_rows():
    tabs = [[["state", "Year", "value"], ["Penang", 2023, 1], ["Penang", 2024], ["Penang"]], []]
    assert latest_period(tabs) == "2024"
    assert latest_period([[["state", "value"], ["Penang", 1]]]) == ""
