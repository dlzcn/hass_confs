"""Support for KTS KNX climate devices."""
import voluptuous as vol

from ._kts_climate import KTSClimate

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
    PLATFORM_SCHEMA,
)
from homeassistant.components.kts_knx import DATA_KNX
from homeassistant.const import ATTR_TEMPERATURE, CONF_NAME, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

CONF_TARGET_TEMPERATURE_STEP = "target_temperature_step"
CONF_TARGET_TEMPERATURE_MAX = "target_temperature_max"
CONF_TARGET_TEMPERATURE_MIN = "target_temperature_min"
CONF_TEMPERATURE_ADDRESS = "temperature_address"
CONF_TARGET_TEMPERATURE_ADDRESS = "target_temperature_address"
CONF_TARGET_TEMPERATURE_STATE_ADDRESS = "target_temperature_state_address"
CONF_OPERATION_MODE_ADDRESS = "operation_mode_address"
CONF_OPERATION_MODE_STATE_ADDRESS = "operation_mode_state_address"
CONF_FAN_MODE_ADDRESS = "fan_mode_address"
CONF_FAN_MODE_STATE_ADDRESS = "fan_mode_state_address"
CONF_ON_OFF_ADDRESS = "on_off_address"
CONF_ON_OFF_STATE_ADDRESS = "on_off_state_address"

DEFAULT_NAME = "KTS Climate"
DEFAULT_TARGET_TEMPERATURE_STEP = 0.5
DEFAULT_TARGET_TEMPERATURE_MAX = 30
DEFAULT_TARGET_TEMPERATURE_MIN = 5

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Required(CONF_TEMPERATURE_ADDRESS): cv.string,
        vol.Required(CONF_TARGET_TEMPERATURE_ADDRESS): cv.string,
        vol.Required(CONF_TARGET_TEMPERATURE_STATE_ADDRESS): cv.string,
        vol.Optional(
            CONF_TARGET_TEMPERATURE_STEP, default=DEFAULT_TARGET_TEMPERATURE_STEP
        ): vol.All(float, vol.Range(min=0, max=2)),
        vol.Optional(
            CONF_TARGET_TEMPERATURE_MAX, default=DEFAULT_TARGET_TEMPERATURE_MAX
        ): vol.All(int, vol.Range(min=15, max=35)),
        vol.Optional(
            CONF_TARGET_TEMPERATURE_MIN, default=DEFAULT_TARGET_TEMPERATURE_MIN
        ): vol.All(int, vol.Range(min=0, max=15)),
        vol.Optional(CONF_OPERATION_MODE_ADDRESS): cv.string,
        vol.Optional(CONF_OPERATION_MODE_STATE_ADDRESS): cv.string,
        vol.Optional(CONF_FAN_MODE_ADDRESS): cv.string,
        vol.Optional(CONF_FAN_MODE_STATE_ADDRESS): cv.string,
        vol.Optional(CONF_ON_OFF_ADDRESS): cv.string,
        vol.Optional(CONF_ON_OFF_STATE_ADDRESS): cv.string,
    }
)

# Map KTS operation modes to HA modes.
OPERATION_MODES = {
    "Cool": HVACMode.COOL,
    "Heat": HVACMode.HEAT,
    "Fan": HVACMode.FAN_ONLY,
    "Dry": HVACMode.DRY,
}

OPERATION_MODES_INV = {v: k for k, v in OPERATION_MODES.items()}


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up climates for the KTS KNX platform."""
    climate = KTSClimate(
        hass.data[DATA_KNX].xknx,
        name=config.get(CONF_NAME),
        group_address_temperature=config.get(CONF_TEMPERATURE_ADDRESS),
        group_address_target_temperature=config.get(CONF_TARGET_TEMPERATURE_ADDRESS),
        group_address_target_temperature_state=config.get(
            CONF_TARGET_TEMPERATURE_STATE_ADDRESS
        ),
        target_temperature_step=config.get(CONF_TARGET_TEMPERATURE_STEP),
        target_temperature_max=config.get(CONF_TARGET_TEMPERATURE_MAX),
        target_temperature_min=config.get(CONF_TARGET_TEMPERATURE_MIN),
        group_address_operation_mode=config.get(CONF_OPERATION_MODE_ADDRESS),
        group_address_operation_mode_state=config.get(
            CONF_OPERATION_MODE_STATE_ADDRESS
        ),
        group_address_fan_mode=config.get(CONF_FAN_MODE_ADDRESS),
        group_address_fan_mode_state=config.get(CONF_FAN_MODE_STATE_ADDRESS),
        group_address_on_off=config.get(CONF_ON_OFF_ADDRESS),
        group_address_on_off_state=config.get(CONF_ON_OFF_STATE_ADDRESS),
    )
    hass.data[DATA_KNX].xknx.devices.async_add(climate)
    async_add_entities([KNXClimate(climate)])


class KNXClimate(ClimateEntity):
    """Representation of a KTS KNX climate device."""

    _attr_should_poll = False
    _attr_temperature_unit = UnitOfTemperature.CELSIUS

    def __init__(self, device: KTSClimate) -> None:
        """Initialize of a KTS KNX climate device."""
        self.device = device
        self._attr_name = device.name
        self._attr_unique_id = device.name

    @property
    def supported_features(self) -> int:
        """Return the list of supported features."""
        support = ClimateEntityFeature.TARGET_TEMPERATURE
        if self.device.supports_fan_mode:
            support |= ClimateEntityFeature.FAN_MODE
        return support

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
    def current_temperature(self) -> float | None:
        """Return the current temperature."""
        return self.device.temperature.value

    @property
    def target_temperature_step(self) -> float | None:
        """Return the supported step of target temperature."""
        return self.device.target_temperature_step

    @property
    def target_temperature(self) -> float | None:
        """Return the temperature we try to reach."""
        return self.device.target_temperature.value

    @property
    def min_temp(self) -> float:
        """Return the minimum temperature."""
        return self.device.target_temperature_min

    @property
    def max_temp(self) -> float:
        """Return the maximum temperature."""
        return self.device.target_temperature_max

    async def async_set_temperature(self, **kwargs) -> None:
        """Set new target temperature."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return
        await self.device.set_target_temperature(temperature)
        self.async_write_ha_state()

    @property
    def hvac_mode(self) -> HVACMode:
        """Return current operation ie. heat, cool, idle."""
        if self.device.supports_on_off and not self.device.is_on:
            return HVACMode.OFF
        kts_op_mode = self.device.get_operation_mode()
        return OPERATION_MODES.get(kts_op_mode, HVACMode.HEAT)

    @property
    def hvac_modes(self) -> list[HVACMode]:
        """Return the list of available operation modes."""
        kts_op_list = self.device.get_supported_operation_modes()
        modes = [OPERATION_MODES[mode] for mode in kts_op_list]
        if self.device.supports_on_off:
            if HVACMode.HEAT not in modes:
                modes.append(HVACMode.HEAT)
            modes.append(HVACMode.OFF)
        return modes

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set operation mode."""
        if self.device.supports_on_off:
            if hvac_mode == HVACMode.OFF:
                await self.device.turn_off()
                return
            await self.device.turn_on()
        if self.device.supports_operation_mode:
            kts_op_mode = OPERATION_MODES_INV.get(hvac_mode)
            await self.device.set_operation_mode(kts_op_mode)
            self.async_write_ha_state()

    @property
    def fan_mode(self) -> str | None:
        """Return the fan setting."""
        return self.device.get_fan_mode()

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set fan mode."""
        if self.device.supports_fan_mode:
            await self.device.set_fan_mode(fan_mode)
            self.async_write_ha_state()

    @property
    def fan_modes(self) -> list[str] | None:
        """List of available fan modes."""
        return self.device.get_supported_fan_modes()

    @property
    def is_on(self) -> bool | None:
        """Return true if the device is on."""
        if self.device.supports_on_off:
            return self.device.is_on
        return None

    async def async_turn_on(self) -> None:
        """Turn on."""
        await self.device.turn_on()

    async def async_turn_off(self) -> None:
        """Turn off."""
        await self.device.turn_off()
