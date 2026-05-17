# custom_components/solaxcloud/config_flow.py
"""Config flow and options flow for the SolaXCloud integration."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
import voluptuous as vol

from .api import SolaxCloudApiClient, SolaxCloudAuthError, SolaxCloudError
from .const import (
    CONF_BASE_URL,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    DEFAULT_BASE_URL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MIN_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared schema helpers
# ---------------------------------------------------------------------------


def _build_credentials_schema(
    base_url: str = DEFAULT_BASE_URL,
    client_id: str = "",
    client_secret: str = "",
) -> vol.Schema:
    """Return a credentials schema pre-filled with the supplied defaults."""
    return vol.Schema(
        {
            vol.Required(CONF_BASE_URL, default=base_url): TextSelector(
                TextSelectorConfig(type=TextSelectorType.URL)
            ),
            vol.Required(CONF_CLIENT_ID, default=client_id): TextSelector(
                TextSelectorConfig(type=TextSelectorType.TEXT, autocomplete="off")
            ),
            vol.Required(CONF_CLIENT_SECRET, default=client_secret): TextSelector(
                TextSelectorConfig(type=TextSelectorType.PASSWORD, autocomplete="off")
            ),
        }
    )


async def _async_validate_credentials(
    hass: HomeAssistant,
    base_url: str,
    client_id: str,
    client_secret: str,
) -> None:
    """Validate OAuth2 credentials by attempting a token fetch.

    Args:
        hass: The Home Assistant instance.
        base_url: Root API URL (no trailing slash).
        client_id: OAuth2 client identifier.
        client_secret: OAuth2 client secret.

    Raises:
        SolaxCloudAuthError: Credentials are invalid.
        SolaxCloudError: Any other API-level failure.
        aiohttp.ClientError: Network-level failure.

    """
    session = async_get_clientsession(hass)
    client = SolaxCloudApiClient(
        base_url=base_url.rstrip("/"),
        client_id=client_id,
        client_secret=client_secret,
        session=session,
    )
    await client.async_get_token()


def _map_error(exc: Exception) -> str:
    """Map an exception to a strings.json error key."""
    if isinstance(exc, SolaxCloudAuthError):
        return "invalid_auth"
    if isinstance(exc, SolaxCloudError | aiohttp.ClientError):
        return "cannot_connect"
    return "unknown"


# ---------------------------------------------------------------------------
# Config flow
# ---------------------------------------------------------------------------


class SolaxCloudConfigFlow(ConfigFlow, domain=DOMAIN):  # type: ignore[call-arg,misc]
    """Handle the initial setup dialog for SolaXCloud."""

    VERSION = 1

    # Stored during multi-step flows (reauth, reconfigure)
    _reauth_entry: ConfigEntry | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the first (and only) step of the initial setup flow."""
        errors: dict[str, str] = {}

        if user_input is not None:
            base_url: str = user_input[CONF_BASE_URL].rstrip("/")
            client_id: str = user_input[CONF_CLIENT_ID]
            client_secret: str = user_input[CONF_CLIENT_SECRET]

            try:
                await _async_validate_credentials(
                    self.hass, base_url, client_id, client_secret
                )
            except Exception as exc:
                _LOGGER.debug(
                    "SolaXCloud config flow validation failed: %s", exc, exc_info=True
                )
                errors["base"] = _map_error(exc)
            else:
                await self.async_set_unique_id(client_id)
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=f"SolaXCloud ({client_id})",
                    data={
                        CONF_BASE_URL: base_url,
                        CONF_CLIENT_ID: client_id,
                        CONF_CLIENT_SECRET: client_secret,
                    },
                )

        prefill_base_url = (
            user_input.get(CONF_BASE_URL, DEFAULT_BASE_URL)
            if user_input
            else DEFAULT_BASE_URL
        )
        prefill_client_id = user_input.get(CONF_CLIENT_ID, "") if user_input else ""
        return self.async_show_form(
            step_id="user",
            data_schema=_build_credentials_schema(
                base_url=prefill_base_url,
                client_id=prefill_client_id,
            ),
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Reauth flow
    # ------------------------------------------------------------------

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        """Start the reauth flow when credentials have become invalid."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle updated credentials during a reauth flow."""
        assert self._reauth_entry is not None
        errors: dict[str, str] = {}

        existing_base_url: str = self._reauth_entry.data[CONF_BASE_URL]
        existing_client_id: str = self._reauth_entry.data[CONF_CLIENT_ID]

        if user_input is not None:
            client_secret: str = user_input[CONF_CLIENT_SECRET]
            try:
                await _async_validate_credentials(
                    self.hass,
                    existing_base_url,
                    existing_client_id,
                    client_secret,
                )
            except Exception as exc:
                _LOGGER.debug(
                    "SolaXCloud reauth validation failed: %s", exc, exc_info=True
                )
                errors["base"] = _map_error(exc)
            else:
                return self.async_update_reload_and_abort(
                    self._reauth_entry,
                    data_updates={CONF_CLIENT_SECRET: client_secret},
                )

        # Only ask for the secret — base URL and client ID are fixed.
        schema = vol.Schema(
            {
                vol.Required(CONF_CLIENT_SECRET): TextSelector(
                    TextSelectorConfig(
                        type=TextSelectorType.PASSWORD, autocomplete="off"
                    )
                ),
            }
        )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "client_id": existing_client_id,
                "base_url": existing_base_url,
            },
        )

    # ------------------------------------------------------------------
    # Reconfigure flow
    # ------------------------------------------------------------------

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Allow the user to change the base URL and/or credentials."""
        reconfigure_entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}

        current_base_url: str = reconfigure_entry.data[CONF_BASE_URL]
        current_client_id: str = reconfigure_entry.data[CONF_CLIENT_ID]

        if user_input is not None:
            base_url: str = user_input[CONF_BASE_URL].rstrip("/")
            client_id: str = user_input[CONF_CLIENT_ID]
            client_secret: str = user_input[CONF_CLIENT_SECRET]

            try:
                await _async_validate_credentials(
                    self.hass, base_url, client_id, client_secret
                )
            except Exception as exc:
                _LOGGER.debug(
                    "SolaXCloud reconfigure validation failed: %s", exc, exc_info=True
                )
                errors["base"] = _map_error(exc)
            else:
                await self.async_set_unique_id(client_id)
                self._abort_if_unique_id_configured(
                    updates={
                        CONF_BASE_URL: base_url,
                        CONF_CLIENT_ID: client_id,
                        CONF_CLIENT_SECRET: client_secret,
                    }
                )
                return self.async_update_reload_and_abort(
                    reconfigure_entry,
                    data_updates={
                        CONF_BASE_URL: base_url,
                        CONF_CLIENT_ID: client_id,
                        CONF_CLIENT_SECRET: client_secret,
                    },
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_build_credentials_schema(
                base_url=current_base_url,
                client_id=current_client_id,
            ),
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Options flow hook
    # ------------------------------------------------------------------

    @staticmethod
    @callback  # type: ignore[untyped-decorator]
    def async_get_options_flow(config_entry: ConfigEntry) -> SolaxCloudOptionsFlow:
        """Return the options flow handler."""
        return SolaxCloudOptionsFlow()


# ---------------------------------------------------------------------------
# Options flow
# ---------------------------------------------------------------------------


class SolaxCloudOptionsFlow(OptionsFlow):  # type: ignore[misc]
    """Handle SolaXCloud options (scan interval, etc.)."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        current_interval: int = self.config_entry.options.get(
            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
        )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_INTERVAL, default=current_interval
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_SCAN_INTERVAL,
                        max=3600,
                        step=1,
                        mode=NumberSelectorMode.BOX,
                        unit_of_measurement="s",
                    )
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
