import pytest


@pytest.fixture(autouse=True)
def _isolated_spend_ledger(tmp_path, monkeypatch):
    """The spend ledger and deploy settings are per test, so no test writes ./data/spend.sqlite."""
    monkeypatch.setenv("SPEND_DB_PATH", str(tmp_path / "spend.sqlite"))
    for name in ("ALLOWED_ORIGINS", "APP_ENV", "DAILY_SPEND_CAP_USD", "MONTHLY_SPEND_CAP_USD", "EST_COST_PER_CALL_USD"):
        monkeypatch.delenv(name, raising=False)
