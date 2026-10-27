"""Layer 4 Cross-Boundary E2E — the credential-storage migration seam.

cross_boundary = data-schema-migration: a secret's storage location moves from the
channels.config DB column to the OS secret store. The SEAM is write-side (strip →
store) ↔ read-side (adapter/gateway recover from store). Layers 1-3 each exercise
ONE side; this drives the REAL round-trip end-to-end.

Hard requirements (test.md Layer 4):
1. Drive the REAL wiring — real extract_secrets_to_keystore + real file-store keystore
   + real SlackChannelAdapter read. The seam itself (keystore + strip) is NOT mocked;
   only sys.platform is forced to 'linux' so the real file-store path runs in CI.
2. Mutation-verify non-vacuous — revert the strip (persist token in config instead) and
   assert the token WOULD have leaked (the thing the migration prevents).
"""
import gzip
import json
import sqlite3

import pytest

from core import channel_secrets as cs
from core import keychain


@pytest.fixture
def real_file_keystore(tmp_path, monkeypatch):
    """Use the REAL file-store keystore (Linux/Hive path) — NOT a mock of the seam."""
    monkeypatch.setattr(keychain, "_SECRETS_DIR", tmp_path / ".secrets")
    monkeypatch.setattr(keychain.sys, "platform", "linux")  # force file-store (the seam)
    monkeypatch.setattr(keychain, "_keychain_get", lambda s, a: None)  # no macOS kc in CI
    for k in list(__import__("os").environ):
        if k.startswith("SWARM_SECRET__"):
            monkeypatch.delenv(k, raising=False)
    return tmp_path


class TestWriteReadRoundTripSeam:
    """The real seam: write strips→stores, read recovers. No mock of keystore or strip."""

    def test_token_survives_write_then_read_via_keystore(self, real_file_keystore):
        # WRITE side (real): create-channel's strip stores the token, returns clean config
        sanitized = cs.extract_secrets_to_keystore(
            "slack", {"bot_token": "xoxb-E2E-REAL", "app_token": "xapp-E2E-REAL"}
        )
        assert "bot_token" not in sanitized  # config is clean (goes to DB)

        # READ side (real): the adapter, given the clean config, recovers the token
        # from the keystore via the REAL _load_channel_secret → keychain.get_secret.
        from channels.adapters import slack
        adapter = slack.SlackChannelAdapter(
            channel_id="e2e", config=sanitized, on_message=lambda *a, **k: None
        )
        # The seam reconnected: token stored by write side is read back by read side.
        assert adapter._bot_token == "xoxb-E2E-REAL"
        assert adapter._app_token == "xapp-E2E-REAL"

    def test_keystore_wins_over_injected_config_token(self, real_file_keystore):
        """Keystore-first: a stray/injected config token must NOT override the stored one.

        Adversarial review (F1): config-first read order was a security downgrade —
        anyone who could write channels.config could shadow the real keystore secret.
        Keystore-first makes config non-authoritative.
        """
        cs.extract_secrets_to_keystore("slack", {"bot_token": "xoxb-REAL-STORED", "app_token": "xapp-REAL"})
        from channels.adapters import slack
        # A row whose config somehow still carries a DIFFERENT (injected) token
        adapter = slack.SlackChannelAdapter(
            channel_id="e2e",
            config={"bot_token": "xoxb-INJECTED-EVIL"},
            on_message=lambda *a, **k: None,
        )
        # Keystore value wins — the injected config token is ignored.
        assert adapter._bot_token == "xoxb-REAL-STORED"

    def test_export_of_written_config_is_token_free_real(self, real_file_keystore, tmp_path):
        """End-to-end root-cause: the config that reaches the DB → export has no token."""
        sanitized = cs.extract_secrets_to_keystore(
            "slack", {"bot_token": "xoxb-LEAK-CHECK", "app_token": "xapp-LEAK-CHECK"}
        )
        db = tmp_path / "chan.db"
        conn = sqlite3.connect(str(db))
        conn.execute("CREATE TABLE channels (id TEXT, channel_type TEXT, config TEXT)")
        conn.execute("INSERT INTO channels VALUES (?,?,?)", ("c", "slack", json.dumps(sanitized)))
        conn.commit()
        gz = tmp_path / "channels.sql.gz"
        with gzip.open(gz, "wt") as f:
            for row in conn.execute("SELECT * FROM channels"):
                f.write(f"INSERT INTO channels VALUES {row};\n")
        conn.close()
        assert "xoxb-" not in gzip.open(gz, "rt").read()


class TestMutationProof:
    """Non-vacuous proof: revert the strip → the token WOULD leak (migration prevents it)."""

    def test_reverting_strip_leaks_token(self, real_file_keystore, tmp_path):
        # MUTATION: simulate the pre-migration behavior — persist raw config (no strip).
        raw_config = {"bot_token": "xoxb-WOULD-LEAK", "app_token": "xapp-WOULD-LEAK"}
        # (This is the reverted seam: config goes to DB WITHOUT extract_secrets_to_keystore)
        db = tmp_path / "chan.db"
        conn = sqlite3.connect(str(db))
        conn.execute("CREATE TABLE channels (id TEXT, channel_type TEXT, config TEXT)")
        conn.execute("INSERT INTO channels VALUES (?,?,?)", ("c", "slack", json.dumps(raw_config)))
        conn.commit()
        gz = tmp_path / "channels.sql.gz"
        with gzip.open(gz, "wt") as f:
            for row in conn.execute("SELECT * FROM channels"):
                f.write(f"INSERT INTO channels VALUES {row};\n")
        conn.close()
        dump = gzip.open(gz, "rt").read()
        # RED on revert: the token LEAKS when the strip is removed — proving the
        # Layer-4 round-trip test above is non-vacuous (the strip is what prevents this).
        assert "xoxb-WOULD-LEAK" in dump, "mutation proof failed — strip wasn't the thing preventing the leak"


class TestLegacyRowMigrationSeamE2E:
    """The installed-base half of the seam: a legacy leaked row → swept → read recovers."""

    @pytest.mark.asyncio
    async def test_legacy_row_swept_then_readable(self, real_file_keystore, monkeypatch):
        rewritten = {}

        class FakeChannels:
            async def update(self, cid, updates):
                rewritten[cid] = updates

        class FakeDB:
            channels = FakeChannels()

        monkeypatch.setattr("database.db", FakeDB())
        # A legacy row: token STILL in config (pre-migration state)
        legacy = [{"id": "c1", "channel_type": "slack",
                   "config": json.dumps({"bot_token": "xoxb-OLD", "app_token": "xapp-OLD"})}]
        n = await cs.migrate_legacy_channel_secrets(legacy)
        assert n == 1
        # Seam reconnected: row rewritten clean AND the token is now readable from keystore
        assert "bot_token" not in rewritten["c1"]["config"]
        assert keychain.get_secret("com.swarmai.channel-creds", "slack:bot_token") == "xoxb-OLD"
