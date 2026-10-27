"""Channel credential ↔ OS-secret-store plumbing (layer-correct shared home).

Lives in ``core/`` so BOTH the write side (``routers/channels.py`` create/update)
and the startup sweep (``channels/gateway.py``) can import it WITHOUT a router→
gateway→router cycle. The rule it enforces, in one place:

    A channel secret (Slack bot/app token) must NEVER sit in the ``channels.config``
    DB column — that column is exported verbatim into a git-tracked
    ``db-export/channels.sql.gz`` (see ``core/keychain.py``). Secrets live in the OS
    secret store instead.

Two entry points:
- ``extract_secrets_to_keystore`` — WRITE side: strip secret keys out of an
  incoming config, store them, return the sanitized config safe to persist.
- ``migrate_legacy_channel_secrets`` — STARTUP sweep: remediate any PRE-EXISTING
  row that still has a plaintext token in config (written before this migration),
  so the guarantee holds for the installed base, not just new writes. Without this
  sweep the write-path fix would leave legacy rows leaking on the next backup, and
  readers prefer config-first so such a row never self-heals. (Review HIGH finding.)
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from core import keychain

logger = logging.getLogger(__name__)

# OS secret-store service namespace for ALL channel credentials.
CHANNEL_CREDS_SERVICE = "com.swarmai.channel-creds"

# Secret config keys per channel_type that must never reach the DB column. Keyed
# by channel_type so only the relevant adapter's secrets are intercepted (Outlook
# has none — it uses a Midway cookie, config is {poll_interval_seconds:60}).
SECRET_CONFIG_KEYS: dict[str, list[str]] = {
    "slack": ["bot_token", "app_token"],
}


def keychain_account(channel_type: str, key: str) -> str:
    """Secret-store account id for (channel_type, key), e.g. 'slack:bot_token'.

    Keyed by channel_TYPE (not channel_id) because the two Slack-reading jobs
    (channel_monitor_fallback, executor) look the channel up by
    ``WHERE channel_type='slack'`` and have no channel_id in scope. Channels are
    upsert-by-type (one row per type), so this is unambiguous. MUST match the
    account strings the read sites (slack adapter, gateway, jobs) use.
    """
    return f"{channel_type}:{key}"


def extract_secrets_to_keystore(channel_type: str, config: Optional[dict]) -> dict:
    """Pop secret keys out of *config* into the OS secret store; return SANITIZED config.

    Returns a NEW dict safe to persist to the DB (no secret values). A secret with
    an empty/falsy value is left untouched in the store (a partial update that omits
    the token must not wipe the stored one). Non-secret channel types pass through
    unchanged. This is the single write-side chokepoint the leak fix depends on.
    """
    if not config or channel_type not in SECRET_CONFIG_KEYS:
        return config or {}
    sanitized = dict(config)
    for key in SECRET_CONFIG_KEYS[channel_type]:
        if key not in sanitized:
            continue  # key absent → caller isn't touching this secret, leave stored value
        value = sanitized.pop(key)
        account = keychain_account(channel_type, key)
        if value:
            # A real value → store/rotate it.
            if not keychain.set_secret(CHANNEL_CREDS_SERVICE, account, value):
                logger.error(
                    "failed to store %s secret for channel_type=%s in keystore",
                    key, channel_type,
                )
        else:
            # Key PRESENT but empty ("") → an explicit revoke/clear. Distinct from
            # key-absent (omitted) above: purge the stored secret so the credential
            # can actually be cleared (adversarial review — the old guard made
            # revocation impossible, silently retaining the prior token).
            keychain.delete_secret(CHANNEL_CREDS_SERVICE, account)
    return sanitized


def delete_channel_secrets(channel_type: str) -> None:
    """Remove all stored secrets for a channel type (called on channel delete).

    Without this, a deleted Slack channel's token lingers in the secret store and a
    later re-create silently reuses the stale credential if the user omits a token.
    """
    for key in SECRET_CONFIG_KEYS.get(channel_type, []):
        keychain.delete_secret(CHANNEL_CREDS_SERVICE, keychain_account(channel_type, key))


async def migrate_legacy_channel_secrets(channels: list[dict]) -> int:
    """Sweep pre-existing rows: move any config-resident token into the keystore.

    For each channel whose config STILL contains a secret key (a row written before
    the keystore migration), move the value into the secret store and rewrite the DB
    row with a sanitized config. Returns the number of rows remediated.

    This is the installed-base half of the root-cause fix: the write path protects
    NEW rows; this protects rows that already leaked. Idempotent — a row whose config
    has no secret key is skipped, so re-running on every startup is a cheap no-op.
    """
    from database import db  # local import — avoid import cycle at module load

    remediated = 0
    for ch in channels:
        channel_type = ch.get("channel_type", "")
        if channel_type not in SECRET_CONFIG_KEYS:
            continue
        config = ch.get("config", {})
        if isinstance(config, str):
            try:
                config = json.loads(config)
            except (json.JSONDecodeError, TypeError):
                continue
        if not isinstance(config, dict):
            continue
        # Does this row still carry a secret in config?
        if not any(config.get(k) for k in SECRET_CONFIG_KEYS[channel_type]):
            continue
        sanitized = extract_secrets_to_keystore(channel_type, config)
        try:
            await db.channels.update(ch["id"], {"config": sanitized})
            remediated += 1
            logger.warning(
                "migrated legacy %s channel %s: secret(s) moved from config to keystore",
                channel_type, ch.get("id"),
            )
        except Exception:
            logger.exception("failed to migrate legacy secrets for channel %s", ch.get("id"))
    return remediated
