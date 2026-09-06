"""Support for KTS KNX covers."""
import voluptuous as vol

from ._kts_cover import KTSCover

from homeassistant.components.cover import (
    ATTR_POSITION,
    ATTR_TILT_POSITION,
    CoverEntity,
    CoverEntityFeature,
    PLATFORM_SCHEMA,
)
from homeassistant.components.kts_knx import DATA_KNX
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant, callback
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
import datetime as dt

CONF_MOVE_LONG_ADDRESS = "move_long_address"
CONF_MOVE_SHORT_ADDRESS = "move_short_address"
CONF_POSITION_ADDRESS = "position_address"
CONF_POSITION_STATE_ADDRESS = "position_state_address"
CONF_ANGLE_ADDRESS = "angle_address"
CONF_ANGLE_STATE_ADDRESS = "angle_state_address"
CONF_TRAVELLING_TIME_DOWN = "travelling_time_down"
CONF_TRAVELLING_TIME_UP = "travelling_time_up"
CONF_INVERT_POSITION = "invert_position"
CONF_INVERT_ANGLE = "invert_angle"

DEFAULT_TRAVEL_TIME = 25
DEFAULT_NAME = "KTS Cover"

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Optional(CONF_MOVE_LONG_ADDRESS): cv.string,
        vol.Optional(CONF_MOVE_SHORT_ADDRESS): cv.string,
        vol.Optional(CONF_POSITION_ADDRESS): cv.string,
        vol.Optional(CONF_POSITION_STATE_ADDRESS): cv.string,
        vol.Optional(CONF_ANGLE_ADDRESS): cv.string,
        vol.Optional(CONF_ANGLE_STATE_ADDRESS): cv.string,
        vol.Optional(
            CONF_TRAVELLING_TIME_DOWN, default=DEFAULT_TRAVEL_TIME
        ): cv.positive_int,
        vol.Optional(CONF_TRAVELLING_TIME_UP, default=DEFAULT_TRAVEL_TIME): cv.positive_int,
        vol.Optional(CONF_INVERT_POSITION, default=False): cv.boolean,
        vol.Optional(CONF_INVERT_ANGLE, default=False): cv.boolean,
    }
)


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up covers for the KTS KNX platform."""
    cover = KTSCover(
        hass.data[DATA_KNX].xknx,
        name=config.get(CONF_NAME),
        group_address_long=config.get(CONF_MOVE_LONG_ADDRESS),
        group_address_short=config.get(CONF_MOVE_SHORT_ADDRESS),
        group_address_position_state=config.get(CONF_POSITION_STATE_ADDRESS),
        group_address_angle=config.get(CONF_ANGLE_ADDRESS),
        group_address_angle_state=config.get(CONF_ANGLE_STATE_ADDRESS),
        group_address_position=config.get(CONF_POSITION_ADDRESS),
        travel_time_down=config.get(CONF_TRAVELLING_TIME_DOWN),
        travel_time_up=config.get(CONF_TRAVELLING_TIME_UP),
        invert_position=config.get(CONF_INVERT_POSITION),
        invert_angle=config.get(CONF_INVERT_ANGLE),
    )
    hass.data[DATA_KNX].xknx.devices.async_add(cover)
    async_add_entities([KNXCover(cover)])


class KNXCover(CoverEntity):
    """Representation of a KTS KNX cover."""

    _attr_should_poll = False

    def __init__(self, device: KTSCover) -> None:
        """Initialize the cover."""
        self.device = device
        self._attr_name = device.name
        self._attr_unique_id = device.name
        self._unsubscribe_auto_updater: callable | None = None

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

    async def async_will_remove_from_hass(self) -> None:
        """Stop auto updater when entity is removed."""
        self.stop_auto_updater()

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.hass.data[DATA_KNX].connected

    @property
    def supported_features(self) -> int:
        """Flag supported features."""
        supported_features = (
            CoverEntityFeature.OPEN
            | CoverEntityFeature.CLOSE
            | CoverEntityFeature.SET_POSITION
            | CoverEntityFeature.STOP
        )
        if self.device.supports_angle:
            supported_features |= CoverEntityFeature.SET_TILT_POSITION
        return supported_features

    @property
    def current_cover_position(self) -> int | None:
        """Return the current position of the cover."""
        return self.device.current_position()

    @property
    def is_closed(self) -> bool | None:
        """Return if the cover is closed."""
        return self.device.is_closed()

    @property
    def is_opening(self) -> bool | None:
        """Return if the cover is opening."""
        return self.device.is_opening()

    @property
    def is_closing(self) -> bool | None:
        """Return if the cover is closing."""
        return self.device.is_closing()

    async def async_close_cover(self, **kwargs) -> None:
        """Close the cover."""
        if not self.device.is_closed():
            await self.device.set_down()
            self.start_auto_updater()

    async def async_open_cover(self, **kwargs) -> None:
        """Open the cover."""
        if not self.device.is_open():
            await self.device.set_up()
            self.start_auto_updater()

    async def async_set_cover_position(self, **kwargs) -> None:
        """Move the cover to a specific position."""
        if ATTR_POSITION in kwargs:
            position = kwargs[ATTR_POSITION]
            await self.device.set_position(position)
            self.start_auto_updater()

    async def async_stop_cover(self, **kwargs) -> None:
        """Stop the cover."""
        await self.device.stop()
        self.stop_auto_updater()

    @property
    def current_cover_tilt_position(self) -> int | None:
        """Return current tilt position of cover."""
        if not self.device.supports_angle:
            return None
        return self.device.current_angle()

    async def async_set_cover_tilt_position(self, **kwargs) -> None:
        """Move the cover tilt to a specific position."""
        if ATTR_TILT_POSITION in kwargs:
            tilt_position = kwargs[ATTR_TILT_POSITION]
            await self.device.set_angle(tilt_position)

    def start_auto_updater(self) -> None:
        """Start the autoupdater to update HASS while cover is moving."""
        if self._unsubscribe_auto_updater is None:
            self._unsubscribe_auto_updater = async_track_time_interval(
                self.hass, self.auto_updater_hook, dt.timedelta(seconds=1)
            )

    def stop_auto_updater(self) -> None:
        """Stop the autoupdater."""
        if self._unsubscribe_auto_updater is not None:
            self._unsubscribe_auto_updater()
            self._unsubscribe_auto_updater = None

    @callback
    def auto_updater_hook(self, now) -> None:
        """Call for the autoupdater."""
        self.async_write_ha_state()
        if self.device.position_reached():
            self.stop_auto_updater()

        self.hass.async_create_task(self.device.auto_stop_if_necessary())
