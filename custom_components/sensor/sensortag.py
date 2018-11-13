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
from threading import Lock
from bluepy import sensortag
from bluepy.btle import BTLEException
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

class _Sensortag():
    """Read data from Sensortag sensor."""
    
    def __init__(self, mac, cache_timeout):
        """Initialize the sensor."""
        self.tag = None
        self.mac = mac
        try:
            self.tag = sensortag.SensorTag(mac)
        except BTLEException as bterror:
            _LOGGER.info('Coonection error %s, MAC %s', bterror, mac)
        self._registered = []
        self._cache = {}
        self._cache_timeout = timedelta(seconds=cache_timeout)
        self._last_read = datetime.now() - timedelta(seconds=cache_timeout+1)
        self.lock = Lock()
    
    def enable(self, sensorname):
        if hasattr(self.tag, sensorname):
           tagfn = getattr(self.tag, sensorname)
           # enable the sensor
           tagfn.enable()
           self._registered.append(sensorname)
        else:
            _LOGGER.info('%s is not supported by %s', sensorname, self.mac)

    def read(self, sensorname, force_update):
        """Read sensor data"""
        if sensorname not in self._registered:
            _LOGGER.info(
                '%s not enabled or not supported by SensorTag %s',
                sensorname, self.mac)
            return None

        if self._cache is None or force_update or \
            (datetime.now() - self._cache_timeout > self._last_read):
            self._last_read = datetime.now()
            # read all in once!
            with self.lock:
                # try not to clean the cache directly
                # we fill refill the data sensor by sensor when force_update is enabled
                data = self._cache
                for sensor in self._registered:
                    if force_update and sensor != sensorname:
                        continue
                    tagfn = getattr(self.tag, sensor)
                    try:
                        rdata = tagfn.read()
                        if sensor == 'IRtemperature':
                            data[sensor] = '{:3.1f}'.format(rdata[0])
                        if sensor in ['humidity', 'barometer']:
                            data[sensor] = '{:.1f}'.format(rdata[1])
                        if sensor == 'lightmeter':
                            data[sensor] = '{:.1f}'.format(rdata)
                        if sensor == 'battery':
                            data[sensor] = '{}'.format(rdata)
                    except TypeError as tperr:
                        _LOGGER.info("Read error %s, %s@%s", tperr, sensor, self.mac)
                    except IOError as ioerr:
                        _LOGGER.info("Read error %s, %s@%s", ioerr, sensor, self.mac)
                    except BTLEException as bterror:
                        _LOGGER.info("Read error %s, %s@%s", bterror, sensor, self.mac)

                # update the cache
                self._cache = data

        if sensorname in self._cache:
            return self._cache[sensorname]
        else:
            return None
    

async def async_setup_platform(hass, config, async_add_entities,
                               discovery_info=None):
    """Set Sensortag."""
    force_update = config.get(CONF_FORCE_UPDATE)
    cache = config.get(CONF_SCAN_INTERVAL, SCAN_INTERVAL).total_seconds()
    median = config.get(CONF_MEDIAN)
    
    _sensor_tag = _Sensortag(config.get(CONF_MAC), cache)

    devs = []

    for parameter in config[CONF_MONITORED_CONDITIONS]:
        dev_cls = SENSOR_TYPES[parameter][2]

        prefix = config.get(CONF_NAME)
        if prefix:
            name = "{} {}".format(prefix, dev_cls)
        
        sensorname = SENSOR_TYPES_SENSORNAME[parameter]
        _sensor_tag.enable(sensorname)

        devs.append(Sensortag(_sensor_tag, sensorname, name,
            SENSOR_TYPES[parameter], force_update, median))

    async_add_entities(devs)


class Sensortag(Entity):
    """Implementing the Sensortag sensor."""

    def __init__(self, sensortag, sensorname, hassname, types, force_update, median_count):
        """Initialize the sensor."""
        self.sensortag = sensortag
        self.sensorname = sensorname
        self._dev_cls = types[2]
        self._unit = types[0]
        self._icon = types[1]
        self._name = hassname
        self._force_update = force_update
        self._state = None
        self.data = []
        # Median is used to filter out outliers. median of 3 will filter
        # single outliers, while  median of 5 will filter double outliers
        # Use median_count = 1 if no filtering is required.
        self.median_count = median_count        

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
        _LOGGER.debug("Read data for %s", self.name)
        data = self.sensortag.read(self.sensorname, self._force_update)

        if data is None:
            _LOGGER.info("Did not receive any data from %s", self.name)
        else:
            _LOGGER.debug("%s = %s", self.name, data)
            self.data.append(data)
        # we only need {median_count} data points
        if len(self.data) > self.median_count:
            self.data = self.data[1:]
        # median filter
        if len(self.data) == self.median_count:
            median = sorted(self.data)[int((self.median_count - 1) / 2)]
            self._state = median
        elif self.data:
            self._state = self.data[0]
        else:
            _LOGGER.debug("Not yet enough data for median calculation")
