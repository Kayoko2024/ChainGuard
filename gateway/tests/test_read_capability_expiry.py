"""Actual tool expiry validator; no chain/model data is fabricated by these units."""
import pytest
from chainguard_sandbox.default_library import validate_capability_expiry
from chainguard_sandbox.protocol import ToolError


@pytest.mark.parametrize('seconds',[1,3600,3601,86399,86400])
def test_default_library_accepts_task_windows_up_to_one_day(monkeypatch,seconds):
    monkeypatch.setattr('time.time',lambda:1000000)
    validate_capability_expiry(1000000+seconds)


@pytest.mark.parametrize('seconds',[-1,0])
def test_expired_credentials_are_still_rejected_at_the_boundary(monkeypatch,seconds):
    monkeypatch.setattr('time.time',lambda:1000000)
    with pytest.raises(ToolError,match='^RESERVATION_EXPIRED$'):
        validate_capability_expiry(1000000+seconds)


@pytest.mark.parametrize('seconds',[86401,172800])
def test_excessive_lifetime_is_distinguished_from_expiry(monkeypatch,seconds):
    monkeypatch.setattr('time.time',lambda:1000000)
    with pytest.raises(ToolError,match='^READ_CAPABILITY_WINDOW_INVALID$'):
        validate_capability_expiry(1000000+seconds)


@pytest.mark.parametrize('value',[True,False,1000001.0,'1000001',None])
def test_malformed_times_cannot_be_interpreted_as_authorization(monkeypatch,value):
    monkeypatch.setattr('time.time',lambda:1000000)
    with pytest.raises(ToolError,match='^SCHEMA_INVALID$'):
        validate_capability_expiry(value)
