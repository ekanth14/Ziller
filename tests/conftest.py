"""Root tests get the same isolation as cryptoscope/tests: never touch production governor state."""
import pytest

from cryptoscope.security.halt_state import GovernorState


@pytest.fixture(autouse=True)
def isolated_governor_state(tmp_path, monkeypatch):
    path = tmp_path / "governor.db"
    monkeypatch.setenv("GOVERNOR_STATE_DB", str(path))
    monkeypatch.delenv("TRADING_MODE", raising=False)
    GovernorState(path).resume_local_admin(admin_reauthenticated=True, actor="isolated-test-admin")
