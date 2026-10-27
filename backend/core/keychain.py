"""Generic OS-native secret storage — parameterized service + account.

A credential store that keeps secrets OUT of any git-backed DB column or file.
Priority chain mirrors ``backup_manager`` (the proven production pattern), but
parameterized by (service, account) so ANY caller — channel adapters, future MCP
secrets — stores through one safe entrance instead of a per-feature copy:

    get:  env var  >  macOS Keychain  >  file (~/.swarm-ai/.secrets/, Linux/Hive)
    set:  macOS → Keychain;  non-macOS → file (chmod 600)

**Why this exists (root-cause fix):** credentials written into the ``channels``
DB ``config`` column are exported verbatim by ``git_sync_engine`` (SELECT* → raw
INSERT, zero redaction) into a git-tracked ``db-export/channels.sql.gz`` and
pushed to the backup repo. Storing secrets HERE instead keeps them off that path
entirely — the leak is fixed at the source, not redacted downstream.

**Cross-platform (Gate-1 catch):** SwarmServer/Hive runs this same code on Amazon
Linux 2023 where the ``security`` CLI does not exist. The file fallback is NOT
optional — without it every Slack channel would die on Hive. This module carries
the SAME env>keychain>file chain as ``backup_manager`` for exactly that reason.

Secrets never enter a shell string (``subprocess`` list-args only, never
``shell=True``) and the env-var read enables a secret to be injected without any
on-disk persistence at all.
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Root dir for the Linux/Hive file fallback. Each (service, account) secret is a
# single 0600 file under here. Kept distinct from backup_manager's single
# ~/.swarm-ai/.backup-token so the two stores never collide.
_SECRETS_DIR = Path(os.path.expanduser("~/.swarm-ai/.secrets"))

# A (service, account) pair maps to one filename. Both are caller-controlled, so
# sanitize to a safe filename charset — a traversal-y account like "../../x" must
# not escape _SECRETS_DIR. Non-[A-Za-z0-9._-] → "_".
_SAFE_CHARS = re.compile(r"[^A-Za-z0-9._-]")


def _env_var_name(service: str, account: str) -> str:
    """Env-var override name for a (service, account): SWARM_SECRET__<svc>__<acct>.

    Uppercased, non-alnum → underscore. Lets a secret be injected via environment
    (e.g. a Hive systemd unit) with NO on-disk persistence — highest priority,
    same as backup_manager's SWARM_BACKUP_TOKEN.
    """
    safe = lambda s: re.sub(r"[^A-Za-z0-9]", "_", s).upper()
    return f"SWARM_SECRET__{safe(service)}__{safe(account)}"


def _file_path(service: str, account: str) -> Path:
    """Resolve the 0600 fallback file for (service, account), traversal-safe."""
    fname = f"{_SAFE_CHARS.sub('_', service)}__{_SAFE_CHARS.sub('_', account)}"
    return _SECRETS_DIR / fname


def _keychain_get(service: str, account: str) -> Optional[str]:
    """Read from macOS Keychain. None if not found / not macOS (FileNotFoundError)."""
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-a", account, "-s", service, "-w"],
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except Exception as exc:  # noqa: BLE001
        # DEBUG not WARNING: get_secret() calls this on EVERY platform, so off-macOS
        # `security` is absent (FileNotFoundError) BY DESIGN and we fall through to
        # the file store. An expected miss, not an incident.
        logger.debug("keychain lookup unavailable for %s/%s (%s); trying file", service, account, exc)
        return None


def _keychain_set(service: str, account: str, value: str) -> bool:
    """Write to macOS Keychain (-U upserts). True on success.

    Token delivery (meta-review CRITICAL — empirically verified on macOS):
    `-w` as the LAST option does NOT read a stdin pipe — it opens an interactive
    prompt WITH a retype confirmation, which on a piped EOF fails "passwords don't
    match", stores NOTHING, yet exits rc=0 (a silent false-success). So the token
    MUST be passed as the `-w <value>` argv element — the form backup_manager.py
    has used in production. The residual exposure (token visible in this process's
    own argv to a SAME-USER `ps`) is the identical, already-accepted tradeoff
    backup_manager makes; a cross-user box cannot see it, and the daemon runs as
    the user who owns the data.

    Other hardening kept:
    - `-T /usr/bin/security` pins the item ACL to the security tool, so a re-signed
      daemon can still re-read non-interactively (no surprise prompt → timeout).
    - On failure log a FIXED string, never `exc` / stderr — a CalledProcessError's
      str() embeds the argv (incl. the token).
    """
    try:
        result = subprocess.run(
            ["security", "add-generic-password", "-a", account, "-s", service,
             "-U", "-T", "/usr/bin/security", "-w", value],
            capture_output=True, timeout=5,
        )
        if result.returncode != 0:
            logger.warning("failed to store secret %s/%s in keychain (rc=%s)",
                           service, account, result.returncode)
            return False
        return True
    except Exception:  # noqa: BLE001
        logger.warning("failed to store secret %s/%s in keychain (exception)", service, account)
        return False


def _keychain_delete(service: str, account: str) -> bool:
    """Delete from macOS Keychain. True if removed; False if absent / not macOS."""
    try:
        result = subprocess.run(
            ["security", "delete-generic-password", "-a", account, "-s", service],
            capture_output=True, timeout=5,
        )
        return result.returncode == 0
    except Exception as exc:  # noqa: BLE001
        logger.debug("keychain delete unavailable for %s/%s (%s)", service, account, exc)
        return False


def _file_get(service: str, account: str) -> Optional[str]:
    """Read from the Linux/Hive 0600 file store. None if absent."""
    path = _file_path(service, account)
    if path.exists():
        try:
            return path.read_text().strip()
        except Exception:
            pass
    return None


def _file_set(service: str, account: str, value: str) -> bool:
    """Write to the file store with 0600 set BEFORE the secret touches disk."""
    path = _file_path(service, account)
    try:
        # O_CREAT with 0o600 up-front: the previous write-then-chmod order left the
        # secret world-readable under the default umask for a window, and a failing
        # chmod returned False with the secret already disclosed. (backup_manager's
        # hard-won invariant — mirror it.)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Also lock the containing dir down to 0700 (defense in depth).
        try:
            os.chmod(path.parent, 0o700)
        except OSError:
            pass
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            # fchmod on the OPEN fd BEFORE writing — closes the one residual case
            # O_CREAT's mode arg misses: a PRE-EXISTING file keeps its old (possibly
            # wider) mode on open, so without this the secret would hit disk under
            # that mode until the post-write chmod. fchmod-before-write = no window
            # on either the new-file or pre-existing-file path.
            os.fchmod(fd, 0o600)
            os.write(fd, (value + "\n").encode())
        finally:
            os.close(fd)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("failed to write secret %s/%s to %s: %s", service, account, path, exc)
        return False


def _file_delete(service: str, account: str) -> bool:
    """Delete the file-store secret. True if removed; False if absent."""
    path = _file_path(service, account)
    try:
        path.unlink()
        return True
    except FileNotFoundError:
        return False
    except Exception as exc:  # noqa: BLE001
        logger.warning("failed to delete secret file %s: %s", path, exc)
        return False


# ---------------------------------------------------------------------------
# Public API — env > keychain(macOS) > file(Linux)
# ---------------------------------------------------------------------------

def get_secret(service: str, account: str) -> Optional[str]:
    """Return the secret for (service, account), or None if stored nowhere.

    Priority: env var (``SWARM_SECRET__<SVC>__<ACCT>``) > macOS Keychain > file.
    Safe on every platform — on Linux the Keychain probe misses quietly and the
    file store answers.
    """
    env_val = os.environ.get(_env_var_name(service, account))
    if env_val:
        return env_val
    kc = _keychain_get(service, account)
    if kc:
        return kc
    return _file_get(service, account)


def set_secret(service: str, account: str, value: str) -> bool:
    """Persist the secret for (service, account). True on success.

    macOS → Keychain; everywhere else → 0600 file. Mirrors
    ``backup_manager.set_backup_token``'s platform split so Hive/Linux is a
    first-class target, not an afterthought.
    """
    if not value:
        return False
    if sys.platform == "darwin":
        return _keychain_set(service, account, value)
    return _file_set(service, account, value)


def delete_secret(service: str, account: str) -> bool:
    """Remove the secret for (service, account). True if something was removed.

    Clears BOTH stores regardless of platform — a stale secret must never linger
    in the store the current platform does not read. (Env-var overrides are not
    ours to unset.)
    """
    removed_kc = _keychain_delete(service, account)
    removed_file = _file_delete(service, account)
    return removed_kc or removed_file
