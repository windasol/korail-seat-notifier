"""에이전트 상태 머신 테스트"""

import pytest

from src.agent.state import AgentState, validate_transition


class TestStateTransitions:
    def test_idle_to_monitoring(self):
        assert validate_transition(AgentState.IDLE, AgentState.MONITORING)

    def test_idle_to_stopped(self):
        assert validate_transition(AgentState.IDLE, AgentState.STOPPED)

    def test_monitoring_to_detected(self):
        assert validate_transition(AgentState.MONITORING, AgentState.DETECTED)

    def test_monitoring_to_error(self):
        assert validate_transition(AgentState.MONITORING, AgentState.ERROR)

    def test_monitoring_to_stopped(self):
        assert validate_transition(AgentState.MONITORING, AgentState.STOPPED)

    def test_detected_to_notified(self):
        assert validate_transition(AgentState.DETECTED, AgentState.NOTIFIED)

    def test_detected_to_monitoring(self):
        assert validate_transition(AgentState.DETECTED, AgentState.MONITORING)

    def test_notified_to_monitoring(self):
        assert validate_transition(AgentState.NOTIFIED, AgentState.MONITORING)

    def test_notified_to_stopped(self):
        assert validate_transition(AgentState.NOTIFIED, AgentState.STOPPED)

    def test_error_to_monitoring(self):
        assert validate_transition(AgentState.ERROR, AgentState.MONITORING)

    def test_error_to_stopped(self):
        assert validate_transition(AgentState.ERROR, AgentState.STOPPED)

    def test_stopped_is_terminal(self):
        for state in AgentState:
            assert not validate_transition(AgentState.STOPPED, state)

    def test_invalid_idle_to_detected(self):
        assert not validate_transition(AgentState.IDLE, AgentState.DETECTED)

    def test_invalid_idle_to_notified(self):
        assert not validate_transition(AgentState.IDLE, AgentState.NOTIFIED)

    def test_invalid_idle_to_error(self):
        assert not validate_transition(AgentState.IDLE, AgentState.ERROR)
