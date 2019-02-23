"""
Module for managing the climate within a room.
* It reads/listens to a temperature address from KNX bus.
* Manages and sends the desired setpoint to KNX bus.

Modified by Haifeng for KTS smart solution in Guohao Changfeng Residence
 - Air conditioner: temperature, target_temperature, operation_mode, fan_mode, on_off
 - Floor heating: temperature, target_temperature, on_off
"""
from xknx.exceptions import CouldNotParseTelegram, DeviceIllegalValue
from xknx.knx import GroupAddress

from xknx.devices.device import Device
from xknx.devices.remote_value_temp import RemoteValueTemp
from xknx.devices.remote_value_1count import RemoteValue1Count
from xknx.devices.remote_value_switch import RemoteValueSwitch


class KTSClimate(Device):
    """Class for managing the climate."""

    # pylint: disable=too-many-instance-attributes,invalid-name
    DEFAULT_TARGET_TEMPERATURE_STEP = 0.5
    DEFAULT_TARGET_TEMPERATURE_MAX = 35
    DEFAULT_TARGET_TEMPERATURE_MIN = 5

    def __init__(self,
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
                 device_updated_cb=None):
        """Initialize Climate class."""
        # pylint: disable=too-many-arguments, too-many-locals, too-many-branches, too-many-statements
        super(KTSClimate, self).__init__(xknx, name, device_updated_cb)

        self.temperature = RemoteValueTemp(
            xknx,
            group_address_state=group_address_temperature,
            device_name=self.name,
            after_update_cb=self.after_update)
        
        self.target_temperature = RemoteValueTemp(
            xknx,
            group_address_target_temperature,
            group_address_target_temperature_state,
            device_name=self.name,
            after_update_cb=self.after_update)

        self.target_temperature_step = target_temperature_step
        self.target_temperature_max = target_temperature_max
        self.target_temperature_min = target_temperature_min

        self.supports_on_off = group_address_on_off is not None or \
                group_address_on_off_state is not None

        self.on = RemoteValueSwitch(
            xknx,
            group_address_on_off,
            group_address_on_off_state,
            self.name,
            self.after_update)            

        self.supports_operation_mode = \
            group_address_operation_mode is not None or \
            group_address_operation_mode_state is not None

        self.operation_mode = RemoteValue1Count(
            xknx,
            group_address_operation_mode,
            group_address_operation_mode_state,
            device_name=self.name,
            after_update_cb=self.after_update)
        
        self.supports_fan_mode = \
            group_address_fan_mode is not None or \
            group_address_fan_mode_state is not None

        self.fan_mode = RemoteValue1Count(
            xknx,
            group_address_fan_mode,
            group_address_fan_mode_state,
            device_name=self.name,
            after_update_cb=self.after_update)


    @classmethod
    def from_config(cls, xknx, name, config):
        """Initialize object from configuration structure."""
        # pylint: disable=too-many-locals
        group_address_temperature = \
            config.get('group_address_temperature')
        group_address_target_temperature = \
            config.get('group_address_target_temperature')
        group_address_target_temperature_state = \
            config.get('group_address_target_temperature_state')
        target_temperature_step = config.get('target_temperature_step')
        target_temperature_max = config.get('target_temperature_max')
        target_temperature_min = config.get('target_temperature_min')
        group_address_operation_mode = \
            config.get('group_address_operation_mode')
        group_address_operation_mode_state = \
            config.get('group_address_operation_mode_state')
        group_address_fan_mode = \
            config.get('group_address_fan_mode')
        group_address_fan_mode_state = \
            config.get('group_address_fan_mode_state')
        group_address_on_off = \
            config.get('group_address_on_off')
        group_address_on_off_state = \
            config.get('group_address_on_off_state')

        return cls(xknx,
                   name,
                   group_address_temperature=group_address_temperature,
                   group_address_target_temperature=group_address_target_temperature,
                   group_address_target_temperature_state=group_address_target_temperature_state,
                   target_temperature_step=target_temperature_step,
                   target_temperature_max=target_temperature_max,
                   target_temperature_min=target_temperature_min,
                   group_address_operation_mode=group_address_operation_mode,
                   group_address_operation_mode_state=group_address_operation_mode_state,
                   group_address_fan_mode=group_address_fan_mode,
                   group_address_fan_mode_state=group_address_fan_mode_state,
                   group_address_on_off=group_address_on_off,
                   group_address_on_off_state=group_address_on_off_state)

    def has_group_address(self, group_address):
        """Test if device has given group address."""
        return self.temperature.has_group_address(group_address) or \
            self.target_temperature.has_group_address(group_address) or \
            self.operation_mode.has_group_address(group_address) or \
            self.fan_mode.has_group_address(group_address) or \
            self.on.has_group_address(group_address)
       
    @property
    def is_on(self):
        """Return power status."""
        return bool(self.on.value and self.on.value.value == 1)

    async def turn_on(self):
        """Set power status to on."""
        await self.on.on()

    async def turn_off(self):
        """Set power status to off."""
        await self.on.off()

    async def set_target_temperature(self, target_temperature):
        """Send target temperature to  KNX bus."""
        # send/broadcast new target temperature and set internally
        await self.target_temperature.set(target_temperature)

    async def set_operation_mode(self, operation_mode):
        """Set the operation mode of a thermostat. Send new operation_mode to BUS and update internal state."""
        if not self.supports_operation_mode:
            raise DeviceIllegalValue("operation mode not supported", operation_mode)

        if operation_mode == 'Cool':
            await self.operation_mode.set(1)
        if operation_mode == 'Heat':
            await self.operation_mode.set(4)
        if operation_mode == 'Fan':
            await self.operation_mode.set(3)
        if operation_mode == 'Dry':
            await self.operation_mode.set(2)            
        # if operation_mode == 'Auto':
        #     await self.operation_mode.set(-1)

    def get_supported_operation_modes(self):
        """Return all configured operation modes."""
        if not self.supports_operation_mode:
            return []
        else:
            return ['Cool', 'Heat', 'Fan', 'Dry']

    def get_operation_mode(self):
        """Return current operation mode."""
        if not self.supports_operation_mode:
            return None
        else:
            val = self.operation_mode.value
            if val == 1:
                return 'Cool'
            if val == 4:
                return 'Heat'
            if val == 3:
                return 'Fan'
            if val == 2:
                return 'Dry'
            # if val == -1:
            #     return 'Auto'
            return 'Cool'

    async def set_fan_mode(self, fan_mode):
        """Set the fan mode of a thermostat. Send new fan_mode to BUS and update internal state."""
        if not self.supports_fan_mode:
            raise DeviceIllegalValue("fan mode not supported", fan_mode)

        if fan_mode == 'Low':
            await self.fan_mode.set(1)
        if fan_mode == 'Medium':
            await self.fan_mode.set(2)
        if fan_mode == 'High':
            await self.fan_mode.set(3)            
        if fan_mode == 'Auto':
            await self.fan_mode.set(4)

    def get_supported_fan_modes(self):
        """Return all configured fan modes."""
        if not self.supports_fan_mode:
            return []
        else:
            return ['Low', 'Medium', 'High', 'Auto']

    def get_fan_mode(self):
        if not self.supports_fan_mode:
            return None
        else:
            val = self.fan_mode.value
            if val == 1:
                return 'Low'
            if val == 2:
                return 'Medium'
            if val == 3:
                return 'High'
            if val == 4:
                return 'Auto'
            return 'Auto'

    async def process_group_write(self, telegram):
        """Process incoming GROUP WRITE telegram."""
        await self.temperature.process(telegram)
        await self.target_temperature.process(telegram)
        await self.operation_mode.process(telegram)
        await self.fan_mode.process(telegram)
        await self.on.process(telegram)

    def state_addresses(self):
        """Return group addresses which should be requested to sync state."""
        state_addresses = []
        state_addresses.extend(self.temperature.state_addresses())
        state_addresses.extend(self.target_temperature.state_addresses())
        state_addresses.extend(self.on.state_addresses())
        if self.supports_operation_mode:
            state_addresses.extend(self.operation_mode.state_addresses())
        if self.supports_fan_mode:
            state_addresses.extend(self.fan_mode.state_addresses())
            # Note: telegrams setting splitted up operation modes are not yet implemented
        return state_addresses

    def __str__(self):
        """Return object as readable string."""
        return '<KTS Climate name="{0}" ' \
            'temperature="{1}"  ' \
            'target_temperature="{2}"  ' \
            'target_temperature_step="{3}" ' \
            'target_temperature_max="{4}" '\
            'target_temperature_min="{5}" '\
            'group_address_operation_mode="{6}" ' \
            'group_address_fan_mode="{7}" ' \
            'group_address_on_off="{8}" ' \
            '/>' \
            .format(
                self.name,
                self.temperature.group_addr_str(),
                self.target_temperature.group_addr_str(),
                self.target_temperature_step,
                self.target_temperature_max,
                self.target_temperature_min,
                self.operation_mode.group_addr_str(),
                self.fan_mode.group_addr_str(),
                self.on.group_addr_str())

    def __eq__(self, other):
        """Equal operator."""
        return self.__dict__ == other.__dict__
