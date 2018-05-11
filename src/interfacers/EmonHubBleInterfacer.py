import time
import struct
from bluepy import btle
import Cargo
from emonhub_interfacer import EmonHubInterfacer

"""class EmonhubBleInterfacer

Polls a Bluetooth LE sensor for temperature, huimidity and battery level

Currently only tested with a Silicon Labs Thunderboard Sense 2


Example config snippets:

[interfacers]

[[blesensor]]
    Type = EmonHubBleInterfacer
    [[[init_settings]]]
    [[[runtimesettings]]]
        pubchannels = ToEmonCMS,
	read_interval = 20

[nodes]

[[1]]
    nodename = Sensornode
    device_addr = '00:0b:57:64:8c:a2'

    [[[rx]]]
        scales = 0.01,0.01,1,0.001
        units = C,%,%,mbar

"""

class EmonHubBleInterfacer(EmonHubInterfacer):

    def __init__(self, name, device_addr='', node_id=1):
        """Initialize interfacer

        device_addr (string): BLE MAC address to connect to

        """

        # Initialization
        super(EmonHubBleInterfacer, self).__init__(name)

        self._private_settings = {
            'read_interval': 60
        }

        self._addr = device_addr
        self._node_id = node_id
        self._last_read_time = 0
        self._bat_readings = []

        try:
	    self._connect()
        except Exception as e:
            self._ble = False
            self._log.warning('Connection failed: {}'.format(e))

    def close(self):
        """Close serial port"""

        # Close serial port
        if self._ble is not None:
            self._log.debug("Closing Bluetooth connection")
            self._ble.disconnect()

        return

    def read(self):
        """Read data from bluetooth sensor

        """

        # Don't read before the configured interval
        interval = int(self._private_settings['read_interval'])
        if time.time() - self._last_read_time < interval:
            return

        self._log.debug("BLE read")

        self._last_read_time = time.time()

        # Check connection, connect if we didn't connect during init
        if not self._ble:
            self._connect()

        if not self._ble:
            return False

        temp = self._get_temperature()
        rh = self._get_humidity()
        bat = self._get_bat_level()
        pressure = self._get_pressure()

        data = '{}, {}, {}, {}'.format(temp, rh, bat, pressure)

        # Create a Payload object
        c = Cargo.new_cargo(rawdata=data)
        c.realdata = (temp, rh, bat, pressure)
        c.names = ('temp', 'humidity', 'battery', 'pressure')


        c.nodeid = self._node_id

        return c

    def set(self, **kwargs):

        for key, setting in self._private_settings.iteritems():
            # Decide which setting value to use
            if key in kwargs.keys():
                setting = kwargs[key]
            else:
                setting = self._private_settings[key]

            # Ignore unchanged
            if key in self._settings and self._settings[key] == setting:
                continue
            elif key == 'read_interval':
                setting = float(setting)
            else:
                self._log.warning("'%s' is not valid for %s: %s" % (str(setting), self.name, key))
                continue

            self._log.debug('Setting {}: {}'.format(key, setting))
            self._private_settings[key] = setting

        # include kwargs from parent
        super(EmonHubBleInterfacer, self).set(**kwargs)

    def _get_val(self, char, format='h'):
        val = char.read()
        (val,) = struct.unpack(format, val)
        return val
        
    def _get_temperature(self):        
        return self._get_val(self._temperature)

    def _get_humidity(self):
        return self._get_val(self._humidity)

    def _get_pressure(self):
        return self._get_val(self._pressure, 'I')

    def _get_bat_level(self):
        val =  self._get_val(self._bat_level, 'B')

        # The battery reading is very noisy - do a simple average
        self._bat_readings.insert(0, val)
        self._bat_readings = self._bat_readings[0:20]

        val = sum(self._bat_readings)/float(len(self._bat_readings))
        self._log.debug('Batt: {} -> {}'.format(self._bat_readings, val))
        
        return round(val)

    def _connect(self):
        self._log.debug("Connecting to BLE address {}...".format(self._addr))
        self._ble = None

        try:
            self._ble = btle.Peripheral(self._addr)
        except btle.BTLEException as e:
            self._log.error(e)
            return False

        self._temperature = self._ble.getCharacteristics(uuid=btle.AssignedNumbers.temperature)[0]
        self._humidity = self._ble.getCharacteristics(uuid=btle.AssignedNumbers.humidity)[0]
        self._bat_level = self._ble.getCharacteristics(uuid=btle.AssignedNumbers.battery_level)[0]
        self._pressure = self._ble.getCharacteristics(uuid=btle.AssignedNumbers.pressure)[0]

        return True

