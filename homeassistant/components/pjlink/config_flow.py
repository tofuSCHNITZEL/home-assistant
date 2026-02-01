"""Config flow for PJLink integration."""

from __future__ import annotations

import logging
from typing import Any

from pypjlink import Projector
from pypjlink.projector import ProjectorError
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT
from homeassistant.helpers import config_validation as cv

from .const import CONF_ENCODING, DEFAULT_ENCODING, DEFAULT_PORT, DOMAIN

_LOGGER = logging.getLogger(__name__)


class PJLinkConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for PJLink."""

    VERSION = 1
    MINOR_VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Validate connection
            try:
                await self.hass.async_add_executor_job(
                    self._test_connection, user_input
                )
            except TimeoutError:
                errors["base"] = "timeout_connect"
            except ProjectorError:
                errors["base"] = "cannot_connect"
            except Exception:  # Allowed in config flow for robustness
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                # Use host:port as unique ID
                unique_id = f"{user_input[CONF_HOST]}:{user_input[CONF_PORT]}"
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=user_input[CONF_HOST],
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST): cv.string,
                    vol.Optional(CONF_PORT, default=DEFAULT_PORT): cv.port,
                    vol.Optional(CONF_PASSWORD): cv.string,
                    vol.Optional(CONF_ENCODING, default=DEFAULT_ENCODING): cv.string,
                }
            ),
            errors=errors,
        )

    @staticmethod
    def _test_connection(user_input: dict[str, Any]) -> None:
        """Test the connection to the PJLink projector."""
        host = user_input[CONF_HOST]
        port = user_input[CONF_PORT]
        password = user_input.get(CONF_PASSWORD)
        encoding = user_input.get(CONF_ENCODING, DEFAULT_ENCODING)

        projector = Projector.from_address(host, port, encoding)
        projector.authenticate(password)
        # Test by getting power state to verify connection
        projector.get_power()

    async def async_step_import(self, import_data: dict[str, Any]) -> ConfigFlowResult:
        """Handle import from YAML configuration."""
        # Use host:port as unique ID
        unique_id = (
            f"{import_data[CONF_HOST]}:{import_data.get(CONF_PORT, DEFAULT_PORT)}"
        )
        await self.async_set_unique_id(unique_id)
        self._abort_if_unique_id_configured()

        # Test connection during import
        try:
            await self.hass.async_add_executor_job(self._test_connection, import_data)
        except (TimeoutError, ProjectorError, Exception):
            _LOGGER.exception(
                "Failed to import PJLink device from YAML: %s",
                import_data[CONF_HOST],
            )
            return self.async_abort(reason="cannot_connect")

        return self.async_create_entry(
            title=import_data[CONF_HOST],
            data={
                CONF_HOST: import_data[CONF_HOST],
                CONF_PORT: import_data.get(CONF_PORT, DEFAULT_PORT),
                CONF_PASSWORD: import_data.get(CONF_PASSWORD),
                CONF_ENCODING: import_data.get(CONF_ENCODING, DEFAULT_ENCODING),
            },
        )
