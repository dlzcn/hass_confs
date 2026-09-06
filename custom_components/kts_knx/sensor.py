"""Support for KTS KNX sensors."""
import voluptuous as vol
from xknx.devices import Sensor as XknxSensor

from homeassistant.components.kts_knx import ATTR_DISCOVER_DEVICES, DATA_KNX
from homeassistant.components.sensor import (
    PLATFORM_SCHEMA,
    SensorDeviceClass,
    SensorEntity,
)
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant, callback
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

CONF_STATE_ADDRESS = "state_address"
CONF_SYNC_STATE = "sync_state"
CONF_VALUE_TYPE = "type"
DEFAULT_NAME = "KTS KNX Sensor"

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Optional(CONF_SYNC_STATE, default=True): cv.boolean,
        vol.Required(CONF_STATE_ADDRESS): cv.string,
        vol.Required(CONF_VALUE_TYPE): cv.string,
    }
)


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up sensors for the KTS KNX platform."""
    if discovery_info is not None:
        entities = []
        for device_name in discovery_info[ATTR_DISCOVER_DEVICES]:
            device = hass.data[DATA_KNX].xknx.devices[device_name]
            entities.append(KNXSensor(device))
        async_add_entities(entities)
        return

    sensor = XknxSensor(
        hass.data[DATA_KNX].xknx,
        name=config[CONF_NAME],
        group_address_state=config[CONF_STATE_ADDRESS],
        sync_state=config[CONF_SYNC_STATE],
        value_type=config[CONF_VALUE_TYPE],
    )
    hass.data[DATA_KNX].xknx.devices.async_add(sensor)
    async_add_entities([KNXSensor(sensor)])


class KNXSensor(SensorEntity):
    """Representation of a KTS KNX sensor."""

    _attr_should_poll = False

    def __init__(self, device: XknxSensor) -> None:
        """Initialize of a KTS KNX sensor."""
        self.device = device
        self._attr_name = device.name
        self._attr_unique_id = device.name
        self._async_update_device_class()

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
    def native_value(self):
        """Return the state of the sensor."""
        return self.device.resolve_state()

    @callback
    def _async_update_device_class(self) -> None:
        """Update the sensor device class from the xknx device."""
        ha_device_class = self.device.ha_device_class()
        if ha_device_class is None:
            return
        try:
            self._attr_device_class = SensorDeviceClass(ha_device_class)
        except ValueError:
            self._attr_device_class = None

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the unit this state is expressed in."""
        return self.device.unit_of_measurement()
