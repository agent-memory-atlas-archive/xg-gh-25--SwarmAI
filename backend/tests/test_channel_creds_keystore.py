"""Slack credential keystore migration — secrets never reach the git-exported DB.

Covers:
- AC1: create/update strips bot_token/app_token out of config into the keystore
- AC4: Outlook (and other non-secret channel types) config is untouched
- AC6 (root cause): a channels-table export carries NO token after the strip
"""
import gzip
import sqlite3
from pathlib import Path

import pytest

from core import channel_secrets as cs
from core import keychain


@pytest.fixture
def mem_keystore(monkeypatch):
    """In-memory stand-in for the OS secret store (no real Keychain/file writes)."""
    store: dict[tuple[str, str], str] = {}
    monkeypatch.setattr(keychain, "set_secret", lambda s, a, v: (store.__setitem__((s, a), v), True)[1])
    monkeypatch.setattr(keychain, "get_secret", lambda s, a: store.get((s, a)))
    monkeypatch.setattr(keychain, "delete_secret", lambda s, a: (store.pop((s, a), None) is not None))
    return store


class TestWriteSideStrip:
    """AC1: secrets are popped from config into the keystore before DB persist."""

    def test_slack_tokens_stripped_from_config(self, mem_keystore):
        config = {"bot_token": "xoxb-FAKE123", "app_token": "xapp-FAKE456", "other": "keep"}
        sanitized = cs.extract_secrets_to_keystore("slack", config)
        assert "bot_token" not in sanitized
        assert "app_token" not in sanitized
        assert sanitized["other"] == "keep"
        # ...and they landed in the keystore under the agreed coordinates
        assert mem_keystore[("com.swarmai.channel-creds", "slack:bot_token")] == "xoxb-FAKE123"
        assert mem_keystore[("com.swarmai.channel-creds", "slack:app_token")] == "xapp-FAKE456"

    def test_original_config_not_mutated(self, mem_keystore):
        config = {"bot_token": "xoxb-FAKE", "app_token": "xapp-FAKE"}
        cs.extract_secrets_to_keystore("slack", config)
        # caller's dict must be left intact (we return a NEW sanitized dict)
        assert config["bot_token"] == "xoxb-FAKE"

    def test_omitted_token_does_not_overwrite_stored(self, mem_keystore):
        # A partial update where the key is ABSENT must NOT wipe the stored one.
        cs.extract_secrets_to_keystore("slack", {"bot_token": "xoxb-REAL", "app_token": "xapp-REAL"})
        cs.extract_secrets_to_keystore("slack", {"app_token": "xapp-NEW"})  # bot_token key absent
        assert mem_keystore[("com.swarmai.channel-creds", "slack:bot_token")] == "xoxb-REAL"
        assert mem_keystore[("com.swarmai.channel-creds", "slack:app_token")] == "xapp-NEW"

    def test_explicit_empty_token_clears_stored(self, mem_keystore):
        # Key PRESENT with "" is an explicit revoke — must PURGE the stored secret
        # (adversarial review: old `if value:` guard made revocation impossible).
        cs.extract_secrets_to_keystore("slack", {"bot_token": "xoxb-REAL", "app_token": "xapp-REAL"})
        cs.extract_secrets_to_keystore("slack", {"bot_token": "", "app_token": "xapp-KEEP"})
        assert ("com.swarmai.channel-creds", "slack:bot_token") not in mem_keystore  # revoked
        assert mem_keystore[("com.swarmai.channel-creds", "slack:app_token")] == "xapp-KEEP"


class TestOutlookUntouched:
    """AC4: non-secret channel types pass config through unchanged, keystore untouched."""

    def test_outlook_config_passthrough(self, mem_keystore):
        config = {"poll_interval_seconds": 60}
        sanitized = cs.extract_secrets_to_keystore("outlook", config)
        assert sanitized == {"poll_interval_seconds": 60}
        assert len(mem_keystore) == 0  # nothing written to the secret store

    def test_none_config_safe(self, mem_keystore):
        assert cs.extract_secrets_to_keystore("slack", None) == {}
        assert cs.extract_secrets_to_keystore("outlook", None) == {}


class TestExportHasNoToken:
    """AC6 (root cause): a channels-table SQL export carries no xoxb-/xapp- after strip."""

    def test_sanitized_config_export_is_token_free(self, mem_keystore, tmp_path):
        # Simulate the DB write with the SANITIZED config (what create_channel now stores)
        sanitized = cs.extract_secrets_to_keystore(
            "slack", {"bot_token": "xoxb-SECRET999", "app_token": "xapp-SECRET888"}
        )
        import json
        db = tmp_path / "t.db"
        conn = sqlite3.connect(str(db))
        conn.execute("CREATE TABLE channels (id TEXT, channel_type TEXT, config TEXT)")
        conn.execute(
            "INSERT INTO channels VALUES (?,?,?)",
            ("c1", "slack", json.dumps(sanitized)),
        )
        conn.commit()
        # Emulate git_sync_engine export: SELECT * → gzip
        gz = tmp_path / "channels.sql.gz"
        with gzip.open(gz, "wt") as f:
            for row in conn.execute("SELECT * FROM channels"):
                f.write(f"INSERT INTO channels VALUES {row};\n")
        conn.close()
        dump = gzip.open(gz, "rt").read()
        assert "xoxb-" not in dump, "bot_token leaked into DB export!"
        assert "xapp-" not in dump, "app_token leaked into DB export!"


class TestDeleteSecrets:
    """A deleted channel's stored secrets must not linger (review LOW finding)."""

    def test_delete_purges_both_keys(self, mem_keystore):
        cs.extract_secrets_to_keystore("slack", {"bot_token": "xoxb-X", "app_token": "xapp-Y"})
        assert len(mem_keystore) == 2
        cs.delete_channel_secrets("slack")
        assert ("com.swarmai.channel-creds", "slack:bot_token") not in mem_keystore
        assert ("com.swarmai.channel-creds", "slack:app_token") not in mem_keystore

    def test_delete_non_secret_type_noop(self, mem_keystore):
        cs.delete_channel_secrets("outlook")  # must not raise
        assert len(mem_keystore) == 0


class TestLegacyMigrationSweep:
    """HIGH: a pre-existing row with a token still in config must be remediated on startup."""

    @pytest.mark.asyncio
    async def test_legacy_row_migrated(self, mem_keystore, monkeypatch):
        import json
        updates_applied = {}

        class FakeChannels:
            async def update(self, cid, updates):
                updates_applied[cid] = updates
                return updates

        class FakeDB:
            channels = FakeChannels()

        monkeypatch.setattr("database.db", FakeDB())
        legacy = [{
            "id": "c1", "channel_type": "slack",
            "config": json.dumps({"bot_token": "xoxb-LEGACY", "app_token": "xapp-LEGACY", "keep": 1}),
        }]
        n = await cs.migrate_legacy_channel_secrets(legacy)
        assert n == 1
        # token moved into keystore
        assert mem_keystore[("com.swarmai.channel-creds", "slack:bot_token")] == "xoxb-LEGACY"
        # row rewritten with sanitized config (no token, non-secret key kept)
        new_cfg = updates_applied["c1"]["config"]
        assert "bot_token" not in new_cfg and "app_token" not in new_cfg
        assert new_cfg["keep"] == 1

    @pytest.mark.asyncio
    async def test_clean_row_is_noop(self, mem_keystore, monkeypatch):
        import json
        touched = []

        class FakeChannels:
            async def update(self, cid, updates):
                touched.append(cid)

        class FakeDB:
            channels = FakeChannels()

        monkeypatch.setattr("database.db", FakeDB())
        # Already-sanitized slack row + an outlook row → zero migrations, zero writes
        clean = [
            {"id": "c1", "channel_type": "slack", "config": json.dumps({"other": "x"})},
            {"id": "c2", "channel_type": "outlook", "config": json.dumps({"poll_interval_seconds": 60})},
        ]
        n = await cs.migrate_legacy_channel_secrets(clean)
        assert n == 0
        assert touched == []  # idempotent — no DB writes on a clean sweep
