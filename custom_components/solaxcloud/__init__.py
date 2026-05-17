# custom_components/solaxcloud/__init__.py
"""SolaXCloud integration for Home Assistant."""

from __future__ import annotations

from dataclasses import dataclass
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import SolaxCloudApiClient, SolaxCloudAuthError, SolaxCloudError
from .const import (
    CONF_BASE_URL,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    DEFAULT_SCAN_INTERVAL,
)
from .coordinator import SolaxCloudCoordinator

_LOGGER = logging.getLogger(__name__)

# Platforms will be added here as entity types are implemented in later phases.
PLATFORMS: list[str] = ["sensor"]

# Increment VERSION when a breaking change to ConfigEntry.data is made and
# async_migrate_entry must handle the old format.
VERSION = 1


# ---------------------------------------------------------------------------
# Runtime data container
# ---------------------------------------------------------------------------


@dataclass(slots=True, kw_only=True)
class SolaxCloudRuntimeData:
    """Objects kept alive for the lifetime of a loaded config entry."""

    client: SolaxCloudApiClient
    coordinator: SolaxCloudCoordinator


type SolaxCloudConfigEntry = ConfigEntry[SolaxCloudRuntimeData]


# ---------------------------------------------------------------------------
# Entry lifecycle
# ---------------------------------------------------------------------------


async def async_setup_entry(hass: HomeAssistant, entry: SolaxCloudConfigEntry) -> bool:
    """Set up SolaXCloud from a config entry.

    1. Validates credentials via one token fetch.
    2. Creates the :class:`SolaxCloudCoordinator` and performs the first
       data refresh.  If the refresh fails the entry transitions to the
       appropriate error state (reauth or not-ready).
    """
    session = async_get_clientsession(hass)
    client = SolaxCloudApiClient(
        base_url=entry.data[CONF_BASE_URL],
        client_id=entry.data[CONF_CLIENT_ID],
        client_secret=entry.data[CONF_CLIENT_SECRET],
        session=session,
    )

    # Validate credentials before constructing the coordinator.
    try:
        await client.async_ensure_token()
    except SolaxCloudAuthError as exc:
        raise ConfigEntryAuthFailed(
            f"SolaXCloud authentication failed for client_id="
            f"{entry.data[CONF_CLIENT_ID]!r}: {exc}"
        ) from exc
    except SolaxCloudError as exc:
        raise ConfigEntryNotReady(
            f"Could not connect to SolaXCloud at {entry.data[CONF_BASE_URL]!r}: {exc}"
        ) from exc

    coordinator = SolaxCloudCoordinator(hass, entry, client)

    # Fetch plant/device metadata once — stored on the coordinator for the
    # lifetime of the entry; never re-fetched during normal polling.
    try:
        await coordinator.async_fetch_metadata()
    except SolaxCloudAuthError as exc:
        raise ConfigEntryAuthFailed(
            f"SolaXCloud authentication failed while fetching metadata: {exc}"
        ) from exc
    except SolaxCloudError as exc:
        raise ConfigEntryNotReady(
            "Could not fetch SolaXCloud metadata from"
            f" {entry.data[CONF_BASE_URL]!r}: {exc}"
        ) from exc

    # Perform the first realtime data fetch.
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = SolaxCloudRuntimeData(client=client, coordinator=coordinator)

    # Apply updated scan interval whenever the user changes options.
    def _on_options_update(updated_entry: SolaxCloudConfigEntry) -> None:
        new_interval = int(
            updated_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        )
        coordinator.update_scan_interval(new_interval)

    entry.async_on_unload(entry.add_update_listener(_on_options_update))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: SolaxCloudConfigEntry) -> bool:
    """Unload a SolaXCloud config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)  # type: ignore[no-any-return]


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate an old config entry to the current schema version.

    Currently only version 1 exists; this handler is a forward-looking stub
    that logs an error and returns False for unknown future versions that
    cannot be downgraded.
    """
    _LOGGER.debug(
        "Migrating SolaXCloud config entry from version %s to %s",
        entry.version,
        VERSION,
    )

    if entry.version > VERSION:
        # Written by a newer version of the integration — cannot migrate down.
        _LOGGER.error(
            "Cannot migrate SolaXCloud config entry version %s to %s — "
            "please upgrade the integration.",
            entry.version,
            VERSION,
        )
        return False

    # No migrations needed yet (only version 1 exists).
    return True
