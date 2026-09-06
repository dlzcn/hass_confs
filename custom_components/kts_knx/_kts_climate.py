"""
Module for managing KTS climate devices (air conditioner / floor heating)
via KNX.

Ported from the legacy custom_components/knx/_kts_climate.py (xknx 0.11 era)
to xknx 3.x.

Non-standard behaviours kept from the original implementation:

* operation mode uses DPT 1count (RemoteValueDptValue1Ucount) with the
  vendor specific mapping Cool=1, Dry=2, Fan=3, Heat=4.
* fan mode uses DPT 1count with Low=1, Medium=2, High=3, Auto=4.
* on/off is a plain DPT 1.001 switch.
"""
from xknx.devices import Device
from xknx.remote_value import (
    RemoteValueDptValue1Ucount,
    RemoteValueSwitch,
    RemoteValueTemp,
)


class KTSClimate(Device):
    """Class for managing the KTS climate."""

    DEFAULT_TARGET_TEMPERATURE_STEP = 0.5
    DEFAULT_TARGET_TEMPERATURE_MAX = 35
    DEFAULT_TARGET_TEMPERATURE_MIN = 5

    OPERATION_MODES = ("Cool", "Heat", "Fan", "Dry")
    OPERATION_MODE_VALUE = {"Cool": 1, "Dry": 2, "Fan": 3, "Heat": 4}
    OPERATION_MODE_FROM_VALUE = {v: k for k, v in OPERATION_MODE_VALUE.items()}

    FAN_MODES = ("Low", "Medium", "High", "Auto")
    FAN_MODE_VALUE = {"Low": 1, "Medium": 2, "High": 3, "Auto": 4}
    FAN_MODE_FROM_VALUE = {v: k for k, v in FAN_MODE_VALUE.items()}

    def __init__(
        self,
        xknx,
        name,
        group_address_temperature=None,
        group_address_target_temperature=None,
        group_address_target_temperature_state=None,
        target_temperature_step=DEFAULT_TARGET_TEMPERATURE_STEP,
        target_temperature_max=DEFAULT_TARGET_TEMPERATURE_MAX,
        target_temperature_min=DEFAULT_TARGET_TEMPERATURE_MIN,
        group_address_operation_mode=None,
        group_address_operation_mode_state=None,
        group_address_fan_mode=None,
        group_address_fan_mode_state=None,
        group_address_on_off=None,
        group_address_on_off_state=None,
        device_updated_cb=None,
    ):
        """Initialize Climate class."""
        super().__init__(xknx, name, device_updated_cb)

        self.temperature = RemoteValueTemp(
            xknx,
            group_address_state=group_address_temperature,
            device_name=self.name,
            after_update_cb=self.after_update,
        )

        self.target_temperature = RemoteValueTemp(
            xknx,
            group_address=group_address_target_temperature,
            group_address_state=group_address_target_temperature_state,
            device_name=self.name,
            after_update_cb=self.after_update,
        )

        self.target_temperature_step = target_temperature_step
        self.target_temperature_max = target_temperature_max
        self.target_temperature_min = target_temperature_min

        self.supports_on_off = (
            group_address_on_off is not None or group_address_on_off_state is not None
        )

        self.on = RemoteValueSwitch(
            xknx,
            group_address=group_address_on_off,
            group_address_state=group_address_on_off_state,
            device_name=self.name,
            after_update_cb=self.after_update,
        )

        self.supports_operation_mode = (
            group_address_operation_mode is not None
            or group_address_operation_mode_state is not None
        )

        self.operation_mode = RemoteValueDptValue1Ucount(
            xknx,
            group_address=group_address_operation_mode,
            group_address_state=group_address_operation_mode_state,
            device_name=self.name,
            after_update_cb=self.after_update,
        )

        self.supports_fan_mode = (
            group_address_fan_mode is not None
            or group_address_fan_mode_state is not None
        )

        self.fan_mode = RemoteValueDptValue1Ucount(
            xknx,
            group_address=group_address_fan_mode,
            group_address_state=group_address_fan_mode_state,
            device_name=self.name,
            after_update_cb=self.after_update,
        )

    @classmethod
    def from_config(cls, xknx, name, config):
        """Initialize object from configuration structure."""
        return cls(
            xknx,
            name,
            group_address_temperature=config.get("group_address_temperature"),
            group_address_target_temperature=config.get(
                "group_address_target_temperature"
            ),
            group_address_target_temperature_state=config.get(
                "group_address_target_temperature_state"
            ),
            target_temperature_step=config.get(
                "target_temperature_step", cls.DEFAULT_TARGET_TEMPERATURE_STEP
            ),
            target_temperature_max=config.get(
                "target_temperature_max", cls.DEFAULT_TARGET_TEMPERATURE_MAX
            ),
            target_temperature_min=config.get(
                "target_temperature_min", cls.DEFAULT_TARGET_TEMPERATURE_MIN
            ),
            group_address_operation_mode=config.get("group_address_operation_mode"),
            group_address_operation_mode_state=config.get(
                "group_address_operation_mode_state"
            ),
            group_address_fan_mode=config.get("group_address_fan_mode"),
            group_address_fan_mode_state=config.get("group_address_fan_mode_state"),
            group_address_on_off=config.get("group_address_on_off"),
            group_address_on_off_state=config.get("group_address_on_off_state"),
        )

    def _iter_remote_values(self):
        """Iterate the devices RemoteValue classes."""
        yield self.temperature
        yield self.target_temperature
        yield self.operation_mode
        yield self.fan_mode
        yield self.on

    def has_group_address(self, group_address):
        """Test if device has given group address."""
        return (
            self.temperature.has_group_address(group_address)
            or self.target_temperature.has_group_address(group_address)
            or self.operation_mode.has_group_address(group_address)
            or self.fan_mode.has_group_address(group_address)
            or self.on.has_group_address(group_address)
        )

    @property
    def is_on(self):
        """Return power status. RemoteValueSwitch.value is a bool in xknx 3.x."""
        return bool(self.on.value)

    async def turn_on(self):
        """Set power status to on."""
        self.on.on()

    async def turn_off(self):
        """Set power status to off."""
        self.on.off()

    async def set_target_temperature(self, target_temperature):
        """Send target temperature to KNX bus."""
        self.target_temperature.set(target_temperature)

    async def set_operation_mode(self, operation_mode):
        """Set the operation mode of a thermostat."""
        if not self.supports_operation_mode:
            raise ValueError("operation mode not supported")
        if operation_mode not in self.OPERATION_MODE_VALUE:
            raise ValueError(f"unknown operation mode {operation_mode}")
        self.operation_mode.set(self.OPERATION_MODE_VALUE[operation_mode])

    def get_supported_operation_modes(self):
        """Return all supported operation modes."""
        if not self.supports_operation_mode:
            return []
        return list(self.OPERATION_MODES)

    def get_operation_mode(self):
        """Return current operation mode."""
        if not self.supports_operation_mode:
            return None
        return self.OPERATION_MODE_FROM_VALUE.get(self.operation_mode.value, "Cool")

    async def set_fan_mode(self, fan_mode):
        """Set the fan mode of a thermostat."""
        if not self.supports_fan_mode:
            raise ValueError("fan mode not supported")
        if fan_mode not in self.FAN_MODE_VALUE:
            raise ValueError(f"unknown fan mode {fan_mode}")
        self.fan_mode.set(self.FAN_MODE_VALUE[fan_mode])

    def get_supported_fan_modes(self):
        """Return all supported fan modes."""
        if not self.supports_fan_mode:
            return []
        return list(self.FAN_MODES)

    def get_fan_mode(self):
        """Return current fan mode."""
        if not self.supports_fan_mode:
            return None
        return self.FAN_MODE_FROM_VALUE.get(self.fan_mode.value, "Auto")

    def _process_telegram(self, telegram):
        """Process incoming GROUP WRITE / GROUP RESPONSE telegram."""
        self.temperature.process(telegram)
        self.target_temperature.process(telegram)
        self.operation_mode.process(telegram)
        self.fan_mode.process(telegram)
        self.on.process(telegram)

    def process_group_write(self, telegram):
        """Process incoming GROUP WRITE telegram."""
        self._process_telegram(telegram)

    def process_group_response(self, telegram):
        """Process incoming GROUP RESPONSE telegram."""
        self._process_telegram(telegram)


    def __str__(self):
        """Return object as readable string."""
        return (
            f'<KTSClimate name="{self.name}" '
            f'temperature="{self.temperature.group_addr_str()}" '
            f'target_temperature="{self.target_temperature.group_addr_str()}" '
            f'target_temperature_step="{self.target_temperature_step}" '
            f'target_temperature_max="{self.target_temperature_max}" '
            f'target_temperature_min="{self.target_temperature_min}" '
            f'group_address_operation_mode="{self.operation_mode.group_addr_str()}" '
            f'group_address_fan_mode="{self.fan_mode.group_addr_str()}" '
            f'group_address_on_off="{self.on.group_addr_str()}" />'
        )
