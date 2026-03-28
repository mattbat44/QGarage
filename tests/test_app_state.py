"""Tests for AppState enum and AppHealth state machine."""

from qgarage.core.app_state import AppHealth, AppState, MAX_CONSECUTIVE_ERRORS


class TestAppState:
    def test_all_states_exist(self):
        expected = {
            "DISCOVERED",
            "LOADING",
            "READY",
            "RUNNING",
            "ERROR",
            "CRASHED",
            "DISABLED",
            "INSTALLING",
        }
        assert {s.name for s in AppState} == expected

    def test_states_are_unique(self):
        values = [s.value for s in AppState]
        assert len(values) == len(set(values))


class TestAppHealth:
    def test_initial_state(self):
        h = AppHealth()
        assert h.state == AppState.DISCOVERED
        assert h.consecutive_errors == 0
        assert h.last_error is None

    def test_record_success(self):
        h = AppHealth()
        h.state = AppState.LOADING
        h.record_success()
        assert h.state == AppState.READY
        assert h.consecutive_errors == 0

    def test_record_error_transitions_to_error(self):
        h = AppHealth()
        h.record_error("something broke")
        assert h.state == AppState.ERROR
        assert h.consecutive_errors == 1
        assert "something broke" in h.last_error
        assert h.last_error_time is not None

    def test_consecutive_errors_trigger_crash(self):
        h = AppHealth()
        for i in range(MAX_CONSECUTIVE_ERRORS):
            h.record_error(f"error #{i}")
        assert h.state == AppState.CRASHED
        assert h.consecutive_errors == MAX_CONSECUTIVE_ERRORS

    def test_success_resets_error_counter(self):
        h = AppHealth()
        h.record_error("err1")
        h.record_error("err2")
        assert h.consecutive_errors == 2
        h.record_success()
        assert h.consecutive_errors == 0
        assert h.state == AppState.READY

    def test_reset_clears_everything(self):
        h = AppHealth()
        for _ in range(MAX_CONSECUTIVE_ERRORS):
            h.record_error("boom")
        assert h.state == AppState.CRASHED
        h.reset()
        assert h.state == AppState.DISCOVERED
        assert h.consecutive_errors == 0
        assert h.last_error is None

    def test_error_log_accumulates(self):
        h = AppHealth()
        h.record_error("first")
        h.record_error("second")
        assert len(h.error_log) == 2
        assert "first" in h.error_log[0]
        assert "second" in h.error_log[1]
