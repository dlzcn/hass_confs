"""
Module for managing a cover via KNX for KTS smart solution
in Guohao Changfeng Residence.

Ported from the legacy custom_components/knx/_kts_cover.py (xknx 0.11 era)
to xknx 3.x.

Non-standard behaviours kept from the original implementation:

* position state is fed back on the same group address as the long
  move address using DPT 1.00x (1 bit). Incoming 1-bit telegrams are
  converted to a DPT 5.001 byte (0 -> 0, 1 -> 255) before the position
  remote value processes them.
* no direct positioning group address: position is predicted with the
  TravelCalculator and the cover is auto-stopped when the target
  position is reached.
"""
from xknx.devices import Device
from xknx.devices.travelcalculator import TravelCalculator
from xknx.remote_value import (
    RemoteValueScaling,
    RemoteValueStep,
    RemoteValueUpDown,
)
from xknx.telegram.apci import GroupValueResponse, GroupValueWrite
from xknx.dpt import DPTArray, DPTBinary


class KTSCover(Device):
    """Class for managing a KTS cover."""

    DEFAULT_TRAVEL_TIME_DOWN = 22
    DEFAULT_TRAVEL_TIME_UP = 22

    def __init__(
        self,
        xknx,
        name,
        group_address_long=None,
        group_address_short=None,
        group_address_position=None,
        group_address_position_state=None,
        group_address_angle=None,
        group_address_angle_state=None,
        travel_time_down=DEFAULT_TRAVEL_TIME_DOWN,
        travel_time_up=DEFAULT_TRAVEL_TIME_UP,
        invert_position=False,
        invert_angle=False,
        device_updated_cb=None,
    ):
        """Initialize Cover class."""
        super().__init__(xknx, name, device_updated_cb)

        self.updown = RemoteValueUpDown(
            xknx,
            group_address=group_address_long,
            device_name=self.name,
            after_update_cb=self.after_update,
            invert=invert_position,
        )

        self.step = RemoteValueStep(
            xknx,
            group_address_short,
            device_name=self.name,
            after_update_cb=self.after_update,
            invert=invert_position,
        )

        position_range_from = 0 if invert_position else 100
        position_range_to = 100 if invert_position else 0
        self.position = RemoteValueScaling(
            xknx,
            group_address_position,
            group_address_position_state,
            device_name=self.name,
            after_update_cb=self.after_update,
            range_from=position_range_from,
            range_to=position_range_to,
        )

        angle_range_from = 0 if invert_angle else 100
        angle_range_to = 100 if invert_angle else 0
        self.angle = RemoteValueScaling(
            xknx,
            group_address_angle,
            group_address_angle_state,
            device_name=self.name,
            after_update_cb=self.after_update,
            range_from=angle_range_from,
            range_to=angle_range_to,
        )

        self.travel_time_down = travel_time_down
        self.travel_time_up = travel_time_up

        self.travelcalculator = TravelCalculator(travel_time_down, travel_time_up)

    @classmethod
    def from_config(cls, xknx, name, config):
        """Initialize object from configuration structure."""
        return cls(
            xknx,
            name,
            group_address_long=config.get("group_address_long"),
            group_address_short=config.get("group_address_short"),
            group_address_position=config.get("group_address_position"),
            group_address_position_state=config.get("group_address_position_state"),
            group_address_angle=config.get("group_address_angle"),
            group_address_angle_state=config.get("group_address_angle_state"),
            travel_time_down=config.get(
                "travel_time_down", cls.DEFAULT_TRAVEL_TIME_DOWN
            ),
            travel_time_up=config.get("travel_time_up", cls.DEFAULT_TRAVEL_TIME_UP),
            invert_position=config.get("invert_position", False),
            invert_angle=config.get("invert_angle", False),
        )

    def _iter_remote_values(self):
        """Iterate the devices RemoteValue classes."""
        yield self.updown
        yield self.step
        yield self.position
        yield self.angle

    def has_group_address(self, group_address):
        """Test if device has given group address."""
        return (
            self.updown.has_group_address(group_address)
            or self.step.has_group_address(group_address)
            or self.position.has_group_address(group_address)
            or self.angle.has_group_address(group_address)
        )

    def __str__(self):
        """Return object as readable string."""
        return (
            f'<KTSCover name="{self.name}" '
            f'updown="{self.updown.group_addr_str()}" '
            f'step="{self.step.group_addr_str()}" '
            f'position="{self.position.group_addr_str()}" '
            f'angle="{self.angle.group_addr_str()}" '
            f'travel_time_down="{self.travel_time_down}" '
            f'travel_time_up="{self.travel_time_up}" />'
        )

    async def set_down(self):
        """Move cover down."""
        self.updown.down()
        self.travelcalculator.start_travel_down()

    async def set_up(self):
        """Move cover up."""
        self.updown.up()
        self.travelcalculator.start_travel_up()

    async def set_short_down(self):
        """Move cover short down."""
        self.step.increase()

    async def set_short_up(self):
        """Move cover short up."""
        self.step.decrease()

    async def stop(self):
        """Stop cover. The KNX way: send a step command."""
        self.step.increase()
        self.travelcalculator.stop()

    async def set_position(self, position):
        """Move cover to a designated position."""
        if not self.position.group_address:
            # No direct positioning group address defined
            current_position = self.current_position()
            if position < current_position:
                self.updown.down()
            elif position > current_position:
                self.updown.up()
            self.travelcalculator.start_travel(position)
            return

        self.position.set(position)
        self.travelcalculator.start_travel(position)

    async def set_angle(self, angle):
        """Move cover to designated angle."""
        if not self.supports_angle:
            self.xknx.logger.warning(
                "Angle not supported for device %s", self.get_name()
            )
            return
        self.angle.set(angle)
        self.after_update()

    async def auto_stop_if_necessary(self):
        """Do auto stop if necessary."""
        if (
            not self.position.group_address
            and self.position_reached()
            and not self.is_open()
            and not self.is_closed()
        ):
            await self.stop()

    async def do(self, action):
        """Execute 'do' commands."""
        if action == "up":
            await self.set_up()
        elif action == "short_up":
            await self.set_short_up()
        elif action == "down":
            await self.set_down()
        elif action == "short_down":
            await self.set_short_down()
        else:
            self.xknx.logger.warning(
                "Could not understand action %s for device %s",
                action,
                self.get_name(),
            )


    @staticmethod
    def _convert_dpt1_position_payload(telegram):
        """Convert incoming DPT 1.00x payloads to DPT 5.001 bytes.

        The KTS curtain reports its position as a 1-bit value (0 = open,
        1 = closed) on the position state address. RemoteValueScaling
        expects a 1-byte DPT 5.001 payload, so rewrite 1 -> 255, 0 -> 0.
        """
        payload = telegram.payload
        raw = payload.value
        if isinstance(raw, DPTBinary):
            # 1-bit payload: raw.value is 0 or 1
            converted = DPTArray(255 if raw.value == 1 else 0)
            if isinstance(payload, GroupValueResponse):
                telegram.payload = GroupValueResponse(converted)
            else:
                telegram.payload = GroupValueWrite(converted)

    def process_group_write(self, telegram):
        """Process incoming GROUP WRITE telegram."""
        self._convert_dpt1_position_payload(telegram)
        position_processed = self.position.process(telegram)
        if position_processed:
            self.travelcalculator.set_position(self.position.value)
            self.after_update()
        self.angle.process(telegram)

    def process_group_response(self, telegram):
        """Process incoming GROUP RESPONSE telegram."""
        self._convert_dpt1_position_payload(telegram)
        position_processed = self.position.process(telegram)
        if position_processed:
            self.travelcalculator.set_position(self.position.value)
            self.after_update()
        self.angle.process(telegram)

    def current_position(self):
        """Return current position of cover."""
        return self.travelcalculator.current_position()

    def current_angle(self):
        """Return current tilt angle of cover."""
        return self.angle.value

    def is_traveling(self):
        """Return if cover is traveling at the moment."""
        return self.travelcalculator.is_traveling()

    def is_opening(self):
        """Return if the cover is opening."""
        return self.travelcalculator.is_opening()

    def is_closing(self):
        """Return if the cover is closing."""
        return self.travelcalculator.is_closing()

    def position_reached(self):
        """Return if cover has reached its final position."""
        return self.travelcalculator.position_reached()

    def is_open(self):
        """Return if cover is open."""
        return self.travelcalculator.is_open()

    def is_closed(self):
        """Return if cover is closed."""
        return self.travelcalculator.is_closed()

    @property
    def supports_position(self):
        """Return if cover supports direct positioning."""
        return self.position.initialized

    @property
    def supports_angle(self):
        """Return if cover supports tilt angle."""
        return self.angle.initialized
