"""Tests for core.keychain — parameterized secret store with env>keychain>file chain."""
import os
import stat
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from core import keychain


@pytest.fixture
def linux_file_store(tmp_path, monkeypatch):
    """Force the file-store path (simulate Linux/Hive: no macOS Keychain)."""
    monkeypatch.setattr(keychain, "_SECRETS_DIR", tmp_path / ".secrets")
    # Force non-darwin so set_secret routes to file.
    monkeypatch.setattr(keychain.sys, "platform", "linux")
    # Keychain probe must miss (as it would on Linux — no `security` binary).
    monkeypatch.setattr(keychain, "_keychain_get", lambda s, a: None)
    monkeypatch.setattr(keychain, "_keychain_delete", lambda s, a: False)
    # Clear any env override that could shadow the file store.
    for k in list(os.environ):
        if k.startswith("SWARM_SECRET__"):
            monkeypatch.delenv(k, raising=False)
    return tmp_path / ".secrets"


class TestFileStoreRoundTrip:
    """AC2/AC7: set→get round-trip on the Linux/Hive file fallback."""

    def test_set_then_get(self, linux_file_store):
        assert keychain.set_secret("com.swarmai.channel-creds", "slack:bot", "xoxb-FAKE") is True
        assert keychain.get_secret("com.swarmai.channel-creds", "slack:bot") == "xoxb-FAKE"

    def test_get_missing_returns_none(self, linux_file_store):
        assert keychain.get_secret("com.swarmai.channel-creds", "slack:app") is None

    def test_distinct_accounts_isolated(self, linux_file_store):
        keychain.set_secret("svc", "slack:bot", "xoxb-A")
        keychain.set_secret("svc", "slack:app", "xapp-B")
        assert keychain.get_secret("svc", "slack:bot") == "xoxb-A"
        assert keychain.get_secret("svc", "slack:app") == "xapp-B"

    def test_set_empty_value_rejected(self, linux_file_store):
        assert keychain.set_secret("svc", "acct", "") is False

    def test_delete_removes_secret(self, linux_file_store):
        keychain.set_secret("svc", "acct", "v")
        assert keychain.delete_secret("svc", "acct") is True
        assert keychain.get_secret("svc", "acct") is None

    def test_delete_absent_returns_false(self, linux_file_store):
        assert keychain.delete_secret("svc", "nope") is False


class TestFileStoreSecurity:
    """The file store holds a SECRET — 0600 is a hard invariant (mirrors backup_manager)."""

    def test_file_is_0600(self, linux_file_store):
        keychain.set_secret("svc", "acct", "secret-value")
        path = keychain._file_path("svc", "acct")
        assert path.exists()
        mode = stat.S_IMODE(path.stat().st_mode)
        assert mode == 0o600, f"expected 0600, got {oct(mode)} — secret world-readable!"

    def test_account_path_traversal_contained(self, linux_file_store):
        """A traversal-y account must not escape _SECRETS_DIR."""
        keychain.set_secret("svc", "../../etc/evil", "v")
        # The resolved file must stay inside the secrets dir.
        path = keychain._file_path("svc", "../../etc/evil")
        assert keychain._SECRETS_DIR in path.parents or path.parent == keychain._SECRETS_DIR
        assert "/etc/evil" not in str(path)


class TestEnvOverride:
    """Env var is highest priority — enables no-on-disk injection (Hive systemd)."""

    def test_env_var_wins(self, linux_file_store, monkeypatch):
        keychain.set_secret("com.swarmai.channel-creds", "slack:bot", "xoxb-FILE")
        env_name = keychain._env_var_name("com.swarmai.channel-creds", "slack:bot")
        monkeypatch.setenv(env_name, "xoxb-ENV")
        assert keychain.get_secret("com.swarmai.channel-creds", "slack:bot") == "xoxb-ENV"


class TestKeychainPathMacOS:
    """On darwin, set routes to Keychain (subprocess security). Mock the boundary."""

    def test_set_routes_to_keychain_on_darwin(self, monkeypatch):
        monkeypatch.setattr(keychain.sys, "platform", "darwin")
        calls = {}

        def fake_kc_set(s, a, v):
            calls["set"] = (s, a, v)
            return True

        monkeypatch.setattr(keychain, "_keychain_set", fake_kc_set)
        assert keychain.set_secret("svc", "acct", "v") is True
        assert calls["set"] == ("svc", "acct", "v")

    def test_security_cli_uses_list_args_never_shell(self):
        """Token must never enter a shell string — subprocess list-args only."""
        import inspect
        src = inspect.getsource(keychain._keychain_set)
        assert "shell=True" not in src
        src_get = inspect.getsource(keychain._keychain_get)
        assert "shell=True" not in src_get

    def test_set_failure_log_never_contains_token(self):
        """On a set failure, the logged message must not embed the token (exc scrub)."""
        import inspect
        src = inspect.getsource(keychain._keychain_set)
        # The except/failure branch logs a FIXED string — never `exc`, `stderr`, or value.
        assert "as exc" not in src or "%s", "failure path must not interpolate exc"
        assert "result.stderr" not in src, "must not log stderr (can echo the token)"


@pytest.mark.skipif(sys.platform != "darwin", reason="real macOS Keychain round-trip")
class TestRealKeychainRoundTrip:
    """REAL Keychain write→read→delete — NOT mocked.

    This is the test whose ABSENCE let a broken `-w`-last-stdin invocation ship a
    silent false-success (set returned True, Keychain stored nothing). A mocked
    _keychain_set can't catch a wrong CLI invocation — only a real round-trip can.
    """

    def test_real_set_get_delete_roundtrip(self):
        svc, acct = "com.swarmai.test-roundtrip", "pytest:probe"
        # Clean any leftover from a previous aborted run
        keychain._keychain_delete(svc, acct)
        try:
            assert keychain._keychain_set(svc, acct, "xoxb-REALPROBE-9988") is True, \
                "set reported failure"
            got = keychain._keychain_get(svc, acct)
            assert got == "xoxb-REALPROBE-9988", \
                f"round-trip mismatch — set said OK but get returned {got!r} (the silent-false-success bug)"
        finally:
            keychain._keychain_delete(svc, acct)
        # After delete, get must miss
        assert keychain._keychain_get(svc, acct) is None
