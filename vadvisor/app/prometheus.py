from datetime import datetime, timedelta
from prometheus_client.core import GaugeMetricFamily, CounterMetricFamily

from ..virt.collector import Collector
from .tree import Tree, Subtree


class Metric:

    def __init__(self, name, field, description):
        self.field = field
        self.name = name
        self.description = description
        self.metric = None

    def expose(self):
        yield self.metric


class Gauge(Metric):

    def process(self, labels, value, timestamp=None):
        self.metric.add_metric(labels, value)

    def reset(self, label_keys):
        self.metric = GaugeMetricFamily(self.name, self.description, labels=label_keys)


class Counter(Metric):

    def process(self, labels, value, timestamp=None):
        self.metric.add_metric(labels, value)

    def reset(self, label_keys):
        self.metric = CounterMetricFamily(self.name, self.description, labels=label_keys)


class LibvirtCollector:

    _vm = Tree(['uuid'], [
        Gauge('vm_up', 'state', '0 if the VM is down, 1 if the VM is up and running, other states'),
        Subtree('cpu', [
            Counter('vm_cpu_milliseconds_total', 'cpu_time', 'Overall VM CPU time in milliseconds'),
            Counter('vm_cpu_system_milliseconds_total', 'system_time', 'Overall VM System CPU time in milliseconds'),
            Counter('vm_cpu_user_milliseconds_total', 'user_time', 'Overall VM User CPU time in milliseconds')
        ]),
        Subtree('memory', [
            Gauge('vm_memory_bytes', 'actual', "VM Memory in bytes"),
        ])
    ])

    _interfaces = Tree(['uuid', 'interface'], [
        Counter('vm_network_receive_bytes_total', 'rx_bytes', 'Cumulative count of bytes received'),
        Counter('vm_network_receive_packets_total', 'rx_packets', 'Cumulative count of packets received'),
        Counter('vm_network_receive_dropped_packets_total', 'rx_dropped', 'Cumulative count of packets dropped while receiving'),
        Counter('vm_network_receive_errors_total', 'rx_errors', 'Cumulative count of errors encountered while receiving'),
        Counter('vm_network_transmit_bytes_total', 'tx_bytes', 'Cumulative count of bytes transmitted'),
        Counter('vm_network_transmit_packets_total', 'tx_packets', 'Cumulative count of packets transmitted'),
        Counter('vm_network_transmit_dropped_packets_total', 'tx_dropped', 'Cumulative count of packets dropped while transmitting'),
        Counter('vm_network_transmit_errors_total', 'tx_errors', 'Cumulative count of errors encountered while transmitting'),
    ])

    _disks = Tree(['uuid', 'device'], [
        Counter('vm_disk_write_requests_total', 'wr_reqs', 'Cumulative count of disk write requests'),
        Counter('vm_disk_write_bytes_total', 'wr_bytes', 'Cumulative count of disk writes in bytes'),
        Counter('vm_disk_read_requests_total', 'rd_reqs', 'Cumulative count of disk read requests'),
        Counter('vm_disk_read_bytes_total', 'rd_bytes', 'Cumulative count of disk reads in bytes'),
    ])

    _cpus = Tree(['uuid', 'cpu'], [
        Counter('vm_vcpu_milliseconds_total', 'vcpu_time', 'Overall CPU time on the virtual CPU in milliseconds'),
    ])

    def __init__(self, collector=Collector(), report_minutes=10):
        self.collector = collector
        self.report_minutes = timedelta(minutes=report_minutes)
        self._known_vms = {}

    def collect(self):
        # Get stats from libvirt
        stats = self.collector.collect()

        # Reset all metrics since the python prometheus library does not
        # override collected metrics with identical label values
        for tree in (self._vm, self._interfaces, self._disks, self._cpus):
            tree.reset()

        # Collect metrics
        now = datetime.now()
        for domainStats in stats:
            # VM status, we have a collection copy, convert state to a number
            domainStats['state'] = 1 if domainStats['state'] == "Running" else 0

            self._known_vms[domainStats['uuid']] = now

            # VM stats
            labels = [domainStats['uuid']]
            self._vm.process(labels, domainStats)

            # Networking stats
            for interface in domainStats['network']['interfaces']:
                labels = [domainStats['uuid'], interface['name']]
                self._interfaces.process(labels, interface)
            # Disk stats
            for disk in domainStats['diskio']:
                labels = [domainStats['uuid'], disk['name']]
                self._disks.process(labels, disk)
            # CPU stats
            try:
                for cpu in domainStats['cpu']['per_cpu_usage']:
                    labels = [domainStats['uuid'], str(cpu['index'])]
                    self._cpus.process(labels, cpu)
            except KeyError:
                print("'cpu' key is missing")        

        # Prometheus reports disappearing metrics for 5 minutes with the same
        # value. Report disappeared VMs for 10 minutes as down to allow
        # filtering out these stale metrics.
        vms_to_delete = []
        for uuid in self._known_vms:
            # Already more than 10 minutes down, don't report the VM anymore
            if self._known_vms[uuid] < now - self.report_minutes:
                vms_to_delete.append(uuid)
            # VM is down report it as down for the next 10 minutes
            elif self._known_vms[uuid] < now:
                labels = [uuid]
                self._vm._elements['state'].process(labels, 0)

        for uuid in vms_to_delete:
            del self._known_vms[uuid]

        # Yield all collected metrics
        for tree in (self._vm, self._interfaces, self._disks, self._cpus):
            for metric in tree.expose():
                yield metric


class StatdMetric:

    def __init__(self, name, field):
        self.field = field
        self.name = name
        self.metric = None

    def reset(self, label_keys):
        self.metric = []

    def expose(self):
        for metric in self.metric:
            yield metric
