"""Support for KTS KNX lights."""
import voluptuous as vol
from xknx.devices import Light as XknxLight

from homeassistant.components.kts_knx import ATTR_DISCOVER_DEVICES, DATA_KNX
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ColorMode,
    LightEntity,
    PLATFORM_SCHEMA,
)
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant, callback
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

CONF_STATE_ADDRESS = "state_address"
CONF_BRIGHTNESS_ADDRESS = "brightness_address"
CONF_BRIGHTNESS_STATE_ADDRESS = "brightness_state_address"
CONF_MIN_KELVIN = "min_kelvin"
CONF_MAX_KELVIN = "max_kelvin"

DEFAULT_NAME = "KTS KNX Light"
DEFAULT_MIN_KELVIN = 2700
DEFAULT_MAX_KELVIN = 6000

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_ADDRESS): cv.string,
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Optional(CONF_STATE_ADDRESS): cv.string,
        vol.Optional(CONF_BRIGHTNESS_ADDRESS): cv.string,
        vol.Optional(CONF_BRIGHTNESS_STATE_ADDRESS): cv.string,
        vol.Optional(CONF_MIN_KELVIN, default=DEFAULT_MIN_KELVIN): vol.All(
            vol.Coerce(int), vol.Range(min=1)
        ),
        vol.Optional(CONF_MAX_KELVIN, default=DEFAULT_MAX_KELVIN): vol.All(
            vol.Coerce(int), vol.Range(min=1)
        ),
    }
)


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up lights for the KTS KNX platform."""
    if discovery_info is not None:
        entities = []
        for device_name in discovery_info[ATTR_DISCOVER_DEVICES]:
            device = hass.data[DATA_KNX].xknx.devices[device_name]
            entities.append(KNXLight(device))
        async_add_entities(entities)
        return

    light = XknxLight(
        hass.data[DATA_KNX].xknx,
        name=config[CONF_NAME],
        group_address_switch=config[CONF_ADDRESS],
        group_address_switch_state=config.get(CONF_STATE_ADDRESS),
        group_address_brightness=config.get(CONF_BRIGHTNESS_ADDRESS),
        group_address_brightness_state=config.get(CONF_BRIGHTNESS_STATE_ADDRESS),
        min_kelvin=config[CONF_MIN_KELVIN],
        max_kelvin=config[CONF_MAX_KELVIN],
    )
    hass.data[DATA_KNX].xknx.devices.async_add(light)
    async_add_entities([KNXLight(light)])


class KNXLight(LightEntity):
    """Representation of a KTS KNX light."""

    _attr_should_poll = False

    def __init__(self, device: XknxLight) -> None:
        """Initialize of KTS KNX light."""
        self.device = device
        self._attr_name = device.name
        self._attr_unique_id = device.name
        self._attr_min_kelvin = device.min_kelvin
        self._attr_max_kelvin = device.max_kelvin

    @callback
    def async_register_callbacks(self) -> None:
        """Register callbacks to update hass after device was changed."""

        async def after_update_callback(device) -> None:
            """Call after device was updated."""
            self.async_write_ha_state()

        self.device.register_device_updated_cb(after_update_callback)

    async def async_added_to_hass(self) -> None:
        """Store register state change callback."""
        self.async_register_callbacks()

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.hass.data[DATA_KNX].connected

    @property
    def brightness(self) -> int | None:
        """Return the brightness of this light between 0..255."""
        if not self.device.supports_brightness:
            return None
        return self.device.current_brightness

    @property
    def color_mode(self) -> ColorMode:
        """Return the color mode of the light."""
        if self.device.supports_brightness:
            return ColorMode.BRIGHTNESS
        return ColorMode.ONOFF

    @property
    def supported_color_modes(self) -> set[ColorMode]:
        """Flag supported color modes."""
        return {self.color_mode}

    @property
    def is_on(self) -> bool:
        """Return true if light is on."""
        return bool(self.device.state)

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the light on."""
        brightness = kwargs.get(ATTR_BRIGHTNESS)
        if self.device.supports_brightness and brightness is not None:
            await self.device.set_brightness(brightness)
        else:
            await self.device.set_on()

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the light off."""
        await self.device.set_off()
