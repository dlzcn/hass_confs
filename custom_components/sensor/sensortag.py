"""
Support for TI SensorTag (CC2650) via bluepy

Example
  - platform: sensortag
    name: storage_room
    mac: xx:xx:xx:xx:xx:xx
    scan_interval: 10
    monitored_conditions:
      - temperature
      - illuminance
      - humidity
      - pressure
      - battery
"""
from datetime import timedelta, datetime
import logging
import voluptuous as vol

from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.helpers.entity import Entity
import homeassistant.helpers.config_validation as cv
from homeassistant.const import (
    CONF_FORCE_UPDATE, CONF_MONITORED_CONDITIONS, CONF_NAME, CONF_MAC,
    CONF_SCAN_INTERVAL, EVENT_HOMEASSISTANT_START,
    DEVICE_CLASS_HUMIDITY, DEVICE_CLASS_ILLUMINANCE, DEVICE_CLASS_TEMPERATURE,
    DEVICE_CLASS_PRESSURE, DEVICE_CLASS_BATTERY)
from homeassistant.core import callback

REQUIREMENTS = ['bluepy==1.2.0']

_LOGGER = logging.getLogger(__name__)

CONF_MEDIAN = 'median'

DEFAULT_FORCE_UPDATE = False
DEFAULT_MEDIAN = 3
DEFAULT_NAME = 'SensorTag'

SCAN_INTERVAL = timedelta(seconds=1200)

# Sensor types are defined like: unit, icon, device_class
SENSOR_TYPES = {
    'temperature': ['°C', 'mdi:thermometer', DEVICE_CLASS_TEMPERATURE],
    'illuminance': ['lux', 'mdi:weather-sunny', DEVICE_CLASS_ILLUMINANCE],
    'humidity': ['%rH', 'mdi:water-percent', DEVICE_CLASS_HUMIDITY],
    'pressure': ['mbar', 'mdi:debug-step-over', DEVICE_CLASS_PRESSURE],
    'battery': ['%', 'mdi:battery-bluetooth', DEVICE_CLASS_BATTERY],
}

SENSOR_TYPES_SENSORNAME = {
    'temperature': 'IRtemperature',
    'illuminance': 'lightmeter',
    'humidity': 'humidity',
    'pressure': 'barometer',
    'battery': 'battery',
}

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_MAC): cv.string,
    vol.Optional(CONF_MONITORED_CONDITIONS, default=list(SENSOR_TYPES)):
        vol.All(cv.ensure_list, [vol.In(SENSOR_TYPES)]),
    vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
    vol.Optional(CONF_MEDIAN, default=DEFAULT_MEDIAN): cv.positive_int,
    # FIXME: bug in voluptuous?
    # expected int for dictionary value @ data['scan_interval']. Got datetime.timedelta(0, 10)
    #vol.Optional(CONF_SCAN_INTERVAL, default=DEFAUTT_SCAN_INTERVAL): cv.positive_timedelta,
    vol.Optional(CONF_FORCE_UPDATE, default=DEFAULT_FORCE_UPDATE): cv.boolean,
})


async def async_setup_platform(hass, config, async_add_entities,
                               discovery_info=None):
    """Set Sensortag."""
    from bluepy import sensortag
    from bluepy.btle import BTLEException

    tag = None
    try:
        tag = sensortag.SensorTag(config.get(CONF_MAC))
    except BTLEException as bterror:
        _LOGGER.info('Coonection error %s, MAC %s',
            bterror, config.get(CONF_MAC))

    force_update = config.get(CONF_FORCE_UPDATE)
    cache = config.get(CONF_SCAN_INTERVAL, SCAN_INTERVAL).total_seconds()
    median = config.get(CONF_MEDIAN)

    devs = []

    for parameter in config[CONF_MONITORED_CONDITIONS]:
        dev_cls = SENSOR_TYPES[parameter][2]

        prefix = config.get(CONF_NAME)
        if prefix:
            name = "{} {}".format(prefix, dev_cls)
        
        sensorname = SENSOR_TYPES_SENSORNAME[parameter]
        if hasattr(tag, sensorname):
           tagfn = getattr(tag, sensorname)
           # enable the sensor
           tagfn.enable()
        devs.append(Sensortag(tag, sensorname, name,
            SENSOR_TYPES[parameter], force_update, cache, median))

    async_add_entities(devs)


class Sensortag(Entity):
    """Implementing the Sensortag sensor."""

    def __init__(self, tag, sensorname, hassname, types, force_update, cache, median):
        """Initialize the sensor."""
        self.tag = tag
        self.sensorname = sensorname
        self._dev_cls = types[2]
        self._unit = types[0]
        self._icon = types[1]
        self._name = hassname
        self._state = None
        self._force_update = force_update
        self._cache = None
        self._cache_timeout = timedelta(seconds=cache)
        self._last_read = None
        self.data = []
        # Median is used to filter out outliers. median of 3 will filter
        # single outliers, while  median of 5 will filter double outliers
        # Use median_count = 1 if no filtering is required.
        self.median_count = median

    async def async_added_to_hass(self):
        """Set initial state."""
        @callback
        def on_startup(_):
            self.async_schedule_update_ha_state(True)

        self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_START, on_startup)

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def device_class(self) -> str:
        """Return the class of the sensor."""
        return self._dev_cls

    @property
    def unit_of_measurement(self):
        """Return the units of measurement."""
        return self._unit

    @property
    def icon(self):
        """Return the icon to use in the frontend."""
        return self._icon

    @property
    def force_update(self):
        """Force update."""
        return self._force_update

    def update(self):
        """
        Update current conditions.
        """
        from bluepy.btle import BTLEException
        import struct
        if not hasattr(self.tag, self.sensorname):
            data = None
        else:
            tagfn = getattr(self.tag, self.sensorname)
            if self._force_update:
                self._cache = None

            if self._cache is None or \
                (datetime.now() - self._cache_timeout > self._last_read):
                self._last_read = datetime.now()
                try:
                    _LOGGER.debug("Read data for %s", self.name)
                    rdata = tagfn.read()

                    if self.sensorname == 'IRtemperature':
                        data = '{:3.1f}'.format(rdata[0])
                    if self.sensorname in ['humidity', 'barometer']:
                        data = '{:.1f}'.format(rdata[1])
                    if self.sensorname == 'lightmeter':
                        data = '{:.1f}'.format(rdata)
                    if self.sensorname == 'battery':
                        data = '{}'.format(rdata)
                    # update the cache
                    self._cache = data
                except struct.error as strerr:
                    _LOGGER.info("Read error %s", strerr)
                    return
                except TypeError as tperr:
                    _LOGGER.info("Read error %s", tperr)                    
                    return
                except IOError as ioerr:
                    _LOGGER.info("Read error %s", ioerr)
                    return
                except BTLEException as bterror:
                    _LOGGER.info("read error %s", bterror)
                    return
            else:
                data = self._cache

        if data is not None:
            _LOGGER.debug("%s = %s", self.name, data)
            self.data.append(data)
        else:
            _LOGGER.info("Did not receive any data from Sensortag %s",
                         self.name)
            # Remove old data from median list or set sensor value to None
            # if no data is available anymore
            if self.data:
                self.data = self.data[1:]
            else:
                self._state = None
            return

        _LOGGER.debug("Data collected: %s", self.data)
        if len(self.data) > self.median_count:
            self.data = self.data[1:]

        if len(self.data) == self.median_count:
            median = sorted(self.data)[int((self.median_count - 1) / 2)]
            _LOGGER.debug("Median is: %s", median)
            self._state = median
        elif self._state is None:
            _LOGGER.debug("Set initial state")
            self._state = self.data[0]
        else:
            _LOGGER.debug("Not yet enough data for median calculation")
