"""Support for KTS KNX notification services."""
import voluptuous as vol
from xknx.devices import Notification as XknxNotification

from homeassistant.components.kts_knx import ATTR_DISCOVER_DEVICES, DATA_KNX
from homeassistant.components.notify import (
    BaseNotificationService,
    PLATFORM_SCHEMA,
)
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

DEFAULT_NAME = "KTS KNX Notify"

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_ADDRESS): cv.string,
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
    }
)


async def async_get_service(
    hass: HomeAssistant,
    config: ConfigType,
    discovery_info: DiscoveryInfoType | None = None,
):
    """Get the KTS KNX notification service."""
    if discovery_info is not None:
        notification_devices = []
        for device_name in discovery_info[ATTR_DISCOVER_DEVICES]:
            device = hass.data[DATA_KNX].xknx.devices[device_name]
            notification_devices.append(device)
        return (
            KNXNotificationService(notification_devices)
            if notification_devices
            else None
        )

    notification = XknxNotification(
        hass.data[DATA_KNX].xknx,
        name=config[CONF_NAME],
        group_address=config[CONF_ADDRESS],
    )
    hass.data[DATA_KNX].xknx.devices.async_add(notification)
    return KNXNotificationService([notification])


class KNXNotificationService(BaseNotificationService):
    """Implement KTS KNX notification service."""

    def __init__(self, devices) -> None:
        """Initialize the service."""
        self.devices = devices

    @property
    def targets(self) -> dict:
        """Return a dictionary of registered targets."""
        return {device.name: device.name for device in self.devices}

    async def async_send_message(self, message: str = "", **kwargs) -> None:
        """Send a notification to knx bus."""
        if "target" in kwargs:
            await self._async_send_to_device(message, kwargs["target"])
        else:
            await self._async_send_to_all_devices(message)

    async def _async_send_to_all_devices(self, message: str) -> None:
        """Send a notification to knx bus to all connected devices."""
        for device in self.devices:
            await device.set(message)

    async def _async_send_to_device(self, message: str, names) -> None:
        """Send a notification to knx bus to device with given names."""
        for device in self.devices:
            if device.name in names:
                await device.set(message)
