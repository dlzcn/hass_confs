"""Support for KTS KNX scenes."""
import voluptuous as vol
from xknx.devices import Scene as XknxScene

from homeassistant.components.kts_knx import ATTR_DISCOVER_DEVICES, DATA_KNX
from homeassistant.components.scene import Scene
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

CONF_SCENE_NUMBER = "scene_number"

DEFAULT_NAME = "KTS KNX Scene"
PLATFORM_SCHEMA = vol.Schema(
    {
        vol.Required("platform"): "kts_knx",
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Required(CONF_ADDRESS): cv.string,
        vol.Required(CONF_SCENE_NUMBER): cv.positive_int,
    }
)


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the scenes for the KTS KNX platform."""
    if discovery_info is not None:
        entities = []
        for device_name in discovery_info[ATTR_DISCOVER_DEVICES]:
            device = hass.data[DATA_KNX].xknx.devices[device_name]
            entities.append(KNXScene(device))
        async_add_entities(entities)
        return

    scene = XknxScene(
        hass.data[DATA_KNX].xknx,
        name=config[CONF_NAME],
        group_address=config[CONF_ADDRESS],
        scene_number=config[CONF_SCENE_NUMBER],
    )
    hass.data[DATA_KNX].xknx.devices.async_add(scene)
    async_add_entities([KNXScene(scene)])


class KNXScene(Scene):
    """Representation of a KTS KNX scene."""

    _attr_should_poll = False

    def __init__(self, scene: XknxScene) -> None:
        """Init KTS KNX scene."""
        self.scene = scene
        self._attr_name = scene.name
        self._attr_unique_id = scene.name

    async def async_activate(self, **kwargs) -> None:
        """Activate the scene."""
        await self.scene.run()
