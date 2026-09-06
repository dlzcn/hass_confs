"""Support for KTS KNX binary sensors."""
import voluptuous as vol
from xknx.devices import BinarySensor as XknxBinarySensor

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    PLATFORM_SCHEMA,
)
from homeassistant.components.kts_knx import ATTR_DISCOVER_DEVICES, DATA_KNX
from homeassistant.const import CONF_DEVICE_CLASS, CONF_NAME
from homeassistant.core import HomeAssistant, callback
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

CONF_STATE_ADDRESS = "state_address"
CONF_SIGNIFICANT_BIT = "significant_bit"
CONF_SYNC_STATE = "sync_state"
CONF_RESET_AFTER = "reset_after"

DEFAULT_NAME = "KTS KNX Binary Sensor"

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Optional(CONF_SYNC_STATE, default=True): cv.boolean,
        vol.Required(CONF_STATE_ADDRESS): cv.string,
        vol.Optional(CONF_DEVICE_CLASS): cv.string,
        vol.Optional(CONF_RESET_AFTER): cv.positive_int,
    }
)


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up binary sensors for the KTS KNX platform."""
    module = hass.data[DATA_KNX]
    if discovery_info is not None:
        entities = []
        for device_name in discovery_info[ATTR_DISCOVER_DEVICES]:
            device = module.xknx.devices[device_name]
            device_config = module.device_configs.get(device_name, {})
            entities.append(
                KNXBinarySensor(device, device_config.get(CONF_DEVICE_CLASS))
            )
        async_add_entities(entities)
        return

    binary_sensor = XknxBinarySensor(
        module.xknx,
        name=config[CONF_NAME],
        group_address_state=config[CONF_STATE_ADDRESS],
        sync_state=config[CONF_SYNC_STATE],
        reset_after=config.get(CONF_RESET_AFTER),
    )
    module.xknx.devices.async_add(binary_sensor)
    async_add_entities([KNXBinarySensor(binary_sensor, config.get(CONF_DEVICE_CLASS))])


class KNXBinarySensor(BinarySensorEntity):
    """Representation of a KTS KNX binary sensor."""

    _attr_should_poll = False

    def __init__(self, device: XknxBinarySensor, device_class: str | None) -> None:
        """Initialize of KTS KNX binary sensor."""
        self.device = device
        self._attr_name = device.name
        self._attr_unique_id = device.name
        if device_class is not None:
            try:
                self._attr_device_class = BinarySensorDeviceClass(device_class)
            except ValueError:
                self._attr_device_class = None

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
    def is_on(self) -> bool:
        """Return true if the binary sensor is on."""
        return bool(self.device.is_on())
