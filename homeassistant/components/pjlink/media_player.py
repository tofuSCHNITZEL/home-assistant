"""Support for controlling projector via the PJLink protocol."""

from __future__ import annotations

import logging

from pypjlink import MUTE_AUDIO, Projector
from pypjlink.projector import ProjectorError
import voluptuous as vol

from homeassistant.components.media_player import (
    PLATFORM_SCHEMA as MEDIA_PLAYER_PLATFORM_SCHEMA,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PASSWORD, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import (
    AddConfigEntryEntitiesCallback,
    AddEntitiesCallback,
)
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from .const import CONF_ENCODING, DEFAULT_ENCODING, DEFAULT_PORT, DOMAIN

_LOGGER = logging.getLogger(__name__)

ERR_PROJECTOR_UNAVAILABLE = "projector unavailable"

PLATFORM_SCHEMA = MEDIA_PLAYER_PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_HOST): cv.string,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): cv.port,
        vol.Optional(CONF_NAME): cv.string,
        vol.Optional(CONF_ENCODING, default=DEFAULT_ENCODING): cv.string,
        vol.Optional(CONF_PASSWORD): cv.string,
    }
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the PJLink platform from a config entry."""
    host = config_entry.data[CONF_HOST]
    port = config_entry.data.get(CONF_PORT, DEFAULT_PORT)
    encoding = config_entry.data.get(CONF_ENCODING, DEFAULT_ENCODING)
    password = config_entry.data.get(CONF_PASSWORD)

    device = PjLinkDevice(hass, host, port, encoding, password, config_entry.entry_id)
    async_add_entities([device], True)


def setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the PJLink platform."""
    host: str | None = config.get(CONF_HOST)
    port: int | None = config.get(CONF_PORT)
    encoding: str | None = config.get(CONF_ENCODING)
    password: str | None = config.get(CONF_PASSWORD)

    if not host or port is None:
        return

    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {}
    hass_data = hass.data[DOMAIN]

    device_label = f"{host}:{port}"
    if device_label in hass_data:
        return

    device = PjLinkDevice(hass, host, port, encoding or "", password, "setup_platform")
    hass_data[device_label] = device
    add_entities([device], True)


def format_input_source(input_source_name: str, input_source_number: str) -> str:
    """Format input source for display in UI."""
    return f"{input_source_name} {input_source_number}"


class PjLinkDevice(MediaPlayerEntity):
    """Representation of a PJLink device."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_supported_features = (
        MediaPlayerEntityFeature.VOLUME_MUTE
        | MediaPlayerEntityFeature.TURN_ON
        | MediaPlayerEntityFeature.TURN_OFF
        | MediaPlayerEntityFeature.SELECT_SOURCE
    )

    def __init__(
        self,
        hass: HomeAssistant,
        host: str,
        port: int,
        encoding: str,
        password: str | None,
        entry_id: str,
    ) -> None:
        """Initialize the PJLink device."""
        self._hass = hass
        self._host = host
        self._port = port
        self._password = password
        self._encoding = encoding
        self._entry_id = entry_id
        self._source_name_mapping: dict[str, tuple[str, str]] = {}
        self._projector_name: str | None = None
        self._unavailable_logged = False

        self._attr_unique_id = f"{host}_{port}"
        self._attr_is_volume_muted = False
        self._attr_state = MediaPlayerState.OFF
        self._attr_source = None
        self._attr_source_list = []
        self._attr_available = False
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{host}:{port}")},
            name=f"PJLink {host}",
            manufacturer="PJLink",
        )

    def _force_off(self) -> None:
        """Force the projector state to off."""
        self._attr_state = MediaPlayerState.OFF
        self._attr_is_volume_muted = False
        self._attr_source = None

    async def _async_setup_projector(self) -> bool:
        """Set up the projector and retrieve initial information."""
        try:
            projector_data = await self._hass.async_add_executor_job(
                self._get_projector_info
            )
        except ProjectorError as err:
            if str(err) == ERR_PROJECTOR_UNAVAILABLE:
                return False
            raise

        self._projector_name, inputs = projector_data
        if self._projector_name:
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, f"{self._host}:{self._port}")},
                name=self._projector_name,
                manufacturer="PJLink",
            )
        self._source_name_mapping = {format_input_source(*x): x for x in inputs}
        self._attr_source_list = sorted(self._source_name_mapping)
        return True

    def _get_projector_info(self) -> tuple[str | None, list[tuple[str, str]]]:
        """Get projector name and inputs (blocking call)."""
        projector = Projector.from_address(self._host, self._port, self._encoding)
        projector.authenticate(self._password)
        name = projector.get_name()
        inputs = projector.get_inputs()
        return name, inputs

    def _get_power_state(self) -> str:
        """Get power state (blocking call)."""
        projector = Projector.from_address(self._host, self._port, self._encoding)
        projector.authenticate(self._password)
        return projector.get_power()

    def _get_mute_state(self) -> tuple[bool, bool]:
        """Get mute state (blocking call)."""
        projector = Projector.from_address(self._host, self._port, self._encoding)
        projector.authenticate(self._password)
        return projector.get_mute()

    def _get_current_input(self) -> tuple[str, str]:
        """Get current input (blocking call)."""
        projector = Projector.from_address(self._host, self._port, self._encoding)
        projector.authenticate(self._password)
        return projector.get_input()

    def _set_power_state(self, state: str) -> None:
        """Set power state (blocking call)."""
        projector = Projector.from_address(self._host, self._port, self._encoding)
        projector.authenticate(self._password)
        projector.set_power(state)

    def _set_mute_state(self, mute: bool) -> None:
        """Set mute state (blocking call)."""
        projector = Projector.from_address(self._host, self._port, self._encoding)
        projector.authenticate(self._password)
        projector.set_mute(MUTE_AUDIO, mute)

    def _set_input_source(self, source_name: str, source_number: str) -> None:
        """Set input source (blocking call)."""
        projector = Projector.from_address(self._host, self._port, self._encoding)
        projector.authenticate(self._password)
        projector.set_input(source_name, source_number)

    async def async_update(self) -> None:
        """Get the latest state from the device."""
        if not self._attr_available:
            self._attr_available = await self._async_setup_projector()

        if not self._attr_available:
            if not self._unavailable_logged:
                _LOGGER.info(
                    "Projector at %s:%s is unavailable", self._host, self._port
                )
                self._unavailable_logged = True
            self._force_off()
            return

        try:
            pwstate = await self._hass.async_add_executor_job(self._get_power_state)
        except (ProjectorError, TimeoutError, OSError) as err:
            if not self._unavailable_logged:
                _LOGGER.info(
                    "Projector at %s:%s became unavailable: %s",
                    self._host,
                    self._port,
                    err,
                )
                self._unavailable_logged = True
            self._attr_available = False
            self._force_off()
            return

        if self._unavailable_logged:
            _LOGGER.info("Projector at %s:%s is back online", self._host, self._port)
            self._unavailable_logged = False

        try:
            if pwstate in ("on", "warm-up"):
                self._attr_state = MediaPlayerState.ON
                mute_state = await self._hass.async_add_executor_job(
                    self._get_mute_state
                )
                self._attr_is_volume_muted = mute_state[1]
                current_input = await self._hass.async_add_executor_job(
                    self._get_current_input
                )
                self._attr_source = format_input_source(*current_input)
            else:
                self._force_off()
        except KeyError as err:
            if str(err) == "'OK'":
                self._force_off()
            else:
                raise
        except ProjectorError as err:
            if str(err) == "unavailable time":
                self._force_off()
            else:
                raise

    async def async_turn_off(self) -> None:
        """Turn projector off."""
        await self._hass.async_add_executor_job(self._set_power_state, "off")

    async def async_turn_on(self) -> None:
        """Turn projector on."""
        await self._hass.async_add_executor_job(self._set_power_state, "on")

    async def async_mute_volume(self, mute: bool) -> None:
        """Mute (true) or unmute (false) media player."""
        await self._hass.async_add_executor_job(self._set_mute_state, mute)

    async def async_select_source(self, source: str) -> None:
        """Set the input source."""
        source_name, source_number = self._source_name_mapping[source]
        await self._hass.async_add_executor_job(
            self._set_input_source, source_name, source_number
        )
