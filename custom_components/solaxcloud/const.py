# custom_components/solaxcloud/const.py
"""Constants for the SolaXCloud integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "solaxcloud"

# Configuration keys (stored in ConfigEntry.data)
CONF_BASE_URL: Final = "base_url"
CONF_CLIENT_ID: Final = "client_id"
CONF_CLIENT_SECRET: Final = "client_secret"

# Options keys (stored in ConfigEntry.options)
# CONF_SCAN_INTERVAL is imported from homeassistant.const ("scan_interval")

# Defaults
DEFAULT_BASE_URL: Final = "https://openapi-eu.solaxcloud.com"
DEFAULT_SCAN_INTERVAL: Final = 300  # seconds — raised to respect API rate limits
MIN_SCAN_INTERVAL: Final = 60  # seconds

# API paths (relative to base URL)
API_PATH_TOKEN: Final = "/openapi/auth/oauth/token"
API_PATH_PLANT_INFO: Final = "/openapi/v2/plant/page_plant_info"
API_PATH_PLANT_REALTIME: Final = "/openapi/v2/plant/realtime_data"
API_PATH_DEVICE_INFO: Final = "/openapi/v2/device/page_device_info"
API_PATH_REALTIME_DATA: Final = "/openapi/v2/device/realtime_data"

# OAuth2 grant type
OAUTH2_GRANT_TYPE: Final = "client_credentials"

# Token response fields
TOKEN_FIELD_CODE: Final = "code"
TOKEN_FIELD_RESULT: Final = "result"
TOKEN_FIELD_ACCESS_TOKEN: Final = "access_token"
TOKEN_FIELD_EXPIRES_IN: Final = "expires_in"

# Proactive token refresh buffer (seconds before actual expiry)
TOKEN_EXPIRY_BUFFER: Final = timedelta(seconds=60)

# API success code (used by data endpoints; token endpoint uses 0)
API_SUCCESS_CODE: Final = 10000

# SolaXCloud application-level error codes
API_ERROR_OPERATION_FAILED: Final = 10001  # Generic failure
API_ERROR_SYSTEM_BUSY: Final = 11500  # System busy, retry later
API_ERROR_NOT_AUTHENTICATED: Final = 10400  # Request not authenticated
API_ERROR_BAD_CREDENTIALS: Final = 10401  # Username or password incorrect
API_ERROR_TOKEN_INVALID: Final = 10402  # access_token authentication failed
API_ERROR_NO_PERMISSION: Final = 10403  # Interface has no access rights
API_ERROR_QUOTA_EXHAUSTED: Final = 10405  # API call quota fully consumed
API_ERROR_RATE_LIMIT: Final = 10406  # API call rate limit reached

# Device type query parameter values
DEVICE_TYPE_INVERTER: Final = 1
DEVICE_TYPE_BATTERY: Final = 2

# businessType query parameter value (mandatory for plant/device endpoints)
BUSINESS_TYPE: Final = 1
