"""Support for Xiaomi water purifier."""
import math
import logging

from datetime import timedelta, datetime
from threading import Lock
from homeassistant.const import (
    CONF_NAME, CONF_HOST, CONF_TOKEN, CONF_SCAN_INTERVAL, 
    EVENT_HOMEASSISTANT_START)
from homeassistant.helpers.entity import Entity
from homeassistant.exceptions import PlatformNotReady
from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.core import callback
import homeassistant.helpers.config_validation as cv
import voluptuous as vol

_LOGGER = logging.getLogger(__name__)

REQUIREMENTS = ['python-miio>=0.3.1']

DEFAULT_NAME = 'Xiaomi Water Purifier'
SCAN_INTERVAL = timedelta(seconds=1200)

TAP_WATER_QUALITY = {'name': 'Tap water', 'key': 'ttds'}
FILTERED_WATER_QUALITY = {'name': 'Filtered water', 'key': 'ftds'}
PP_COTTON_FILTER_REMAINING = {'name': 'PP cotton filter', 'key': 'pfd', 'days_key': 'pfp'}
FRONT_ACTIVE_CARBON_FILTER_REMAINING = {'name': 'Front active carbon filter', 'key': 'fcfd', 'days_key': 'fcfp'}
RO_FILTER_REMAINING = {'name': 'RO filter', 'key': 'rfd', 'days_key': 'rfp'}
REAR_ACTIVE_CARBON_FILTER_REMAINING = {'name': 'Rear active carbon filter', 'key': 'rcfd', 'days_key': 'rcfp'}

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_HOST): cv.string,
    vol.Required(CONF_TOKEN): cv.string,
    vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
    # FIXME: bug in voluptuous?
    # expected int for dictionary value @ data['scan_interval']. Got datetime.timedelta(0, 10)
    #vol.Optional(CONF_SCAN_INTERVAL, default=DEFAUTT_SCAN_INTERVAL): cv.positive_timedelta,
})

async def async_setup_platform(hass, config, async_add_entities,
                               discovery_info=None):
    """Perform the setup for Xiaomi water purifier."""
    from miio import Device, DeviceException    
    
    host = config.get(CONF_HOST)
    # name = config.get(CONF_NAME) <-- to be treated as prefix of following sensors
    token = config.get(CONF_TOKEN)
    cache = config.get(CONF_SCAN_INTERVAL, SCAN_INTERVAL).total_seconds()

    _LOGGER.info("Initializing Xiaomi Water Purifier with host %s (token %s...)", host, token[:5])

    devs = []
    try:
        device = Device(host, token)
        waterPurifier = XiaomiWaterPurifier(device, cache)

        devs.append(XiaomiWaterPurifierSensor(waterPurifier, TAP_WATER_QUALITY))
        devs.append(XiaomiWaterPurifierSensor(waterPurifier, FILTERED_WATER_QUALITY))
        devs.append(XiaomiWaterPurifierSensor(waterPurifier, PP_COTTON_FILTER_REMAINING))
        devs.append(XiaomiWaterPurifierSensor(waterPurifier, FRONT_ACTIVE_CARBON_FILTER_REMAINING))
        devs.append(XiaomiWaterPurifierSensor(waterPurifier, RO_FILTER_REMAINING))
        devs.append(XiaomiWaterPurifierSensor(waterPurifier, REAR_ACTIVE_CARBON_FILTER_REMAINING))
    except DeviceException:
        _LOGGER.exception('Fail to setup Xiaomi water purifier')
        raise PlatformNotReady

    async_add_entities(devs)


class XiaomiWaterPurifierSensor(Entity):
    """Representation of a XiaomiWaterPurifierSensor."""

    def __init__(self, waterPurifier, data_key):
        """Initialize the XiaomiWaterPurifierSensor."""
        self._state = None
        self._attrs = {}
        self._waterPurifier = waterPurifier
        self._data_key = data_key

    async def async_added_to_hass(self):
        """Set initial state."""
        @callback
        def on_startup(_):
            self.async_schedule_update_ha_state(True)

        self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_START, on_startup)

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._data_key['name']

    @property
    def icon(self):
        """Icon to use in the frontend, if any."""
        if self._data_key['key'] is TAP_WATER_QUALITY['key'] or \
           self._data_key['key'] is FILTERED_WATER_QUALITY['key']:
            return 'mdi:water'
        else:
            return 'mdi:filter-outline'

    @property
    def state(self):
        """Return the state of the device."""
        return self._state

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement of this entity, if any."""
        if self._data_key['key'] is TAP_WATER_QUALITY['key'] or \
           self._data_key['key'] is FILTERED_WATER_QUALITY['key']:
            return 'TDS'
        return '%'

    @property
    def device_state_attributes(self):
        """Return the state attributes of the device."""
        return self._attrs

    def update(self):
        """Get the latest data and updates the states."""
        data = self._waterPurifier.read()
        self._attrs = {}
        self._state = None
        if data:
            self._state = data[self._data_key['key']]
            if 'days_key' in self._data_key:
                self._attrs[self._data_key['name']] = \
                    '{} days remaining'.format(data[self._data_key['days_key']])


class XiaomiWaterPurifier():
    """Representation of a XiaomiWaterPurifier."""

    def __init__(self, device, cache_timeout):
        """Initialize the XiaomiWaterPurifier."""
        self._device = device
        self._cache = {}
        self._cache_timeout = timedelta(seconds=cache_timeout)
        self._last_read = None
        self.lock = Lock()
        self.parse_data()

    def parse_data(self):
        """Parse data."""
        from miio import DeviceException
        if not self._cache or \
            (datetime.now() - self._cache_timeout > self._last_read):
            try:
                data = {}
                last_read = datetime.now()
                status = self._device.send('get_prop', [])
                data[TAP_WATER_QUALITY['key']] = status[0]
                data[FILTERED_WATER_QUALITY['key']] = status[1]
                pfd = int((status[11] - status[3]) / 24)
                data[PP_COTTON_FILTER_REMAINING['days_key']] = pfd
                data[PP_COTTON_FILTER_REMAINING['key']] = math.floor(pfd * 24 * 100 / status[11])
                fcfd = int((status[13] - status[5]) / 24)
                data[FRONT_ACTIVE_CARBON_FILTER_REMAINING['days_key']] = fcfd
                data[FRONT_ACTIVE_CARBON_FILTER_REMAINING['key']] = math.floor(fcfd * 24 * 100 / status[13])
                rfd = int((status[15] - status[7]) / 24)
                data[RO_FILTER_REMAINING['days_key']] = rfd
                data[RO_FILTER_REMAINING['key']] = math.floor(rfd * 24 * 100 / status[15])
                rcfd = int((status[17] - status[9]) / 24)
                data[REAR_ACTIVE_CARBON_FILTER_REMAINING['days_key']] = rcfd
                data[REAR_ACTIVE_CARBON_FILTER_REMAINING['key']] = math.floor(rcfd * 24 * 100 / status[17])

                self._last_read = last_read
                self._cache = data
            except DeviceException:
                _LOGGER.exception('Fail to get_prop from Xiaomi water purifier')
                self._cache = None

    def read(self):
        """Get the latest data and updates the states."""
        with self.lock:
            self.parse_data()
            return self._cache
