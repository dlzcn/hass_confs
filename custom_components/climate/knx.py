"""
Support for KNX/IP climate devices.
For more details about this platform, please refer to the documentation at
https://home-assistant.io/components/climate.knx/

Modified by Haifeng for KTS smart solution in Guohao Changfeng Residence
 - Air conditioner: temperature, target_temperature, operation_mode, fan_mode, on_off
 - Floor heating: temperature, target_temperature, on_off
"""

import voluptuous as vol

from homeassistant.components.climate import (
    PLATFORM_SCHEMA, SUPPORT_OPERATION_MODE, SUPPORT_FAN_MODE,
    SUPPORT_TARGET_TEMPERATURE, SUPPORT_ON_OFF, ClimateDevice)
from homeassistant.components.knx import ATTR_DISCOVER_DEVICES, DATA_KNX
from homeassistant.const import ATTR_TEMPERATURE, CONF_NAME, TEMP_CELSIUS, STATE_UNKNOWN
from homeassistant.core import callback
import homeassistant.helpers.config_validation as cv

CONF_TARGET_TEMPERATURE_STEP = 'target_temperature_step'
CONF_TARGET_TEMPERATURE_MAX = 'target_temperature_max'
CONF_TARGET_TEMPERATURE_MIN = 'target_temperature_min'
CONF_TEMPERATURE_ADDRESS = 'temperature_address'
CONF_TARGET_TEMPERATURE_ADDRESS = 'target_temperature_address'
CONF_TARGET_TEMPERATURE_STATE_ADDRESS = 'target_temperature_state_address'
CONF_OPERATION_MODE_ADDRESS = 'operation_mode_address'
CONF_OPERATION_MODE_STATE_ADDRESS = 'operation_mode_state_address'
CONF_FAN_MODE_ADDRESS = 'fan_mode_address'
CONF_FAN_MODE_STATE_ADDRESS = 'fan_mode_state_address'
CONF_ON_OFF_ADDRESS = 'on_off_address'
CONF_ON_OFF_STATE_ADDRESS = 'on_off_state_address'

DEFAULT_NAME = 'KTS Climate'
DEFAULT_TARGET_TEMPERATURE_STEP = 0.5
DEFAULT_TARGET_TEMPERATURE_MAX = 30
DEFAULT_TARGET_TEMPERATURE_MIN = 5
DEPENDENCIES = ['knx']

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
    vol.Required(CONF_TEMPERATURE_ADDRESS): cv.string,
    vol.Required(CONF_TARGET_TEMPERATURE_ADDRESS): cv.string,
    vol.Required(CONF_TARGET_TEMPERATURE_STATE_ADDRESS): cv.string,
    vol.Optional(CONF_TARGET_TEMPERATURE_STEP,
                 default=DEFAULT_TARGET_TEMPERATURE_STEP): vol.All(
                     float, vol.Range(min=0, max=2)),
    vol.Optional(CONF_TARGET_TEMPERATURE_MAX, default=DEFAULT_TARGET_TEMPERATURE_MAX):
        vol.All(int, vol.Range(min=15, max=35)),
    vol.Optional(CONF_TARGET_TEMPERATURE_MIN, default=DEFAULT_TARGET_TEMPERATURE_MIN):
        vol.All(int, vol.Range(min=0, max=15)),
    vol.Optional(CONF_OPERATION_MODE_ADDRESS): cv.string,
    vol.Optional(CONF_OPERATION_MODE_STATE_ADDRESS): cv.string,
    vol.Optional(CONF_FAN_MODE_ADDRESS): cv.string,
    vol.Optional(CONF_FAN_MODE_STATE_ADDRESS): cv.string,
    vol.Optional(CONF_ON_OFF_ADDRESS): cv.string,
    vol.Optional(CONF_ON_OFF_STATE_ADDRESS): cv.string,
    })


async def async_setup_platform(hass, config, async_add_devices,
                               discovery_info=None):
    """Set up climate(s) for KNX platform."""
    if discovery_info is not None:
        async_add_devices_discovery(hass, discovery_info, async_add_devices)
    else:
        async_add_devices_config(hass, config, async_add_devices)


@callback
def async_add_devices_discovery(hass, discovery_info, async_add_devices):
    """Set up climates for KNX platform configured within platform."""
    entities = []
    for device_name in discovery_info[ATTR_DISCOVER_DEVICES]:
        device = hass.data[DATA_KNX].xknx.devices[device_name]
        entities.append(KNXClimate(hass, device))
    async_add_devices(entities)


@callback
def async_add_devices_config(hass, config, async_add_devices):
    """Set up climate for KNX platform configured within platform."""
    from ._kts_climate import KTSClimate

    climate = KTSClimate(
        hass.data[DATA_KNX].xknx,
        name=config.get(CONF_NAME),
        group_address_temperature=config.get(CONF_TEMPERATURE_ADDRESS),
        group_address_target_temperature=config.get(
            CONF_TARGET_TEMPERATURE_ADDRESS),
        group_address_target_temperature_state=config.get(
            CONF_TARGET_TEMPERATURE_STATE_ADDRESS),
        target_temperature_step=config.get(CONF_TARGET_TEMPERATURE_STEP),
        target_temperature_max=config.get(CONF_TARGET_TEMPERATURE_MAX),
        target_temperature_min=config.get(CONF_TARGET_TEMPERATURE_MIN),
        group_address_operation_mode=config.get(CONF_OPERATION_MODE_ADDRESS),
        group_address_operation_mode_state=config.get(
            CONF_OPERATION_MODE_STATE_ADDRESS),
        group_address_fan_mode=config.get(CONF_FAN_MODE_ADDRESS),
        group_address_fan_mode_state=config.get(CONF_FAN_MODE_STATE_ADDRESS),
        group_address_on_off=config.get(CONF_ON_OFF_ADDRESS),
        group_address_on_off_state=config.get(CONF_ON_OFF_STATE_ADDRESS))
    hass.data[DATA_KNX].xknx.devices.add(climate)
    async_add_devices([KNXClimate(hass, climate)])


class KNXClimate(ClimateDevice):
    """Representation of a KNX climate device."""

    def __init__(self, hass, device):
        """Initialize of a KNX climate device."""
        self.device = device
        self.hass = hass
        self.async_register_callbacks()

        self._unit_of_measurement = TEMP_CELSIUS

    @property
    def supported_features(self):
        """Return the list of supported features."""
        support = SUPPORT_TARGET_TEMPERATURE
        if self.device.supports_operation_mode:
            support |= SUPPORT_OPERATION_MODE
        if self.device.supports_fan_mode:
            support |= SUPPORT_FAN_MODE
        if self.device.supports_on_off:
            support |= SUPPORT_ON_OFF
        return support

    def async_register_callbacks(self):
        """Register callbacks to update hass after device was changed."""
        async def after_update_callback(device):
            """Call after device was updated."""
            # pylint: disable=unused-argument
            await self.async_update_ha_state()
        self.device.register_device_updated_cb(after_update_callback)

    @property
    def name(self):
        """Return the name of the KNX device."""
        return self.device.name

    @property
    def available(self):
        """Return True if entity is available."""
        return self.hass.data[DATA_KNX].connected

    @property
    def should_poll(self):
        """No polling needed within KNX."""
        return False

    @property
    def temperature_unit(self):
        """Return the unit of measurement."""
        return self._unit_of_measurement

    @property
    def current_temperature(self):
        """Return the current temperature."""
        return self.device.temperature.value

    @property
    def target_temperature_step(self):
        """Return the supported step of target temperature."""
        return self.device.target_temperature_step

    @property
    def target_temperature(self):
        """Return the temperature we try to reach."""
        return self.device.target_temperature.value

    @property
    def min_temp(self):
        """Return the minimum temperature."""
        return self.device.target_temperature_min

    @property
    def max_temp(self):
        """Return the maximum temperature."""
        return self.device.target_temperature_max

    async def async_set_temperature(self, **kwargs):
        """Set new target temperature."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return
        await self.device.set_target_temperature(temperature)
        await self.async_update_ha_state()

    @property
    def current_operation(self):
        """Return current operation ie. heat, cool, idle."""
        return self.device.get_operation_mode()

    @property
    def operation_list(self):
        """Return the list of available operation modes."""
        return self.device.get_supported_operation_modes()

    async def async_set_operation_mode(self, operation_mode):
        """Set operation mode."""
        if self.device.supports_operation_mode:
            await self.device.set_operation_mode(operation_mode)

    @property
    def current_fan_mode(self):
        """Return the fan setting."""
        return self.device.get_fan_mode()

    async def async_set_fan_mode(self, fan_mode):
        """Set fan mode."""
        if self.device.supports_fan_mode:
            await self.device.set_fan_mode(fan_mode)

    @property
    def fan_list(self):
        """List of available fan modes."""
        return self.device.get_supported_fan_modes()

    @property
    def is_on(self):
        """Return true if the device is on."""
        if self.device.supports_on_off:
            return self.device.is_on
        return STATE_UNKNOWN

    async def async_turn_on(self):
        """Turn on."""
        await self.device.turn_on()

    async def async_turn_off(self):
        """Turn off."""
        await self.device.turn_off()
