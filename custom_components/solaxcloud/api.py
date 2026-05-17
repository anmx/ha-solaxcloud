# custom_components/solaxcloud/api.py
"""Async API client for the SolaXCloud OpenAPI."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
import logging
from typing import Any

import aiohttp

from .const import (
    API_ERROR_BAD_CREDENTIALS,
    API_ERROR_NO_PERMISSION,
    API_ERROR_NOT_AUTHENTICATED,
    API_ERROR_QUOTA_EXHAUSTED,
    API_ERROR_RATE_LIMIT,
    API_ERROR_TOKEN_INVALID,
    API_PATH_DEVICE_INFO,
    API_PATH_PLANT_INFO,
    API_PATH_PLANT_REALTIME,
    API_PATH_REALTIME_DATA,
    API_PATH_TOKEN,
    API_SUCCESS_CODE,
    BUSINESS_TYPE,
    DEVICE_TYPE_BATTERY,
    DEVICE_TYPE_INVERTER,
    OAUTH2_GRANT_TYPE,
    TOKEN_EXPIRY_BUFFER,
    TOKEN_FIELD_ACCESS_TOKEN,
    TOKEN_FIELD_CODE,
    TOKEN_FIELD_EXPIRES_IN,
    TOKEN_FIELD_RESULT,
)

_LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Typed response models
# ---------------------------------------------------------------------------


@dataclass(slots=True, kw_only=True, frozen=True)
class TokenResponse:
    """Parsed OAuth2 token response from SolaXCloud."""

    access_token: str
    expires_in: int


@dataclass(slots=True, kw_only=True, frozen=True)
class PlantInfo:
    """Information about a single SolaXCloud plant (site)."""

    plant_id: str
    plant_name: str
    login_name: str
    battery_capacity: float | None
    pv_capacity: float | None
    create_time: str
    plant_time_zone: str
    plant_state: int
    plant_address: str
    longitude: float | None
    latitude: float | None
    electricity_price_unit: str

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> PlantInfo:
        """Construct from a raw API record dict."""
        return cls(
            plant_id=data["plantId"],
            plant_name=data["plantName"],
            login_name=data["loginName"],
            battery_capacity=data.get("batteryCapacity"),
            pv_capacity=data.get("pvCapacity"),
            create_time=data.get("createTime", ""),
            plant_time_zone=data.get("plantTimeZone", ""),
            plant_state=int(data.get("plantState", 0)),
            plant_address=data.get("plantAddress", ""),
            longitude=data.get("longitude"),
            latitude=data.get("latitude"),
            electricity_price_unit=data.get("electricityPriceUnit", ""),
        )


@dataclass(slots=True, kw_only=True, frozen=True)
class InverterInfo:
    """Information about a single inverter device."""

    device_model: int
    arm_version: str
    dsp_version: str
    rated_power: float | None
    register_no: str
    device_sn: str
    plant_id: str
    online_status: int
    flag: int

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> InverterInfo:
        """Construct from a raw API record dict."""
        return cls(
            device_model=int(data.get("deviceModel", 0)),
            arm_version=data.get("armVersion", ""),
            dsp_version=data.get("dspVersion", ""),
            rated_power=data.get("ratedPower"),
            register_no=data.get("registerNo", ""),
            device_sn=data.get("deviceSn", ""),
            plant_id=data.get("plantId", ""),
            online_status=int(data.get("onlineStatus", 0)),
            flag=int(data.get("flag", 0)),
        )


@dataclass(slots=True, kw_only=True, frozen=True)
class BatteryInfo:
    """Information about a single battery (SOC) device."""

    device_model: int
    hardware_version: str | None
    register_no: str
    device_sn: str
    plant_id: str
    software_version: str
    rated_capacity: float | None
    online_status: int

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> BatteryInfo:
        """Construct from a raw API record dict."""
        return cls(
            device_model=int(data.get("deviceModel", 0)),
            hardware_version=data.get("hardwareVersion"),
            register_no=data.get("registerNo", ""),
            device_sn=data.get("deviceSn", ""),
            plant_id=data.get("plantId", ""),
            software_version=data.get("softwareVersion", ""),
            rated_capacity=data.get("ratedCapacity"),
            online_status=int(data.get("onlineStatus", 0)),
        )


@dataclass(slots=True, kw_only=True, frozen=True)
class MpptData:
    """Per-MPPT string voltages, currents, and power from the inverter."""

    mppt1_voltage: float | None
    mppt1_current: float | None
    mppt1_power: float | None
    mppt2_voltage: float | None
    mppt2_current: float | None
    mppt2_power: float | None

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> MpptData:
        """Construct from the ``mpptMap`` dict inside a realtime record."""
        return cls(
            mppt1_voltage=data.get("MPPT1Voltage"),
            mppt1_current=data.get("MPPT1Current"),
            mppt1_power=data.get("MPPT1Power"),
            mppt2_voltage=data.get("MPPT2Voltage"),
            mppt2_current=data.get("MPPT2Current"),
            mppt2_power=data.get("MPPT2Power"),
        )


@dataclass(slots=True, kw_only=True, frozen=True)
class InverterRealtimeData:
    """Real-time telemetry for a single inverter."""

    device_sn: str
    register_no: str
    device_status: int
    data_time: str
    plant_local_time: str

    # Grid / metering
    grid_power: float | None
    today_import_energy: float | None
    total_import_energy: float | None
    today_export_energy: float | None
    total_export_energy: float | None

    # AC phase measurements
    ac_current1: float | None
    ac_voltage1: float | None
    ac_current2: float | None
    ac_voltage2: float | None
    ac_current3: float | None
    ac_voltage3: float | None
    ac_power1: float | None
    ac_power2: float | None
    ac_power3: float | None
    ac_frequency1: float | None
    ac_frequency2: float | None
    ac_frequency3: float | None
    grid_frequency: float | None
    total_power_factor: float | None

    # Inverter health / production
    inverter_temperature: float | None
    daily_ac_output: float | None
    total_ac_output: float | None
    daily_yield: float | None
    total_yield: float | None

    # MPPT strings
    mppt: MpptData

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> InverterRealtimeData:
        """Construct from a raw realtime API record dict."""
        return cls(
            device_sn=data.get("deviceSn", ""),
            register_no=data.get("registerNo", ""),
            device_status=int(data.get("deviceStatus", 0)),
            data_time=data.get("dataTime", ""),
            plant_local_time=data.get("plantLocalTime", ""),
            grid_power=data.get("gridPower"),
            today_import_energy=data.get("todayImportEnergy"),
            total_import_energy=data.get("totalImportEnergy"),
            today_export_energy=data.get("todayExportEnergy"),
            total_export_energy=data.get("totalExportEnergy"),
            ac_current1=data.get("acCurrent1"),
            ac_voltage1=data.get("acVoltage1"),
            ac_current2=data.get("acCurrent2"),
            ac_voltage2=data.get("acVoltage2"),
            ac_current3=data.get("acCurrent3"),
            ac_voltage3=data.get("acVoltage3"),
            ac_power1=data.get("acPower1"),
            ac_power2=data.get("acPower2"),
            ac_power3=data.get("acPower3"),
            ac_frequency1=data.get("acFrequency1"),
            ac_frequency2=data.get("acFrequency2"),
            ac_frequency3=data.get("acFrequency3"),
            grid_frequency=data.get("gridFrequency"),
            total_power_factor=data.get("totalPowerFactor"),
            inverter_temperature=data.get("inverterTemperature"),
            daily_ac_output=data.get("dailyACOutput"),
            total_ac_output=data.get("totalACOutput"),
            daily_yield=data.get("dailyYield"),
            total_yield=data.get("totalYield"),
            mppt=MpptData.from_api(data.get("mpptMap") or {}),
        )


@dataclass(slots=True, kw_only=True, frozen=True)
class BatteryRealtimeData:
    """Real-time telemetry for a single battery (SOC) device."""

    device_sn: str
    register_no: str
    device_status: int
    data_time: str
    plant_local_time: str

    battery_soc: int | None
    battery_soh: int | None
    charge_discharge_power: float | None
    battery_voltage: float | None
    battery_current: float | None
    battery_temperature: float | None
    battery_cycle_times: int | None
    total_device_discharge: float | None
    total_device_charge: float | None
    battery_remainings: float | None

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> BatteryRealtimeData:
        """Construct from a raw realtime API record dict."""
        return cls(
            device_sn=data.get("deviceSn", ""),
            register_no=data.get("registerNo", ""),
            device_status=int(data.get("deviceStatus", 0)),
            data_time=data.get("dataTime", ""),
            plant_local_time=data.get("plantLocalTime", ""),
            battery_soc=data.get("batterySOC"),
            battery_soh=data.get("batterySOH"),
            charge_discharge_power=data.get("chargeDischargePower"),
            battery_voltage=data.get("batteryVoltage"),
            battery_current=data.get("batteryCurrent"),
            battery_temperature=data.get("batteryTemperature"),
            battery_cycle_times=data.get("batteryCycleTimes"),
            total_device_discharge=data.get("totalDeviceDischarge"),
            total_device_charge=data.get("totalDeviceCharge"),
            battery_remainings=data.get("batteryRemainings"),
        )


@dataclass(slots=True, kw_only=True, frozen=True)
class PlantRealtimeData:
    """Real-time aggregated telemetry for a single SolaXCloud plant (site)."""

    plant_id: str
    plant_local_time: str

    # Production
    daily_yield: float | None
    total_yield: float | None

    # Battery
    daily_charged: float | None
    total_charged: float | None
    daily_discharged: float | None
    total_discharged: float | None

    # Grid exchange
    daily_imported: float | None
    total_imported: float | None
    daily_exported: float | None
    total_exported: float | None

    # Earnings
    daily_earnings: float | None
    total_earnings: float | None

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> PlantRealtimeData:
        """Construct from a raw plant realtime API result dict."""
        return cls(
            plant_id=data.get("plantId", ""),
            plant_local_time=data.get("plantLocalTime", ""),
            daily_yield=data.get("dailyYield"),
            total_yield=data.get("totalYield"),
            daily_charged=data.get("dailyCharged"),
            total_charged=data.get("totalCharged"),
            daily_discharged=data.get("dailyDischarged"),
            total_discharged=data.get("totalDischarged"),
            daily_imported=data.get("dailyImported"),
            total_imported=data.get("totalImported"),
            daily_exported=data.get("dailyExported"),
            total_exported=data.get("totalExported"),
            daily_earnings=data.get("dailyEarnings"),
            total_earnings=data.get("totalEarnings"),
        )


@dataclass(slots=True, kw_only=True, frozen=True)
class SolaxCloudData:
    """Aggregated snapshot fetched during a single coordinator update cycle."""

    plants: list[PlantInfo]
    inverters: list[InverterInfo]
    batteries: list[BatteryInfo]
    inverter_realtime: list[InverterRealtimeData]
    battery_realtime: list[BatteryRealtimeData]
    plant_realtime: list[PlantRealtimeData]


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------


class SolaxCloudError(Exception):
    """Base error for all SolaXCloud API failures."""


class SolaxCloudAuthError(SolaxCloudError):
    """Raised when credentials are invalid or the token cannot be issued.

    Covers HTTP 401 responses as well as application-level auth codes:
    - 10400: Request not authenticated
    - 10401: Username or password incorrect
    - 10402: access_token authentication failed (token invalid/expired)
    - 10403: Interface has no access rights
    """


class SolaxCloudApiError(SolaxCloudError):
    """Raised on non-auth API or connectivity failures."""


class SolaxCloudRateLimitError(SolaxCloudApiError):
    """Raised when the API returns error code 10406 (call rate limit reached).

    The caller should treat this as a transient failure and retry after the
    next polling interval rather than marking the integration permanently broken.
    """


class SolaxCloudQuotaExhaustedError(SolaxCloudApiError):
    """Raised when error code 10405 is returned (API call quota fully consumed).

    Unlike a rate-limit this does not resolve on its own within the current
    billing period.  HA will continue retrying, but the user needs to act
    (e.g. renew their API quota in the SolaX Developer Portal).
    """


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


# Auth-level application codes that map to SolaxCloudAuthError.
_AUTH_CODES: frozenset[int] = frozenset(
    {
        API_ERROR_NOT_AUTHENTICATED,  # 10400
        API_ERROR_BAD_CREDENTIALS,  # 10401
        API_ERROR_TOKEN_INVALID,  # 10402
        API_ERROR_NO_PERMISSION,  # 10403
    }
)


def _raise_for_app_code(code: object, path: str) -> None:
    """Raise the appropriate exception for a non-success SolaXCloud app code.

    Args:
        code: The application-level code from the JSON response body.
        path: The request path, used only for the error message.

    Raises:
        SolaxCloudAuthError: code is an auth failure (10400-10403).
        SolaxCloudRateLimitError: code is ``API_ERROR_RATE_LIMIT`` (10406).
        SolaxCloudQuotaExhaustedError: code is ``API_ERROR_QUOTA_EXHAUSTED`` (10405).
        SolaxCloudApiError: Any other non-success code.

    """
    if code in _AUTH_CODES:
        raise SolaxCloudAuthError(
            f"SolaXCloud authentication error on {path} (code {code}). "
            "The access token may be invalid or expired — "
            "the integration will attempt to re-authenticate."
        )
    if code == API_ERROR_RATE_LIMIT:
        raise SolaxCloudRateLimitError(
            f"SolaXCloud API call rate limit reached on {path} (code {code}). "
            "Consider increasing the query interval in the integration options."
        )
    if code == API_ERROR_QUOTA_EXHAUSTED:
        raise SolaxCloudQuotaExhaustedError(
            f"SolaXCloud API call quota exhausted on {path} (code {code}). "
            "Please check your quota in the SolaX Developer Portal."
        )
    raise SolaxCloudApiError(f"SolaXCloud returned application code {code} on {path}")


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


@dataclass(slots=True, kw_only=True)
class SolaxCloudApiClient:
    """Thin async wrapper around the SolaXCloud OpenAPI.

    The client uses the OAuth2 ``client_credentials`` grant to obtain an
    access token.  It caches the token internally and proactively refreshes
    it ``TOKEN_EXPIRY_BUFFER`` seconds before it expires so callers never
    need to think about token lifecycle.

    Args:
        base_url: Root URL of the SolaXCloud OpenAPI, e.g.
            ``https://openapi-eu.solaxcloud.com``.  No trailing slash.
        client_id: OAuth2 client identifier.
        client_secret: OAuth2 client secret.  Never logged.
        session: An ``aiohttp.ClientSession`` managed by Home Assistant.

    """

    base_url: str
    client_id: str
    client_secret: str
    session: aiohttp.ClientSession

    # Internal token cache — not part of the public interface.
    _access_token: str = field(default="", init=False, repr=False)
    _token_expires_at: datetime = field(
        default_factory=lambda: datetime.min.replace(tzinfo=UTC),
        init=False,
        repr=False,
    )

    # ------------------------------------------------------------------
    # Token management
    # ------------------------------------------------------------------

    async def async_get_token(self) -> TokenResponse:
        """Fetch a new access token from the SolaXCloud token endpoint.

        This method always performs a network request; use
        :meth:`async_ensure_token` to benefit from caching.

        Returns:
            A :class:`TokenResponse` with the new token and its TTL.

        Raises:
            SolaxCloudAuthError: The server rejected the credentials or
                returned a non-zero application error code.
            SolaxCloudApiError: Any other connectivity or parsing failure.

        """
        url = f"{self.base_url}{API_PATH_TOKEN}"
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": OAUTH2_GRANT_TYPE,
        }

        # The SolaX token endpoint requires the currently-held access token
        # in the Authorization header on every call — even when requesting a
        # replacement.  On the very first call (no cached token yet) the
        # header is omitted; the API accepts that for initial issuance.
        headers: dict[str, str] = {"content-type": "application/x-www-form-urlencoded"}
        if self._access_token:
            headers["authorization"] = f"Bearer {self._access_token}"

        _LOGGER.debug(
            "Requesting new SolaXCloud access token (client_id=%s)", self.client_id
        )

        try:
            async with self.session.post(
                url,
                data=data,
                headers=headers,
            ) as response:
                if response.status == 401:
                    raise SolaxCloudAuthError(
                        "HTTP 401 from token endpoint — check client credentials"
                        f" (client_id={self.client_id})"
                    )
                if response.status >= 400:
                    raise SolaxCloudApiError(
                        f"Token endpoint returned HTTP {response.status}"
                    )

                payload: dict[str, Any] = await response.json(content_type=None)

        except SolaxCloudError:
            raise
        except aiohttp.ClientError as exc:
            raise SolaxCloudApiError(
                f"Connection error reaching token endpoint: {exc}"
            ) from exc

        # SolaXCloud uses an application-level error code in the JSON body.
        code = payload.get(TOKEN_FIELD_CODE)
        if code != 0:
            # code values other than 0 indicate auth/business failures.
            # Do NOT include the raw payload here — it may contain secrets.
            _LOGGER.debug(
                "SolaXCloud token request failed (client_id=%s, code=%s)",
                self.client_id,
                code,
            )
            raise SolaxCloudAuthError(
                f"SolaXCloud returned error code {code} for client_id={self.client_id}"
            )

        result: dict[str, Any] = payload.get(TOKEN_FIELD_RESULT, {})
        access_token: str = result.get(TOKEN_FIELD_ACCESS_TOKEN, "")
        expires_in: int = result.get(TOKEN_FIELD_EXPIRES_IN, 0)

        if not access_token:
            raise SolaxCloudApiError(
                "Token endpoint returned an empty access_token"
                " — unexpected response shape."
            )

        return TokenResponse(access_token=access_token, expires_in=expires_in)

    async def async_ensure_token(self) -> str:
        """Return a valid access token, refreshing it if necessary.

        Refreshes proactively ``TOKEN_EXPIRY_BUFFER`` seconds before the
        cached token expires so in-flight requests are never rejected.

        If the token endpoint rejects the current token (``SolaxCloudAuthError``
        raised by :meth:`async_get_token`), the cached token is cleared and one
        retry is attempted without a Bearer header, which allows the API to
        issue a completely fresh token.  If the retry also fails the error
        is re-raised so the coordinator can trigger a reauth flow.

        Returns:
            The current valid access token string.

        Raises:
            SolaxCloudAuthError: Credentials are definitively invalid.
            SolaxCloudApiError: The token could not be fetched.

        """
        now = datetime.now(UTC)
        if self._access_token and now < self._token_expires_at - TOKEN_EXPIRY_BUFFER:
            return self._access_token

        try:
            token_response = await self.async_get_token()
        except SolaxCloudAuthError:
            if self._access_token:
                # The cached token was rejected by the token endpoint.
                # Clear it and try once more as a fresh (no-header) request.
                _LOGGER.debug(
                    "SolaXCloud: cached token rejected by token endpoint; "
                    "retrying as a fresh token request (client_id=%s)",
                    self.client_id,
                )
                self._access_token = ""
                self._token_expires_at = datetime.min.replace(tzinfo=UTC)
                token_response = await self.async_get_token()
            else:
                raise

        self._access_token = token_response.access_token
        now_truncated = datetime.now(UTC).replace(microsecond=0)
        # Advance by expires_in seconds; buffer applied at comparison time.
        self._token_expires_at = now_truncated + timedelta(
            seconds=token_response.expires_in
        )
        _LOGGER.debug(
            "SolaXCloud token refreshed; expires at %s (client_id=%s)",
            self._token_expires_at.isoformat(),
            self.client_id,
        )
        return self._access_token

    # ------------------------------------------------------------------
    # Private GET helper
    # ------------------------------------------------------------------

    async def _async_get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        """Execute an authenticated GET request and return the parsed body.

        Handles token injection, HTTP-level errors, and the application-level
        ``code`` field that SolaXCloud wraps every response in.

        Args:
            path: URL path relative to ``base_url``.
            params: Query-string parameters (excluding auth).

        Returns:
            The ``result`` dict from the response body.

        Raises:
            SolaxCloudAuthError: HTTP 401 received.
            SolaxCloudApiError: Any other HTTP or connectivity failure, or a
                non-success application code.

        """
        token = await self.async_ensure_token()
        url = f"{self.base_url}{path}"

        try:
            async with self.session.get(
                url,
                params=params,
                headers={"authorization": f"Bearer {token}"},
            ) as response:
                if response.status == 401:
                    raise SolaxCloudAuthError(
                        f"HTTP 401 on {path} — token may have been revoked"
                    )
                if response.status >= 400:
                    raise SolaxCloudApiError(f"HTTP {response.status} on {path}")
                payload: dict[str, Any] = await response.json(content_type=None)

        except SolaxCloudError:
            raise
        except aiohttp.ClientError as exc:
            raise SolaxCloudApiError(f"Connection error on {path}: {exc}") from exc

        code = payload.get(TOKEN_FIELD_CODE)
        if code != API_SUCCESS_CODE:
            _raise_for_app_code(code, path)

        result: dict[str, Any] = payload.get(TOKEN_FIELD_RESULT, {})
        return result

    # ------------------------------------------------------------------
    # Data access methods
    # ------------------------------------------------------------------

    async def async_get_plants(self) -> list[PlantInfo]:
        """Fetch all plants (sites) visible to this API credential.

        Iterates all pages automatically.

        Returns:
            A list of :class:`PlantInfo` objects, one per plant record.

        Raises:
            SolaxCloudAuthError: Authentication failed mid-request.
            SolaxCloudApiError: API or connectivity failure.

        """
        records: list[dict[str, Any]] = []
        current_page = 1

        while True:
            result = await self._async_get(
                API_PATH_PLANT_INFO,
                params={
                    "businessType": BUSINESS_TYPE,
                    "current": current_page,
                },
            )
            page_records: list[dict[str, Any]] = result.get("records", [])
            records.extend(page_records)

            total_pages: int = int(result.get("pages", 1))
            if current_page >= total_pages:
                break
            current_page += 1

        _LOGGER.debug(
            "SolaXCloud: fetched %d plant(s) across %d page(s)",
            len(records),
            current_page,
        )
        return [PlantInfo.from_api(r) for r in records]

    async def async_get_inverters(self) -> list[InverterInfo]:
        """Fetch all inverter devices visible to this API credential.

        Iterates all pages automatically.

        Returns:
            A list of :class:`InverterInfo` objects.

        Raises:
            SolaxCloudAuthError: Authentication failed mid-request.
            SolaxCloudApiError: API or connectivity failure.

        """
        records: list[dict[str, Any]] = []
        current_page = 1

        while True:
            result = await self._async_get(
                API_PATH_DEVICE_INFO,
                params={
                    "deviceType": DEVICE_TYPE_INVERTER,
                    "businessType": BUSINESS_TYPE,
                    "current": current_page,
                },
            )
            page_records: list[dict[str, Any]] = result.get("records", [])
            records.extend(page_records)

            total_pages = int(result.get("pages", 1))
            if current_page >= total_pages:
                break
            current_page += 1

        _LOGGER.debug(
            "SolaXCloud: fetched %d inverter(s) across %d page(s)",
            len(records),
            current_page,
        )
        return [InverterInfo.from_api(r) for r in records]

    async def async_get_batteries(self) -> list[BatteryInfo]:
        """Fetch all battery (SOC) devices visible to this API credential.

        Iterates all pages automatically.

        Returns:
            A list of :class:`BatteryInfo` objects.

        Raises:
            SolaxCloudAuthError: Authentication failed mid-request.
            SolaxCloudApiError: API or connectivity failure.

        """
        records: list[dict[str, Any]] = []
        current_page = 1

        while True:
            result = await self._async_get(
                API_PATH_DEVICE_INFO,
                params={
                    "deviceType": DEVICE_TYPE_BATTERY,
                    "businessType": BUSINESS_TYPE,
                    "current": current_page,
                },
            )
            page_records: list[dict[str, Any]] = result.get("records", [])
            records.extend(page_records)

            total_pages = int(result.get("pages", 1))
            if current_page >= total_pages:
                break
            current_page += 1

        _LOGGER.debug(
            "SolaXCloud: fetched %d battery(ies) across %d page(s)",
            len(records),
            current_page,
        )
        return [BatteryInfo.from_api(r) for r in records]

    async def _async_get_list(
        self, path: str, params: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Execute an authenticated GET request whose ``result`` is a list.

        Used by the realtime-data endpoint, which returns a JSON array under
        ``result`` instead of the paged dict used by the info endpoints.

        Args:
            path: URL path relative to ``base_url``.
            params: Query-string parameters (excluding auth).

        Returns:
            The list of record dicts from the ``result`` field.

        Raises:
            SolaxCloudAuthError: HTTP 401 received.
            SolaxCloudApiError: Any other HTTP, connectivity, or app-code failure.

        """
        token = await self.async_ensure_token()
        url = f"{self.base_url}{path}"

        try:
            async with self.session.get(
                url,
                params=params,
                headers={"authorization": f"Bearer {token}"},
            ) as response:
                if response.status == 401:
                    raise SolaxCloudAuthError(
                        f"HTTP 401 on {path} — token may have been revoked"
                    )
                if response.status >= 400:
                    raise SolaxCloudApiError(f"HTTP {response.status} on {path}")
                payload: dict[str, Any] = await response.json(content_type=None)

        except SolaxCloudError:
            raise
        except aiohttp.ClientError as exc:
            raise SolaxCloudApiError(f"Connection error on {path}: {exc}") from exc

        code = payload.get(TOKEN_FIELD_CODE)
        if code != API_SUCCESS_CODE:
            _raise_for_app_code(code, path)

        result: list[dict[str, Any]] = payload.get(TOKEN_FIELD_RESULT, [])
        return result

    async def async_get_inverter_realtime(
        self, serial_numbers: list[str]
    ) -> list[InverterRealtimeData]:
        """Fetch real-time telemetry for the given inverter serial numbers.

        Args:
            serial_numbers: List of inverter ``deviceSn`` values to query.
                The API accepts a comma-separated ``snList`` parameter.

        Returns:
            One :class:`InverterRealtimeData` per serial number (order
            matches the API response, which may differ from the input).
            Returns an empty list when ``serial_numbers`` is empty.

        Raises:
            SolaxCloudAuthError: Authentication failed.
            SolaxCloudApiError: API or connectivity failure.

        """
        if not serial_numbers:
            return []

        records = await self._async_get_list(
            API_PATH_REALTIME_DATA,
            params={
                "snList": ",".join(serial_numbers),
                "businessType": BUSINESS_TYPE,
                "deviceType": DEVICE_TYPE_INVERTER,
            },
        )
        _LOGGER.debug(
            "SolaXCloud: fetched realtime data for %d inverter(s)", len(records)
        )
        return [InverterRealtimeData.from_api(r) for r in records]

    async def async_get_battery_realtime(
        self, serial_numbers: list[str]
    ) -> list[BatteryRealtimeData]:
        """Fetch real-time telemetry for the given battery serial numbers.

        Args:
            serial_numbers: List of battery ``deviceSn`` values to query.
                The API accepts a comma-separated ``snList`` parameter.

        Returns:
            One :class:`BatteryRealtimeData` per serial number (order
            matches the API response).  Returns an empty list when
            ``serial_numbers`` is empty.

        Raises:
            SolaxCloudAuthError: Authentication failed.
            SolaxCloudApiError: API or connectivity failure.

        """
        if not serial_numbers:
            return []

        records = await self._async_get_list(
            API_PATH_REALTIME_DATA,
            params={
                "snList": ",".join(serial_numbers),
                "businessType": BUSINESS_TYPE,
                "deviceType": DEVICE_TYPE_BATTERY,
            },
        )
        _LOGGER.debug(
            "SolaXCloud: fetched realtime data for %d battery(ies)", len(records)
        )
        return [BatteryRealtimeData.from_api(r) for r in records]

    async def async_get_plant_realtime(
        self, plant_ids: list[str]
    ) -> list[PlantRealtimeData]:
        """Fetch real-time aggregated telemetry for the given plant IDs.

        One GET request is issued per plant because the endpoint only accepts
        a single ``plantId`` at a time.

        Args:
            plant_ids: List of plant identifiers from :attr:`PlantInfo.plant_id`.

        Returns:
            One :class:`PlantRealtimeData` per plant (same order as input).
            Returns an empty list when ``plant_ids`` is empty.

        Raises:
            SolaxCloudAuthError: Authentication failed.
            SolaxCloudApiError: API or connectivity failure.

        """
        if not plant_ids:
            return []

        results: list[PlantRealtimeData] = []
        for plant_id in plant_ids:
            result = await self._async_get(
                API_PATH_PLANT_REALTIME,
                params={
                    "plantId": plant_id,
                    "businessType": BUSINESS_TYPE,
                },
            )
            results.append(PlantRealtimeData.from_api(result))

        _LOGGER.debug(
            "SolaXCloud: fetched plant realtime data for %d plant(s)", len(results)
        )
        return results
