# custom_components/solaxcloud/coordinator.py
"""DataUpdateCoordinator for the SolaXCloud integration."""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    BatteryInfo,
    InverterInfo,
    PlantInfo,
    SolaxCloudApiClient,
    SolaxCloudAuthError,
    SolaxCloudData,
    SolaxCloudError,
    SolaxCloudQuotaExhaustedError,
    SolaxCloudRateLimitError,
)
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class SolaxCloudCoordinator(DataUpdateCoordinator[SolaxCloudData]):  # type: ignore[misc]
    """Poll SolaXCloud for realtime telemetry on a configurable schedule.

    **Metadata is fetched once** — plant info, inverter list, and battery list
    are retrieved during :meth:`async_fetch_metadata` (called once from
    :func:`async_setup_entry` before the first coordinator refresh) and stored
    as instance attributes.  They are never re-fetched during the normal poll
    cycle, which keeps the integration well within the API rate limits.

    **Every poll tick** makes exactly two API calls:

    * ``GET /device/realtime_data?deviceType=1&snList=…`` (inverters)
    * ``GET /device/realtime_data?deviceType=2&snList=…`` (batteries)

    If there are no inverters or no batteries, the corresponding call is
    skipped entirely (the client already returns ``[]`` for an empty SN list).
    """

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: SolaxCloudApiClient,
    ) -> None:
        """Initialise the coordinator.

        Args:
            hass: The Home Assistant instance.
            entry: The config entry this coordinator belongs to.
            client: An already-authenticated API client.

        """
        scan_interval: int = int(
            entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        )
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=timedelta(seconds=scan_interval),
        )
        self.client = client

        # Metadata populated by async_fetch_metadata(); never mutated afterwards.
        self.plants: list[PlantInfo] = []
        self.inverters: list[InverterInfo] = []
        self.batteries: list[BatteryInfo] = []

        # Pre-computed ID/SN lists derived from metadata; used on every tick.
        self._plant_ids: list[str] = []
        self._inverter_sns: list[str] = []
        self._battery_sns: list[str] = []

    # ------------------------------------------------------------------
    # Runtime interval update (called when options change)
    # ------------------------------------------------------------------

    def update_scan_interval(self, seconds: int) -> None:
        """Apply a new polling interval to the running coordinator.

        Called from the options-update listener in ``async_setup_entry``
        whenever the user changes the query interval in the Options dialog.
        The change takes effect on the *next* scheduled tick.

        Args:
            seconds: New interval in whole seconds.  Values below
                ``MIN_SCAN_INTERVAL`` are silently clamped.

        """
        from .const import MIN_SCAN_INTERVAL

        clamped = max(int(seconds), MIN_SCAN_INTERVAL)
        current: timedelta | None = self.update_interval  # type: ignore[has-type]
        if current == timedelta(seconds=clamped):
            return
        self.update_interval = timedelta(seconds=clamped)
        _LOGGER.debug(
            "SolaXCloud: scan interval updated to %d s (coordinator=%s)",
            clamped,
            self.name,
        )

    # ------------------------------------------------------------------
    # One-time metadata fetch (called from async_setup_entry)
    # ------------------------------------------------------------------

    async def async_fetch_metadata(self) -> None:
        """Fetch plant and device metadata from SolaXCloud.

        Called **once** during integration setup before the first coordinator
        refresh.  The results are stored on the instance and reused for the
        lifetime of the config entry — no further metadata calls are made
        during normal operation.

        Raises:
            SolaxCloudAuthError: Credentials are invalid.
            SolaxCloudApiError: API or connectivity failure.

        """
        _LOGGER.debug("SolaXCloud: fetching one-time metadata")
        self.plants = await self.client.async_get_plants()
        self.inverters = await self.client.async_get_inverters()
        self.batteries = await self.client.async_get_batteries()

        self._plant_ids = [p.plant_id for p in self.plants]
        self._inverter_sns = [inv.device_sn for inv in self.inverters]
        self._battery_sns = [bat.device_sn for bat in self.batteries]

        _LOGGER.debug(
            "SolaXCloud metadata: %d plant(s), %d inverter(s), %d battery(ies)",
            len(self.plants),
            len(self.inverters),
            len(self.batteries),
        )

    # ------------------------------------------------------------------
    # Recurring realtime poll (called by DataUpdateCoordinator every tick)
    # ------------------------------------------------------------------

    async def _async_update_data(self) -> SolaxCloudData:
        """Fetch realtime telemetry for all known devices and plants.

        Makes at most three API calls per tick:

        * ``GET /plant/realtime_data?plantId=…`` (one per plant)
        * ``GET /device/realtime_data?deviceType=1&snList=…`` (inverters)
        * ``GET /device/realtime_data?deviceType=2&snList=…`` (batteries)

        Calls are skipped when the corresponding list is empty.

        Returns:
            A :class:`SolaxCloudData` snapshot combining the cached metadata
            with freshly-fetched realtime readings.

        Raises:
            ConfigEntryAuthFailed: Token can no longer be refreshed — triggers
                the HA reauth flow.
            UpdateFailed: Any transient API or connectivity failure, including
                rate-limit responses.  HA retries on the next tick and keeps
                showing the last known values in the UI.

        """
        try:
            plant_realtime = await self.client.async_get_plant_realtime(self._plant_ids)
            inverter_realtime = await self.client.async_get_inverter_realtime(
                self._inverter_sns
            )
            battery_realtime = await self.client.async_get_battery_realtime(
                self._battery_sns
            )
        except SolaxCloudAuthError as exc:
            from homeassistant.exceptions import ConfigEntryAuthFailed

            raise ConfigEntryAuthFailed(
                f"SolaXCloud authentication lost during data update: {exc}"
            ) from exc
        except SolaxCloudRateLimitError as exc:
            _LOGGER.warning(
                "SolaXCloud rate limit hit — keeping previous data until next poll. "
                "Consider increasing the query interval in the integration options. "
                "(%s)",
                exc,
            )
            raise UpdateFailed(str(exc)) from exc
        except SolaxCloudQuotaExhaustedError as exc:
            _LOGGER.error(
                "SolaXCloud API call quota exhausted. "
                "Data will not update until the quota is renewed in the "
                "SolaX Developer Portal. (%s)",
                exc,
            )
            raise UpdateFailed(str(exc)) from exc
        except SolaxCloudError as exc:
            raise UpdateFailed(
                f"Error communicating with SolaXCloud API: {exc}"
            ) from exc

        return SolaxCloudData(
            plants=self.plants,
            inverters=self.inverters,
            batteries=self.batteries,
            inverter_realtime=inverter_realtime,
            battery_realtime=battery_realtime,
            plant_realtime=plant_realtime,
        )
