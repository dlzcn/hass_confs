"""Support KTS KNX devices.

Migrated from the legacy custom_components/knx integration (HA ~0.9x,
xknx 0.11) to the modern Home Assistant integration layout (HA 2024+,
xknx 3.x).

The domain was renamed to ``kts_knx`` so it can coexist with the
built-in ``knx`` integration (which is now config-flow based and takes
over the ``knx`` domain).

Device definitions are still read from the old xknx.yaml file
(``config_file`` option); climate and cover entities are still
configured as YAML platform entries under ``climate:`` / ``cover:``.
"""
import logging

import voluptuous as vol
from xknx import XKNX
from xknx.devices import (
    BinarySensor as XknxBinarySensor,
    Light as XknxLight,
    Notification as XknxNotification,
    Scene as XknxScene,
    Sensor as XknxSensor,
    Switch as XknxSwitch,
)
from xknx.dpt import DPTArray, DPTBinary
from xknx.exceptions import XKNXException
from xknx.io import ConnectionConfig, ConnectionType
from xknx.telegram import AddressFilter, GroupAddress, Telegram
from xknx.telegram.apci import GroupValueWrite

from homeassistant.const import (
    CONF_ENTITY_ID,
    CONF_HOST,
    CONF_PORT,
    EVENT_HOMEASSISTANT_STOP,
)
from homeassistant.core import Event, HomeAssistant, ServiceCall, callback
from homeassistant.helpers import discovery
import homeassistant.helpers.config_validation as cv

_LOGGER = logging.getLogger(__name__)

DOMAIN = "kts_knx"
DATA_KNX = "kts_knx"

CONF_KNX_CONFIG = "config_file"
CONF_KNX_ROUTING = "routing"
CONF_KNX_TUNNELING = "tunneling"
CONF_KNX_LOCAL_IP = "local_ip"
CONF_KNX_FIRE_EVENT = "fire_event"
CONF_KNX_FIRE_EVENT_FILTER = "fire_event_filter"
CONF_KNX_STATE_UPDATER = "state_updater"
CONF_KNX_RATE_LIMIT = "rate_limit"
CONF_KNX_INDIVIDUAL_ADDRESS = "own_address"

SERVICE_KNX_SEND = "send"
SERVICE_KNX_ATTR_ADDRESS = "address"
SERVICE_KNX_ATTR_PAYLOAD = "payload"

ATTR_DISCOVER_DEVICES = "devices"

TUNNELING_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): cv.string,
        vol.Optional(CONF_KNX_LOCAL_IP): cv.string,
        vol.Optional(CONF_PORT, default=3671): cv.port,
    }
)

ROUTING_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_KNX_LOCAL_IP): cv.string,
    }
)

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Optional(CONF_KNX_CONFIG): cv.string,
                vol.Exclusive(CONF_KNX_ROUTING, "connection_type"): ROUTING_SCHEMA,
                vol.Exclusive(CONF_KNX_TUNNELING, "connection_type"): TUNNELING_SCHEMA,
                vol.Inclusive(CONF_KNX_FIRE_EVENT, "fire_ev"): cv.boolean,
                vol.Inclusive(CONF_KNX_FIRE_EVENT_FILTER, "fire_ev"): vol.All(
                    cv.ensure_list, [cv.string]
                ),
                vol.Optional(CONF_KNX_STATE_UPDATER, default=True): cv.boolean,
                vol.Optional(CONF_KNX_RATE_LIMIT, default=20): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=100)
                ),
                vol.Optional(CONF_KNX_INDIVIDUAL_ADDRESS): cv.string,
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)

SERVICE_KNX_SEND_SCHEMA = vol.Schema(
    {
        vol.Required(SERVICE_KNX_ATTR_ADDRESS): cv.string,
        vol.Required(SERVICE_KNX_ATTR_PAYLOAD): vol.Any(
            cv.positive_int, [cv.positive_int]
        ),
    }
)

PLATFORMS = (
    "switch",
    "climate",
    "cover",
    "light",
    "sensor",
    "binary_sensor",
    "scene",
    "notify",
)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the KTS KNX component."""
    try:
        module = KNXModule(hass, config)
        hass.data[DATA_KNX] = module
        await module.load_yaml_devices()
        await module.start()
    except XKNXException as ex:
        _LOGGER.warning("Can't connect to KNX interface: %s", ex)
        hass.components.persistent_notification.async_create(
            f"Can't connect to KNX interface: <br><b>{ex}</b>", title="KTS KNX"
        )

    module = hass.data[DATA_KNX]

    for component in PLATFORMS:
        found_devices = module.devices_for_component(component)
        if not found_devices:
            continue
        hass.async_create_task(
            discovery.async_load_platform(
                hass,
                component,
                DOMAIN,
                {ATTR_DISCOVER_DEVICES: found_devices},
                config,
            )
        )

    hass.services.async_register(
        DOMAIN,
        SERVICE_KNX_SEND,
        module.service_send_to_knx_bus,
        schema=SERVICE_KNX_SEND_SCHEMA,
    )

    return True


class KNXModule:
    """Representation of the KTS KNX module."""

    def __init__(self, hass: HomeAssistant, config: dict) -> None:
        """Initialize of KNX module."""
        self.hass = hass
        self.config = config[DOMAIN]
        self.connected = False
        self.device_configs: dict[str, dict] = {}
        self.init_xknx()
        self.register_callbacks()

    def init_xknx(self) -> None:
        """Initialize XKNX object."""
        self.xknx = XKNX(
            rate_limit=self.config[CONF_KNX_RATE_LIMIT],
            state_updater=self.config[CONF_KNX_STATE_UPDATER],
            connection_config=self.connection_config(),
        )

    async def start(self) -> None:
        """Start XKNX. Connect to tunneling or routing interface."""

        async def async_stop(event: Event) -> None:
            await self.xknx.stop()

        await self.xknx.start()
        self.config_stop_listener = self.hass.bus.async_listen_once(
            EVENT_HOMEASSISTANT_STOP, async_stop
        )
        self.connected = True

    def connection_config(self) -> ConnectionConfig:
        """Return the connection_config."""
        if CONF_KNX_TUNNELING in self.config:
            tunneling = self.config[CONF_KNX_TUNNELING]
            return ConnectionConfig(
                connection_type=ConnectionType.TUNNELING,
                gateway_ip=tunneling[CONF_HOST],
                gateway_port=tunneling[CONF_PORT],
                local_ip=tunneling.get(CONF_KNX_LOCAL_IP),
            )
        if CONF_KNX_ROUTING in self.config:
            return ConnectionConfig(
                connection_type=ConnectionType.ROUTING,
                local_ip=self.config[CONF_KNX_ROUTING][CONF_KNX_LOCAL_IP],
            )
        return ConnectionConfig(
            individual_address=self.config.get(CONF_KNX_INDIVIDUAL_ADDRESS)
        )

    def register_callbacks(self) -> None:
        """Register callbacks within XKNX object."""
        if self.config.get(CONF_KNX_FIRE_EVENT):
            address_filters = [
                AddressFilter(addr)
                for addr in self.config.get(CONF_KNX_FIRE_EVENT_FILTER, [])
            ]
            self.xknx.telegram_queue.register_telegram_received_cb(
                self.telegram_received_cb, address_filters
            )

    async def telegram_received_cb(self, telegram):
        """Call invoked after a KNX telegram was received."""
        self.hass.bus.async_fire(
            "kts_knx_event",
            {
                "address": str(telegram.destination_address),
                "data": str(telegram.payload.value),
            },
        )
        # False signals XKNX to proceed with processing telegrams.
        return False

    def config_file(self):
        """Resolve and return the full path of xknx.yaml if configured."""
        config_file = self.config.get(CONF_KNX_CONFIG)
        if not config_file:
            return None
        if not config_file.startswith("/"):
            return self.hass.config.path(config_file)
        return config_file

    async def load_yaml_devices(self) -> None:
        """Load devices from the legacy xknx.yaml file.

        climate and cover devices are non-standard KTS devices; they are
        created by their platform files instead and are not loaded here.
        """
        import yaml

        config_file = self.config_file()
        if not config_file:
            return
        with open(config_file, encoding="utf-8") as file_handle:
            conf = yaml.safe_load(file_handle) or {}

        groups = conf.get("groups", {})
        xknx = self.xknx

        for name, cfg in (groups.get("light") or {}).items():
            device = XknxLight(
                xknx,
                name=name,
                group_address_switch=cfg.get("group_address_switch"),
                group_address_switch_state=cfg.get("group_address_switch_state"),
                group_address_brightness=cfg.get("group_address_brightness"),
                group_address_brightness_state=cfg.get(
                    "group_address_brightness_state"
                ),
                min_kelvin=cfg.get("min_kelvin"),
                max_kelvin=cfg.get("max_kelvin"),
            )
            xknx.devices.async_add(device)

        for name, cfg in (groups.get("switch") or {}).items():
            device = XknxSwitch(
                xknx,
                name=name,
                group_address=cfg.get("group_address"),
                group_address_state=cfg.get("group_address_state"),
            )
            xknx.devices.async_add(device)

        for name, cfg in (groups.get("scene") or {}).items():
            device = XknxScene(
                xknx,
                name=name,
                group_address=cfg.get("group_address"),
                scene_number=cfg.get("scene_number", 1),
            )
            xknx.devices.async_add(device)

        for name, cfg in (groups.get("binary_sensor") or {}).items():
            self.device_configs[name] = cfg
            # note: device_class is no longer an xknx BinarySensor
            # parameter; the HA entity picks it up from device_configs
            device = XknxBinarySensor(
                xknx,
                name=name,
                group_address_state=cfg.get("group_address_state"),
                sync_state=cfg.get("sync_state", True),
                reset_after=cfg.get("reset_after"),
            )
            xknx.devices.async_add(device)

        for name, cfg in (groups.get("sensor") or {}).items():
            device = XknxSensor(
                xknx,
                name=name,
                group_address_state=cfg.get("group_address_state"),
                sync_state=cfg.get("sync_state", True),
                value_type=cfg.get("value_type"),
            )
            xknx.devices.async_add(device)

        for name, cfg in (groups.get("notify") or {}).items():
            device = XknxNotification(
                xknx,
                name=name,
                group_address=cfg.get("group_address"),
            )
            xknx.devices.async_add(device)

    def devices_for_component(self, component: str) -> list[str]:
        """Get device names of the devices matching the platform type."""
        # climate and cover are set up via their own YAML platforms
        # (`climate: - platform: kts_knx`) because they are custom
        # KTS device classes, not stock xknx devices.
        type_map = {
            "switch": XknxSwitch,
            "light": XknxLight,
            "sensor": XknxSensor,
            "binary_sensor": XknxBinarySensor,
            "scene": XknxScene,
            "notify": XknxNotification,
        }
        device_type = type_map.get(component)
        if device_type is None:
            return []
        return [
            device.name
            for device in self.xknx.devices
            if isinstance(device, device_type)
        ]

    async def service_send_to_knx_bus(self, call: ServiceCall) -> None:
        """Service for sending an arbitrary KNX message to the KNX bus."""
        attr_payload = call.data.get(SERVICE_KNX_ATTR_PAYLOAD)
        attr_address = call.data.get(SERVICE_KNX_ATTR_ADDRESS)

        if isinstance(attr_payload, int):
            payload = DPTBinary(attr_payload)
        else:
            payload = DPTArray(attr_payload)
        telegram = Telegram(
            destination_address=GroupAddress(attr_address),
            payload=GroupValueWrite(payload),
        )
        await self.xknx.telegrams.put(telegram)
