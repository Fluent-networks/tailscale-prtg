#!/usr/bin/env python3
import json
import subprocess
import time
from pathlib import Path

# Tailscale path
TAILSCALE = '/usr/bin/tailscale'

# JSON channel store
STORE = '/var/prtg/scriptsxml/tailscale.json'

# PRTG channels mapped to tailscale sample indicies
CHANNELS = [
    {
        "name": "Traffic Total (Speed)",
        "ctype": "speed",
        "metrics": [3,4,5,10,11,12],
        "value": 0
    },
    {
        "name": "Traffic In (Speed)",
        "ctype": "speed",
        "metrics": [3,4,5],
        "value": 0.0
    },
    {
        "name": "Traffic Out (Speed)",
        "ctype": "speed",
        "metrics": [10,11,12],
        "value": 0.0
    },
    {
        "name": "Advertised Routes",
        "ctype": "count",
        "metrics": [0],
        "value": 0
    },
    {
        "name": "Approved Routes",
        "ctype": "count",
        "metrics": [0],
        "value": 0
    },
]

# Tailscale samples
SAMPLES = [
    {
        'name': 'tailscaled_advertised_routes',
        'value': 0,
    },
    {
        'name': 'tailscaled_approved_routes',
        'value': 0,
    },
    {
        'name': 'tailscaled_health_messages{type="warning"}',
        'value': 0,
    },
    {
        'name': 'tailscaled_inbound_bytes_total{path="derp"}',
        'value': 0,
    },
    {
        'name': 'tailscaled_inbound_bytes_total{path="direct_ipv4"}',
        'value': 0,
    },
    {
        'name': 'tailscaled_inbound_bytes_total{path="direct_ipv6"}',
        'value': 0,
    },
    {
        'name': 'tailscaled_inbound_dropped_packets_total{reason="acl"}',
        'value': 0,
    },
    {
        'name': 'tailscaled_inbound_packets_total{path="derp"}',
        'value': 0,
    },
    {
        'name': 'tailscaled_inbound_packets_total{path="direct_ipv4"}',
        'value': 0,
    },
    {
        'name': 'tailscaled_inbound_packets_total{path="direct_ipv6"}',
        'value': 0,
    },
    {
        'name': 'tailscaled_outbound_bytes_total{path="derp"}',
        'value': 0,
    },
    {
        'name': 'tailscaled_outbound_bytes_total{path="direct_ipv4"}',
        'value': 0,
    },
    {
        'name': 'tailscaled_outbound_bytes_total{path="direct_ipv6"}',
        'value': 0,
    },
    {
        'name': 'tailscaled_outbound_dropped_packets_total{reason="error"}l',
        'value': 0,
    },    
    {
        'name': 'tailscaled_outbound_packets_total{path="derp"}',
        'value': 0,
    },
    {
        'name': 'tailscaled_outbound_packets_total{path="direct_ipv4"}',
        'value': 0,
    },
    {
        'name': 'tailscaled_outbound_packets_total{path="direct_ipv6"}',
        'value': 0,
    },
]

class Sensor(object):
    """PRTG Sensor class.

    Attributes:
        timestamp (int): Unix timestamp
        channels (list): List of sensor channels
        samples (list): Tailscale metric samples
    """

    def __init__(self, load=False):
        self.timestamp = None
        self.channels = []
        self.samples = SAMPLES.copy()

        # Load from JSON store
        if load:
            self.load()

        if self.channels:
            return

        for c in CHANNELS:
            self.channels.append(Channel(c))
    
    def load(self):
        """Load stored data into the sensor object."""
        store = Path(STORE)
        if store.is_file():
            with open(STORE) as f:
                data = json.load(f)
                self.timestamp = data['timestamp']
                for c in data['channels']:
                    self.channels.append(Channel(c))
                self.samples = data['samples']
            f.close()
    
    def save(self):
        """Save sensor object to file."""
        cdata = []
        for c in self.channels:
            cdata.append(c.__dict__)
        data = {'timestamp': self.timestamp, 'channels': cdata, 
                'samples': self.samples}
        with open(STORE, 'w+') as f:
            json.dump(data, f)
    
    def metrics(self):
        """Acquire tailscale metric samples."""
        self.timestamp = time.time()
        r = subprocess.run([TAILSCALE, 'metrics'], stdout=subprocess.PIPE)
        raw_metrics = r.stdout.decode('utf-8')

        for line in raw_metrics.splitlines():
            # Ignore comments
            if line.startswith('#'):
                continue
            # Obtain name and value
            (name, value) = line.split(' ')
            # Find the matching sample and store the value
            sample = next((s for s in self.samples if s["name"] == name), None)
            if sample:
                sample['value'] = float(value)

    def update(self, last):
        """Populate channel values
        
        Arguments:
            last: Sensor object loaded from store.
        """
        # Assume 5 minutes if this is the first run
        if last.timestamp is None:
            interval = 300
        else:
            interval = self.timestamp - last.timestamp
        for idx, channel in enumerate(self.channels):
            channel.update(interval, last.channels[idx], last.samples, self.samples)


class Channel(object):
    """PRTG Channel class.

    Attributes:
        name (str): Channel name
        ctype (str): Channel type
        value (float | int): Channel value
        metrics (list): Tailscale metric map
        unit (str): PRTG Unit tag
        size (str): PRTG Size tag
        float(str) PRTG Float tag
    """

    def __init__(self, c):
        self.name = c['name']
        self.ctype = c['ctype']
        self.metrics = c['metrics']
        self.value = c['value']
        if self.ctype == 'count':
            self.unit = 'Count'
            self.size = 'One'
            self.float = 0
        elif self.ctype == 'volume':
            self.unit = 'BytesBandwidth'
            self.float = 1
        elif self.ctype == 'speed':
            self.unit = 'SpeedNet'
            self.float = 1

    def update(self, interval, last_channel, last_samples, samples):
        """Update the channel value
        
        Arguments:
            interval: Time in seconds since the last update
            last_channel: Last Channel loaded from store
            last_samples: Last list of samples loaded from store
            samples: Current list of samples
        """
        # Obtain the subset of relevant metric samples
        slist = [samples[i] for i in self.metrics]

        # Count is a absolute value
        if self.ctype == 'count':
            self.value = int(sum(s['value'] for s in slist))
        
        # Volume type is the difference between last and current
        # values in bytes
        if self.ctype == 'volume':
            # Sum current metrics and calculate the difference
            cval = int(sum(s['value'] for s in slist))
            self.value = cval - last_channel.value

        # Speed requires us to sum the last metric values and subtract from
        # sum of current metric values. A divisor of 64 is required to provide
        # the correct value to PRTG's conversion process.
        elif self.ctype == 'speed':
            # Difference of bytes between current and previous
            plist = [last_samples[i] for i in self.metrics]
            pval = float(sum(s['value'] for s in plist))
            cval = float(sum(s['value'] for s in slist))
            self.value = (cval - pval) / 64

    def marshal(self):
        """Output the object as a dict suitable for return to PRTG"""
        if self.ctype == 'count':
            value = int(self.value)
        else:
            value = float("{:.2f}".format(self.value))
        data = {
            'channel': self.name, 
            'value': value,
            'unit': self.unit,
            'float': self.float
            }
        if self.ctype == 'speed':
            data['speedsize'] = 'MegaBit'
        return data


# Load last stored sensor
stored = Sensor(load=True)

# Create a new sensor, obtain metrics, update and save
sensor = Sensor()
sensor.metrics()
sensor.update(stored)
sensor.save()

# Create PRTG output
result = []
for channel in sensor.channels:
    result.append(channel.marshal())
print(json.dumps({'prtg': { 'result': result } }))

