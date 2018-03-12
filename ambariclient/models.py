#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""
Defines all the model classes for the various parts of the API.
"""

import logging
import json
import os
import time

from ambariclient import base, exceptions, events
from ambariclient.utils import normalize_underscore_case, NullHandler

LOG = logging.getLogger(__name__)
LOG.addHandler(NullHandler())


class Bootstrap(base.PollableMixin, base.GeneratedIdentifierMixin, base.QueryableModel):
    """Boostrap hosts by installing the agent on them.

    There are two ways to register hosts with Ambari:
        1. Preload the agent and configuration on the hosts.
        2. Preload an ssh key on the hosts and tell Ambari to bootstrap them.

    Boostrapping involves using an uploaded private SSH key to contact the
    hosts via SSH and tell them to install and configure the Ambari agent.

    It is generally not recommended for production workloads as you're passing
    in the private SSH key to Ambari to contact the hosts, but it's very useful
    for development or proof-of-concept work.

    To bootstrap some hosts:
        ambari.bootstrap.create(hosts=[hostname, hostname, ...],
                                sshKey=ssh_key_as_string,
                                user=username)

    The wait() method works as expected here and will not return until all of
    the bootstrapped hosts are online and registered with the Ambari server.

    The API for boostrap is very inconsistent with the rest of the API.  There
    is no way to query for a collection of bootstrap attempts, for example.  We
    work around that as much as possible, but some things might not work as
    expected.
    """
    path = 'bootstrap'
    primary_key = 'requestId'
    fields = ('status', 'requestId', 'message', 'hostsStatus')

    def __init__(self, *args, **kwargs):
        super(Bootstrap, self).__init__(*args, **kwargs)
        self._hosts = []

    @events.evented
    def create(self, **kwargs):
        # we always want the verbose response here
        kwargs['verbose'] = True

        if 'user' not in kwargs:
            kwargs['user'] = 'root'

        if self.client.version >= (2,0):
            if 'userRunAs' not in kwargs:
                kwargs['userRunAs'] = 'root'

        if 'ssh_key_path' in kwargs:
            ssh_key_path = os.path.expanduser(kwargs.pop('ssh_key_path'))
            with open(ssh_key_path) as ssh_key_file:
                kwargs['sshKey'] = ssh_key_file.read()

        if 'sshKey' not in kwargs:
            raise exceptions.BadRequest("You must pass in a private ssh key to bootstrap hosts")

        data = self._generate_input_dict(**kwargs)
        self.load(self.client.post(self.url,
                                   content_type="application/json",
                                   data=data))
        # this special case morphs the object URL after creation since we don't
        # know the requestId ahead of time
        self._hosts = kwargs['hosts']
        self._href = None
        return self

    @property
    def has_failed(self):
        return True if self.status == 'ERROR' else False

    @property
    def is_finished(self):
        return True if self.status == 'SUCCESS' else False

    @property
    def hosts(self):
        if self._hosts:
            return self.client.hosts(self._hosts)
        return []

    def wait(self, **kwargs):
        """Wait until the bootstrap completes and all hosts are registered.

        Even after bootstrap finishes, there is a slight delay while the agents
        start and register themselves with Ambari.  We add in additional checks
        to ensure they are fully online before returning, because that's all a
        user should care about.
        """
        super(Bootstrap, self).wait(**kwargs)
        # make sure all the hosts are registered as well
        for host in self.hosts:
            host.wait()
        return self

    def inflate(self):
        # the requestId isn't returned in the response body except on create
        # so keep track of it manually.
        request_id = self._data.get('requestId')
        super(Bootstrap, self).inflate()
        self._data['requestId'] = request_id
        return self


class MetricCollection(base.DependentModelCollection):
    def __call__(self, *args, **kwargs):
        if len(args) == 1 and isinstance(args[0], dict):
            metrics = []
            for name in args[0]:
                metrics.append({
                    'name': name,
                    'metrics': args[0][name],
                })
            return super(MetricCollection, self).__call__(metrics, **kwargs)

        return super(MetricCollection, self).__call__(*args, **kwargs)


class Metric(base.DependentModel):
    collection_class = MetricCollection
    fields = ('name', 'metrics')
    primary_key = 'name'


class Action(base.QueryableModel):
    path = 'actions'
    data_key = 'Actions'
    primary_key = 'action_name'
    fields = ('action_name', 'action_type', 'default_timeout', 'description', 'inputs',
              'target_component', 'target_service', 'target_type')


class Task(base.PollableMixin, base.QueryableModel):
    path = 'tasks'
    data_key = 'Tasks'
    primary_key = 'id'
    fields = ('id', 'cluster_name', 'host_name', 'request_id', 'exit_code', 'stdout',
              'stderr', 'status', 'attempt_cnt', 'command', 'role', 'start_time',
              'stage_id', 'end_time', 'error_log', 'output_log', 'command_detail',
              'structured_out', 'custom_command_name')

    @property
    def has_failed(self):
        return self.status not in ('PENDING', 'QUEUED', 'IN_PROGRESS', 'COMPLETED')

    @property
    def is_finished(self):
        return self.status == 'COMPLETED'


class Request(base.PollableMixin, base.GeneratedIdentifierMixin, base.QueryableModel):
    path = 'requests'
    data_key = 'Requests'
    primary_key = 'id'
    fields = ('id', 'request_context', 'status', 'request_status', 'progress_percent',
              'queued_task_count', 'task_count', 'completed_task_count', 'type',
              'operation_level', 'exclusive', 'aborted_task_count', 'create_time',
              'end_time', 'failed_task_count', 'inputs', 'request_schedule',
              'resource_filters', 'start_time', 'timed_out_task_count')
    relationships = {
        'tasks': Task,
    }

    @property
    def has_failed(self):
        return self.request_status in ('FAILED', 'ABORTED')

    @property
    def is_finished(self):
        return int(self.progress_percent) == 100

    def create(self, **kwargs):
        data = self._generate_input_dict(**kwargs)
        # we don't have the id for a request, so post to the parent
        # yay for consistency
        self.load(self.client.post(self.parent.url, data=data))
        return self


class AlertHistory(base.QueryableModel):
    min_version = (2,0,0)
    path = 'alert_history'
    data_key = 'AlertHistory'
    primary_key = 'id'
    fields = ('id', 'cluster_name', 'component_name', 'definition_id', 'definition_name',
              'host_name', 'instance', 'label', 'service_name', 'state', 'text', 'timestamp')


class Component(base.QueryableModel):
    path = 'components'
    data_key = 'ServiceComponentInfo'
    primary_key = 'component_name'
    fields = ('component_name', 'component_version', 'server_clock',
              'service_name', 'properties')

    def to_json_dict(self):
        """Components are passed in with 'name' as the key rather than the
        primary 'component_name' key for no apparent reason.
        """
        return { 'name': self.component_name }


class ClusterServiceComponentCollection(base.QueryableModelCollection):
    def get_client_config_tar(self):
        """Returns tarfile.Tarfile instance."""
        url = self.url + "?format=client_config_tar"
        return self.client.get(url)


class HostComponentCollection(base.QueryableModelCollection):
    @property
    def _server_components(self):
        """Client components can't be stopped or started, so we need to filter them out"""
        server_components = []
        for component in self:
            service = component.cluster.services(component.service_name)
            if service.components(component.component_name).category != 'CLIENT':
                server_components.append(component)

        return server_components

    def install(self, context=None):
        """Install all of the components associated with this host."""
        components = [x.component_name for x in self if x.state in ('INIT', 'UNINSTALLED')]
        if not context:
            context = "Install All Host Components"

        if components:
            self.load(self.client.put(self.url, data={
                "RequestInfo": {
                    "context": context,
                    "operation_level": {
                        "level": "HOST",
                        "cluster_name": self.parent.cluster_name,
                        "host_name": self.parent.host_name,
                    },
                    "query": "HostRoles/component_name.in({0})".format(','.join(components)),
                },
                "Body": {
                    "HostRoles": {"state": "INSTALLED"},
                },
            }))
        return self

    def start(self, context=None):
        """Start all of the components associated with this host."""
        components = [x.component_name
                      for x in self._server_components
                      if x.state in ('INSTALLED', 'STOPPED')]
        if not context:
            context = "Start All Host Components"

        if components:
            self.load(self.client.put(self.url, data={
                "RequestInfo": {
                    "context": context,
                    "operation_level": {
                        "level": "HOST",
                        "cluster_name": self.parent.cluster_name,
                        "host_name": self.parent.host_name,
                    },
                    "query": "HostRoles/component_name.in({0})".format(','.join(components)),
                },
                "Body": {
                    "HostRoles": {"state": "STARTED"},
                },
            }))
        return self

    def stop(self, context=None):
        """Stop all of the components associated with this host."""
        components = [x.component_name for x in self._server_components if x.state == 'STARTED']
        if not context:
            context = "Stop All Host Components"

        if components:
            self.load(self.client.put(self.url, data={
                "RequestInfo": {
                    "context": context,
                    "operation_level": {
                        "level": "HOST",
                        "cluster_name": self.parent.cluster_name,
                        "host_name": self.parent.host_name,
                    },
                    "query": "HostRoles/component_name.in({0})".format(','.join(components)),
                },
                "Body": {
                    "HostRoles": {"state": "INSTALLED"},
                },
            }))
        return self


class HostComponent(Component):
    collection_class = HostComponentCollection
    path = 'host_components'
    data_key = 'HostRoles'
    fields = ('cluster_name', 'component_name', 'desired_stack_id',
              'desired_state', 'host_name', 'maintenance_state', 'service_name',
              'stack_id', 'stale_configs', 'state', 'actual_configs',
              'desired_admin_state')

    def install(self, context=None):
        if not context:
            context = "Install %s" % normalize_underscore_case(self.component_name)

        """Installs this component on the host in question."""
        self.load(self.client.put(self.url, data={
            "RequestInfo": {
                "context": context,
            },
            "HostRoles": {
                "state": "INSTALLED",
            },
        }))
        return self

    def start(self, context=None):
        if not context:
            context = "Start %s" % normalize_underscore_case(self.component_name)

        """Starts this component on its host, if already installed."""
        self.load(self.client.put(self.url, data={
            "RequestInfo": {
                "context": context,
            },
            "HostRoles": {
                "state": "STARTED",
            },
        }))
        return self

    def stop(self, context=None):
        if not context:
            context = "Stop %s" % normalize_underscore_case(self.component_name)

        """Starts this component on its host, if already installed and started."""
        self.load(self.client.put(self.url, data={
            "RequestInfo": {
                "context": context,
            },
            "HostRoles": {
                "state": "INSTALLED",
            },
        }))
        return self

    def restart(self, context=None):
        if not context:
            context = "Restart %s" % normalize_underscore_case(self.component_name)

        """Restarts this component on its host, if already installed and started."""
        self.load(self.client.post(self.cluster.requests.url, data={
            "RequestInfo": {
                "command": "RESTART",
                "context": context,
                "operation_level": {
                    "level": "SERVICE",
                    "cluster_name": self.cluster_name,
                    "service_name": self.service_name,
                },
            },
            "Requests/resource_filters": [{
                "service_name": self.service_name,
                "component_name": self.component_name,
                "hosts": self.host_name,
            }],
        }))
        return self


class ClusterServiceComponent(Component):
    collection_class = ClusterServiceComponentCollection
    fields = ['cluster_name', 'component_name', 'service_name', 'category',
              'installed_count', 'started_count', 'total_count']
    extra_fields = {
        # some components have additional component-specific fields added, because why not?
        # this list might grow over time as more are discovered
        'NAMENODE': ["CapacityRemaining", "CapacityTotal", "CapacityUsed", "DeadNodes",
                     "DecomNodes", "HeapMemoryMax", "HeapMemoryUsed", "LiveNodes",
                     "NonDfsUsedSpace", "NonHeapMemoryMax", "NonHeapMemoryUsed",
                     "PercentRemaining", "PercentUsed", "Safemode", "StartTime", "TotalFiles",
                     "UpgradeFinalized", "Version"],
    }

    relationships = {
        'host_components': HostComponent,
        'metrics': Metric,
    }

    def __getattr__(self, attr):
        if ('component_name' in self._data and self._data['component_name'] in self.extra_fields
                and attr in self.extra_fields[self._data['component_name']]):
            if attr not in self._data:
                self.inflate()
            return self._data.get(attr)
        if attr == 'host_components':
            # for some reason they come back as dependent models here
            self.inflate()
        return super(ClusterServiceComponent, self).__getattr__(attr)

    def restart(self):
        """Restarts this component on its host, if already installed and started."""
        hosts = [hc.host_name for hc in self.host_components]
        if hosts:
            self.load(self.client.post(self.cluster.requests.url, data={
                "RequestInfo": {
                    "command": "RESTART",
                    "context": "Restart %s" % normalize_underscore_case(self.component_name),
                    "operation_level": {
                        "level": "SERVICE",
                        "cluster_name": self.cluster_name,
                        "service_name": self.service_name,
                    },
                },
                "Requests/resource_filters": [{
                    "service_name": self.service_name,
                    "component_name": self.component_name,
                    "hosts": ','.join(hosts)
                }],
            }))
        return self


class Host(base.PollableMixin, base.QueryableModel):
    path = 'hosts'
    data_key = 'Hosts'
    primary_key = 'host_name'
    fields = ('host_name', 'cluster_name', 'cpu_count', 'os_arch', 'disk_info',
              'os_type', 'total_mem', 'host_state', 'ip', 'rack_info',
              'public_host_name', 'host_health_report', 'host_status', 'ip',
              'last_agent_env', 'last_heartbeat_time', 'last_registration_time',
              'maintenance_state', 'os_arch', 'os_type', 'ph_cpu_count',
              'desired_configs')

    default_interval = 5
    default_timeout = 180

    @property
    def has_failed(self):
        """Detect whether the host registration failed.

        There's nothing to do other than wait for it to time out on getting a
        HEALTHY state.
        """
        return False

    @property
    def is_finished(self):
        """Make sure the host is registered with Ambari."""
        if self.host_status == 'HEALTHY':
            return True

        # starting with 2.0.0, maintenance mode sets host_status to 'UNKNOWN'
        if self.maintenance_state == 'ON' and self.host_status == 'UNKNOWN':
            return True

        return False

    def wait(self, **kwargs):
        # we lose the request checking from base.QueryableModel
        # there might be a more Pythonic way to handle this
        if self.request:
            self.request.wait(**kwargs)

        # the host might give a 404 on the first few attempts, give it a chance
        # to register
        for x in range(1, 7):
            try:
                self.inflate()
            except exceptions.NotFound:
                if x == 6:
                    raise
                else:
                    self._is_inflating = False
                    LOG.debug("Host not found (attempt %d): %s", x, self.host_name)
                    time.sleep(5)

        return super(Host, self).wait(**kwargs)


class HostMaintenance(object):
    def __init__(self, host):
        self.host = host

    def enable(self):
        """Set all components on a host to maintenance mode.

        Maintenance mode disables monitoring, so it's then safe to stop or
        remove components, etc.
        """
        # Ambari API currently has a bug where it doesn't return the Request object here
        self.host.load(self.host.client.put(self.host.url, data={
            "RequestInfo": {
                "context": "Start Maintenance Mode",
                "query": "Hosts/host_name.in(%s)" % self.host.host_name,
            },
            "Body": {
                "Hosts": {"maintenance_state": "ON"},
            },
        }))
        return self.host

    def disable(self):
        """Turn off maintenance mode on this host."""
        # Ambari API currently has a bug where it doesn't return the Request object here
        self.host.load(self.host.client.put(self.host.url, data={
            "RequestInfo": {
                "context": "Stop Maintenance Mode",
                "query": "Hosts/host_name.in(%s)" % self.host.host_name,
            },
            "Body": {
                "Hosts": {"maintenance_state": "OFF"},
            },
        }))
        return self.host


class ClusterHosts(base.QueryableModelCollection):
    def create_many(self, hosts):
        """Add multiple hosts to a cluster in one call.

        For Ambari 2.0+, this uses the new 'add hosts to host_group' feature. For older versions
        of Ambari, we attempt to mimic the functionality in the client as much as possible by
        loading the blueprint and figuring out what all components need to be installed and
        adding them to the host.  Unfortunately, there's no easy way to mimic the automatic
        'install and start' phase, so you'll have to manually do that in your code.

        Ambari 1.7.0:
            cluster.hosts.create_many([...])
            for host in cluster.hosts(new_hostname):
                host.components.install().wait()
                host.components.start().wait()

        Ambari 2.0+:
            cluster.hosts.create_many([...]).wait()

        In either case, the hosts must all be registered with Ambari before adding them.  This
        can be done using `Boostrap` or manually registering the Ambari agents on each host.

        :param hosts: a list of dictionaries containing the keys `host_name`, `host_group`,
            and `blueprint`:
            {
                'host_name': 'c6405.ambari.apache.org',
                'host_group': 'my-hostgroup',
                'blueprint': 'my-blueprint'
            }
        :return: `ClusterHosts` instance
        """
        if self.client.version < (2,0,0):
            for host_info in hosts:
                self.create(host_info.pop('host_name'), **host_info)
        else:
            # get the Request object
            self.load(self.client.post(self.url, json=json.dumps(hosts)))
            # rebuild the list with the new additions
            self.refresh()

        return self

    def wait(self, **kwargs):
        super(ClusterHosts, self).wait(**kwargs)
        for host in self._models:
            host.wait()


class ClusterAlert(base.QueryableModel):
    min_version = (2,0,0)
    path = 'alerts'
    data_key = 'Alert'
    primary_key = 'id'
    fields = ('id', 'cluster_name', 'component_name', 'definition_id', 'definition_name',
              'host_name', 'instance', 'label', 'latest_timestamp', 'maintenance_state',
              'original_timestamp', 'scope', 'service_name', 'state', 'text')


class ClusterHost(Host):
    collection_class = ClusterHosts

    relationships = {
        'alert_history': AlertHistory,
        'alerts': ClusterAlert,
        'components': HostComponent,
    }

    def load(self, response):
        # remove the old 'alerts' response that isn't the related Alert objects
        if 'alerts' in response and isinstance(response['alerts'], dict):
            del response['alerts']
        return super(ClusterHost, self).load(response)

    def create(self, *args, **kwargs):
        if self.client.version < (2,0,0):
            host_group_name = kwargs.pop('host_group')
            blueprint_name = kwargs.pop('blueprint')
            super(ClusterHost, self).create(*args, **kwargs)
            # the API doesn't have a way to just add a host to a host_group
            # so we handle the logic here to make it easier on the user
            if host_group_name and blueprint_name:
                bp = self.client.blueprints(blueprint_name)
                host_group = next(x for x in bp.host_groups if x.name == host_group_name)
                for component in host_group.components:
                    url = self.parent.url + "?Hosts/host_name=%s" % self.host_name
                    self.client.post(url, data={
                        "host_components": [{
                            "HostRoles": {
                                "component_name": component['name'],
                            },
                        }],
                    })

            return self
        else:
            # 2.0.0 added the ability to add hosts to host_groups in the API, but the 'host_name'
            # is part of the payload, not the URL
            self.load(self.client.post(self.parent.url, data=kwargs))
            self.refresh()

    @property
    def maintenance(self):
        return HostMaintenance(self)


class TaskAttempt(base.QueryableModel):
    path = 'taskattempts'
    data_key = 'TaskAttempt'
    primary_key = ''
    fields = ()


class Job(base.QueryableModel):
    path = 'jobs'
    data_key = 'Job'
    primary_key = ''
    fields = ()
    relationships = {
        'taskattempts': TaskAttempt,
    }


class Workflow(base.QueryableModel):
    path = 'workflows'
    data_key = 'Workflow'
    primary_key = ''
    fields = ()
    relationships = {
        'jobs': Job,
    }


class Service(base.QueryableModel):
    path = 'services'
    data_key = 'ServiceInfo'
    primary_key = 'service_name'
    fields = ('service_name', 'cluster_name', 'maintenance_state', 'state')


class ClusterServiceCollection(base.QueryableModelCollection):
    def start(self):
        """Start all services on a cluster."""
        self.load(self.client.put(self.url, data={
            "RequestInfo": {
                "context": "_PARSE_.START.ALL_SERVICES",
                "operation_level": {
                    "level": "CLUSTER",
                    "cluster_name": self.parent.cluster_name
                }
            },
            "Body": {
                "ServiceInfo": {
                    "state": "STARTED"
                }
            }
        }))
        return self.request

    def stop(self):
        """Stop all services on a cluster."""
        self.load(self.client.put(self.url, data={
            "RequestInfo": {
                "context": "_PARSE_.STOP.ALL_SERVICES",
                "operation_level": {
                    "level": "CLUSTER",
                    "cluster_name": self.parent.cluster_name
                }
            },
            "Body": {
                "ServiceInfo": {
                    "state": "INSTALLED"
                }
            }
        }))
        return self.request


class ClusterService(Service):
    collection_class = ClusterServiceCollection
    relationships = {
        'alert_history': AlertHistory,
        'alerts': ClusterAlert,
        'components': ClusterServiceComponent,
    }

    def restart(self, component_names=None):
        """Restarts components of this service, if already installed and started."""

        components = self.components
        if component_names:
            components = components(component_names)

        resource_filters = []
        for component in components:
            hosts = [hc.host_name for hc in component.host_components]
            if hosts:
                resource_filters.append({
                    "service_name": self.service_name,
                    "component_name": component.component_name,
                    "hosts": ','.join(hosts),
                })

        if resource_filters:
            self.load(self.client.post(self.cluster.requests.url, data={
                "RequestInfo": {
                    "command": "RESTART",
                    "context": "Restart all components for %s" % normalize_underscore_case(
                        self.service_name),
                    "operation_level": {
                        "level": "SERVICE",
                        "cluster_name": self.cluster_name,
                        "service_name": self.service_name,
                    },
                },
                "Requests/resource_filters": resource_filters,
            }))
        return self

    def start(self, component_names=None):
        """Starts this service."""
        self.load(self.client.put(self.url, data={
            "RequestInfo": {
                "context": "_PARSE_.START.%s" % self.service_name,
                "operation_level": {
                    "level": "SERVICE",
                    "cluster_name": self.cluster_name,
                    "service_name": self.service_name,
                }
            },
            "Body": {
                "ServiceInfo": {"state": "STARTED"},
            },
        }))
        return self

    def stop(self, component_names=None):
        """Stops this service."""
        self.load(self.client.put(self.url, data={
            "RequestInfo": {
                "context": "_PARSE_.STOP.%s" % self.service_name,
                "operation_level": {
                    "level": "SERVICE",
                    "cluster_name": self.cluster_name,
                    "service_name": self.service_name,
                }
            },
            "Body": {
                "ServiceInfo": {"state": "INSTALLED"},
            },
        }))
        return self


class ConfigurationItemCollection(base.QueryableModelCollection):
    @property
    def url(self):
        return self.parent.url

    def create(self, tag=None, properties_to_update=None, **kwargs):
        """Update properties or create new Cluster configuration.

        Args:
            tag (:obj:`str`, optional): Configuration tag to use.
                Default: timestamp
            properties_to_update (:obj:`dict`, optional): Configuration properties to update. Keyword argument
                `properties` is ignored if this is provided. Default: ``None``
            **kwargs: Configuration items to set.

        Returns:
            A :obj:`ConfigurationItemCollection` self
        """
        # support for create(properties_to_update='{"hadoop.proxyuser.xyz.groups" : "*"}')
        # a PUT to "http://localhost:8080/api/v1/clusters/cluster"
        # in format as: [{"Clusters":{"desired_config":[{"type":"core-site", "tag":"somrandchars",
        #                                                "properties":{"hadoop.proxyuser.xyz.groups" : "*", ... }]}}]
        new_tag = tag or str(time.time())
        new_item = {'Clusters': {'desired_config': [{'type': self.parent.type, 'tag': new_tag}]}}

        if properties_to_update:
            current_tag = self.parent.cluster.desired_configs[self.parent.type]['tag']
            self.inflate()
            current_item = {}
            for model in self._models:
                if model.tag == current_tag:
                    current_item = (model.items[0] if (model.items and len(model.items) > 0) else None)
                    break

            for key, value in current_item.items():
                if key.upper() not in ('VERSION', 'CONFIG', 'TYPE', 'TAG', 'HREF'):
                    new_item['Clusters']['desired_config'][0][key] = value

            if 'properties' in new_item['Clusters']['desired_config'][0]:
                new_item['Clusters']['desired_config'][0]['properties'].update(properties_to_update)
            else:
                new_item['Clusters']['desired_config'][0]['properties'] = properties_to_update
            kwargs.pop('properties', None)

        new_item['Clusters']['desired_config'][0].update(kwargs)
        self.client.put(self.parent.cluster.url, json=json.dumps(new_item))

        return self.refresh()


class ConfigurationItem(base.QueryableModel):
    primary_key = 'tag'
    collection_class = ConfigurationItemCollection
    fields = ('tag', 'version', 'items')

    @property
    def url(self):
        url = '{}&tag={}'.format(self.parent.url, self._data['tag'])
        return url


class Configuration(base.QueryableModel):
    path = 'configurations'
    use_key_prefix = False
    data_key = 'Config'
    primary_key = 'type'
    fields = ('cluster_name', 'tag', 'type', 'version', 'properties')
    relationships = {
        'items': ConfigurationItem
    }

    def load(self, response):
        # sigh, this API does not follow the pattern at all
        for field in self.fields:
            if field in response and field not in response[self.data_key]:
                response[self.data_key][field] = response.pop(field)
        return super(Configuration, self).load(response)

    @property
    def url(self):
        url = '{}?type={}'.format(self.parent.url, self._data['type'])
        return url


class UserPrivilege(base.GeneratedIdentifierMixin, base.QueryableModel):
    path = 'privileges'
    data_key = 'PrivilegeInfo'
    primary_key = 'privilege_id'
    fields = ('privilege_id', 'permission_name', 'principal_name',
              'principal_type', 'type', 'user_name', 'cluster_name')


class ClusterAlertDefinition(base.QueryableModel):
    min_version = (2,0,0)
    path = 'alert_definitions'
    data_key = 'AlertDefinition'
    primary_key = 'id'
    fields = ('id', 'cluster_name', 'component_name', 'description', 'enabled', 'ignore_host',
              'interval', 'label', 'name', 'scope', 'service_name', 'source')


class ClusterAlertGroup(base.QueryableModel):
    min_version = (2,0,0)
    path = 'alert_groups'
    data_key = 'AlertGroup'
    primary_key = 'id'
    fields = ('id', 'cluster_name', 'default', 'definition', 'name', 'targets')


class ClusterAlertNotice(base.QueryableModel):
    min_version = (2,0,0)
    path = 'alert_notices'
    data_key = 'AlertNotice'
    primary_key = 'id'
    fields = ('id', 'cluster_name', 'history_id', 'notification_state', 'service_name',
              'target_id', 'target_name', 'uuid')


class ClusterUpgradeItem(base.PollableMixin, base.GeneratedIdentifierMixin, base.QueryableModel):
    min_version = (2,0,0)
    path = 'upgrade_items'
    data_key = 'UpgradeItem'
    primary_key = 'stage_id'
    fields = ('stage_id', 'context', 'status', 'cluster_host_info', 'cluster_name',
              'command_params', 'end_time', 'group_id', 'host_params', 'log_info',
              'progress_percent', 'request_id', 'skippable', 'start_time', 'text')

    relationships = {
        'tasks': Task,
    }

    def execute(self):
        return self.update(status='COMPLETED')

    def abort(self):
        return self.update(status='ABORTED')

    def retry(self):
        return self.update(status='PENDING')

    def skip(self):
        if not self.skippable:
            raise exceptions.BadRequest("Upgrade Item is not skippable")

        if self.status == 'HOLDING_TIMEDOUT':
            return self.update(status='TIMEDOUT')

        return self.update(status='FAILED')

    @property
    def has_failed(self):
        return self.status not in ('PENDING', 'COMPLETED')

    @property
    def is_finished(self):
        return True if int(self.progress_percent) == 100 else False


class ClusterUpgradeItemGroup(base.PollableMixin, base.GeneratedIdentifierMixin,
                              base.QueryableModel):
    min_version = (2,0,0)
    path = 'upgrade_groups'
    data_key = 'UpgradeGroup'
    primary_key = 'group_id'
    fields = ('group_id', 'title', 'progress_percent', 'completed_task_count', 'group_id',
              'in_progress_task_count', 'name', 'request_id', 'status', 'total_task_count')

    relationships = {
        'items': ClusterUpgradeItem,
    }

    @property
    def has_failed(self):
        return self.status not in ('PENDING', 'COMPLETED')

    @property
    def is_finished(self):
        return True if int(self.progress_percent) == 100 else False


class ClusterUpgrade(base.PollableMixin, base.GeneratedIdentifierMixin, base.QueryableModel):
    min_version = (2,0,0)
    path = 'upgrades'
    data_key = 'Upgrade'
    primary_key = 'request_id'
    fields = ('request_id', 'cluster_name', 'create_time', 'direction', 'end_time', 'exclusive',
              'from_version', 'to_version', 'progress_percent', 'request_context',
              'request_status', 'start_time', 'type', 'repository_version')

    relationships = {
        'groups': ClusterUpgradeItemGroup,
    }

    @property
    def has_failed(self):
        return self.status not in ('PENDING', 'COMPLETED')

    @property
    def is_finished(self):
        return True if int(self.progress_percent) == 100 else False


class Cluster(base.QueryableModel):
    path = 'clusters'
    data_key = 'Clusters'
    primary_key = 'cluster_name'
    fields = ('cluster_id', 'cluster_name', 'health_report', 'provisioning_state',
              'total_hosts', 'version', 'desired_configs',
              'desired_service_config_versions')
    relationships = {
        'alerts': ClusterAlert,
        'alert_definitions': ClusterAlertDefinition,
        'alert_groups': ClusterAlertGroup,
        'alert_history': AlertHistory,
        'alert_notices': ClusterAlertNotice,
        'hosts': ClusterHost,
        'host_components': HostComponent,
        'requests': Request,
        'services': ClusterService,
        'configurations': Configuration,
        'privileges': UserPrivilege,
        'upgrades': ClusterUpgrade,
        # the workflows API doesn't appear to do anything yet
        # 'workflows': Workflow,
    }

    @property
    def stack(self):
        """Finds the stack object that was used in the blueprint for this cluster"""
        (stack_name, stack_version) = self.version.split('-')
        return self.client.stacks(stack_name).versions(stack_version)

    def load(self, response):
        # remove the old 'alerts' response that isn't the related Alert objects
        if 'alerts' in response and isinstance(response['alerts'], dict):
            del response['alerts']
        return super(Cluster, self).load(response)

    def execute_action(self, action, context, parameters=None, hosts=None):
        """Execute a custom action on the cluster.

        The custom action gets executed on the specified hosts of the cluster.

        :param action: Custom action name
        :param context: Context name for the specific request
        :param parameters: Dictionary of input parameters that are supported by
                           the custom script
        :param hosts: Comma separated list of hosts to run the action on
        :return: Current status of the request
        """
        self.load(self.client.post(self.cluster.requests.url, data={
            "RequestInfo": {
                "action": action,
                "context": context,
                "parameters": parameters
            },
            "Requests/resource_filters": [{
                "hosts": hosts,
            }],
        }))
        return self.request

    def decommission(self, service, hosts):
        self.commission(service, hosts, "decommission")

    def recommission(self, service, hosts):
        self.commission(service, hosts, "recommission")
        """Nodemanager recommission does not start nodemanager process on the host. so its required to do it separately"""
        if service is "YARN":
            for host in hosts:
                self.hosts(host).components("NODEMANAGER").start()

    def commission(self, service, hosts, commission_type):
        """Decommission/Recommission slave components on a cluster.

        This should make it safe to remove these hosts from the cluster.

        :param service: The name of the service that the components are for
        :param hosts: Comma separated list of hosts to decommission/recommission
        :param commission_type: type of commission decommission or recommission
        :return: Current status of the request
        """

        components = {
            'YARN': {'slave': 'NODEMANAGER', 'master': 'RESOURCEMANAGER'},
            'HDFS': {'slave': 'DATANODE', 'master': 'NAMENODE'},
            'HBASE': {'slave': 'HBASE_REGIONSERVER', 'master': 'HBASE_MASTER'},
        }

        desired_admin_state = {
            "decommission" : "DECOMMISSIONED",
            "recommission" : "LIVE"
        }

        include_or_exclude_hosts = "excluded_hosts" if commission_type == "decommission" else "included_hosts"

        if service not in components:
            raise ValueError("{0} is not a valid service to {1}".format(service, commission_type))

        slave = components[service]['slave']
        # filter off hosts where the slave component is already decommissioned
        hosts = [host for host in hosts
                 if self.hosts(host).components(slave).desired_admin_state != desired_admin_state[commission_type]]
        if len(hosts) == 0:
            # no action required, all hosts are already decommissioned
            return self

        operation_level = {
            "level": "HOST_COMPONENT",
            "cluster_name": self.cluster_name
        }
        if len(hosts) == 1:
            # if there's only one host, it requires a more specific operation_level
            operation_level.update({
                "host_name": hosts[0],
                "service_name": service
            })
        self.load(self.client.post(self.cluster.requests.url, data={
            "RequestInfo": {
                "command": "DECOMMISSION",
                "context": "Decommission {0}".format(normalize_underscore_case(slave)),
                "parameters": {"slave_type": slave, include_or_exclude_hosts: ','.join(hosts)},
                "operation_level": operation_level,
            },
            "Requests/resource_filters": [{
                "service_name": service,
                "component_name": components[service]['master'],
            }],
        }))
        return self

    def restart_stale_config_components(self, context=None):
        """Restart all required components resulting from stale configs"""
        self.load(self.client.post(self.cluster.requests.url, data={
            "RequestInfo": {
                "context": (context or 'Restart All Required'),
                "operation_level": "host_component",
                "command": "RESTART"
            },
            "Requests/resource_filters": [{
                "hosts_predicate": "HostRoles/stale_configs=true"
            }],
        }))
        return self.request


class BlueprintHostGroup(base.DependentModel):
    fields = ('name', 'configurations', 'components', 'cardinality')
    primary_key = 'name'


class Blueprint(base.QueryableModel):
    path = 'blueprints'
    data_key = 'Blueprints'
    primary_key = 'blueprint_name'
    fields = ('blueprint_name', 'stack_name', 'stack_version')
    relationships = {
        'host_groups': BlueprintHostGroup,
    }


class StackServiceComponent(Component):
    data_key = 'StackServiceComponents'
    primary_key = 'component_name'
    fields = ('component_name', 'service_name', 'stack_name', 'stack_version',
              'cardinality', 'component_category', 'custom_commands',
              'display_name', 'is_client', 'is_master')


class StackConfigurationProperty(base.QueryableModel):
    path = 'configurations'
    data_key = 'StackConfigurations'
    primary_key = 'property_name'
    fields = ('property_name', 'service_name', 'stack_name', 'stack_version',
              'final', 'property_description', 'property_type', 'property_value',
              'type')


class StackConfiguration(base.QueryableModel):
    path = 'configurations'

    def __init__(self, *args, **kwargs):
        super(StackConfiguration, self).__init__(*args, **kwargs)
        self._properties = []
        self._iter_marker = 0

    def __iter__(self):
        self.inflate()
        self._iter_marker = 0
        return self

    def next(self):
        if self._iter_marker >= len(self._properties):
            raise StopIteration
        model = self._properties[self._iter_marker]
        self._iter_marker += 1
        return model

    def load(self, response):
        self._properties = []
        # we either get a single item or a list of items.  WTF Ambari devs?
        if isinstance(response, list):
            for item in response:
                model = StackConfigurationProperty(self.parent)
                model.load(item)
                self._properties.append(model)
        else:
            model = StackConfigurationProperty(self.parent)
            model.load(response)
            self._properties.append(model)

    def to_dict(self):
        self.inflate()
        return { 'files': [x.to_dict() for x in self._properties] }


class StackService(base.QueryableModel):
    path = 'services'
    data_key = 'StackServices'
    primary_key = 'service_name'
    fields = ('service_name', 'stack_name', 'stack_version', 'display_name',
              'comments', 'custom_commands', 'required_services',
              'service_check_supported', 'service_version', 'user_name',
              'config_types')
    relationships = {
        'components': StackServiceComponent,
        'configurations': StackConfiguration,
    }

    def can(self, action):
        """Determine whether or not this service can execute a specific custom action

        Example:

        if service.can('DECOMMISSION'):
            cluster.decommission(service.service_name)
        """
        if action in self.custom_commands:
            return True
        for component in self.components(is_master=True):
            if action in component.custom_commands:
                return True
        return False


class Repository(base.QueryableModel):
    path = 'repositories'
    data_key = 'Repositories'
    primary_key = 'repo_id'
    fields = ('repo_id', 'repo_name', 'os_type', 'stack_name', 'stack_version',
              'base_url', 'default_base_url', 'latest_base_url', 'mirrors_list', 'verify_base_url')


class OperatingSystem(base.QueryableModel):
    path = 'operating_systems'
    data_key = 'OperatingSystems'
    primary_key = 'os_type'
    fields = ('os_type', 'stack_name', 'stack_version')
    relationships = {
        'repositories': Repository,
    }


class Version(base.QueryableModel):
    path = 'versions'
    data_key = 'Versions'
    primary_key = 'stack_version'
    fields = ('stack_name', 'stack_version', 'active', 'min_upgrade_version',
              'parent_stack_version', 'config_types')
    relationships = {
        'operating_systems': OperatingSystem,
        'services': StackService,
    }


class Stack(base.QueryableModel):
    path = 'stacks'
    data_key = 'Stacks'
    primary_key = 'stack_name'
    fields = ('stack_name')
    relationships = {
        'versions': Version,
    }


class User(base.QueryableModel):
    path = 'users'
    data_key = 'Users'
    primary_key = 'user_name'
    fields = ('user_name', 'active', 'admin', 'groups', 'ldap_user', 'password', 'old_password')
    relationships = {
        'privileges': UserPrivilege,
    }


class GroupMember(base.QueryableModel):
    path = 'members'
    data_key = 'MemberInfo'
    primary_key = 'user_name'
    fields = ('user_name', 'group_name')


class Group(base.QueryableModel):
    path = 'groups'
    data_key = 'Groups'
    primary_key = 'group_name'
    fields = ('group_name', 'ldap_group')
    relationships = {
        'members': GroupMember,
    }


class ViewPermission(base.QueryableModel):
    path = 'permissions'
    data_key = 'PermissionInfo'
    primary_key = 'permission_id'
    fields = ('permission_id', 'version', 'view_name', 'permission_name',
              'resource_name')


class ViewPrivilegeCollection(base.QueryableModelCollection):
    def create(self, *args, **kwargs):
        """This collection requires you to PUT the entire collection every time you add to it"""

        fields = ('principal_type', 'principal_name', 'permission_name')

        def uniquify(model):
            """
            We don't want to create duplicate privileges, but we can't rely on the id for
            uniqueness because it doesn't exist for new entries yet
            """
            return ':'.join([getattr(model, field) for field in fields])

        new_privileges = {}
        model = self.model_class(self, data=kwargs)
        data_key = {}
        for field in fields:
            data_key[field] = getattr(model, field)
        new_privileges[uniquify(model)] = {
            model.data_key: data_key
        }

        self.inflate()
        for model in self._models:
            # add in any existing ones that weren't in the "new" ones
            key = uniquify(model)
            if key not in new_privileges:
                new_privileges[key] = {
                    model.data_key: data_key
                }

        self.client.put(self.url, json=json.dumps(list(new_privileges.values())))
        return self.refresh()

    def delete(self):
        self.client.put(self.url, data=[])
        return self.refresh()


class ViewPrivilege(UserPrivilege):
    collection_class = ViewPrivilegeCollection
    fields = ('privilege_id', 'instance_name', 'view_name', 'version', 'permission_name',
              'principal_name', 'principal_type')

    def inflate(self):
        if self.primary_key not in self._data:
            return
        return super(ViewPrivilege, self).inflate()


class ViewResource(base.QueryableModel):
    data_key = 'ViewResource'
    path = 'resources'
    fields = ('name', 'instance_name', 'version', 'view_name')
    primary_key = 'name'

    def load(self, response):
        # sigh, this API does not follow the pattern at all
        # when you get a single instance, it returns a list of properties
        if isinstance(response, list):
            self._data['properties'] = response
            return

        # but when you get a collection, it has the other fields at the top-level of each dict
        if self.data_key not in response:
            response[self.data_key] = {}
        for field in self.fields:
            if field in response and field not in response[self.data_key]:
                response[self.data_key][field] = response.pop(field)

        return super(ViewResource, self).load(response)


class ViewInstance(base.QueryableModel):
    path = 'instances'
    data_key = 'ViewInstanceInfo'
    primary_key = 'instance_name'
    fields = ('instance_name', 'context_path', 'description', 'icon64_path',
              'icon_path', 'label', 'static', 'version', 'view_name', 'visible',
              'instance_data', 'properties', 'cluster_handle')

    relationships = {
        'privileges': ViewPrivilege,
        'resources': ViewResource,
    }


class ViewVersion(base.QueryableModel):
    path = 'versions'
    data_key = 'ViewVersionInfo'
    primary_key = 'version'
    fields = ('version', 'view_name', 'archive', 'description', 'label',
              'masker_class', 'parameters', 'status', 'status_detail', 'system')
    relationships = {
        'permissions': ViewPermission,
        'instances': ViewInstance,
    }


class View(base.QueryableModel):
    path = 'views'
    data_key = 'ViewInfo'
    primary_key = 'view_name'
    fields = ('view_name')
    relationships = {
        'versions': ViewVersion,
    }

class RootServiceHostComponents(Component):
    collection_class = HostComponentCollection
    path = 'hostComponents'
    data_key = 'RootServiceHostComponents'
    fields = ('component_name', 'host_name', 'service_name')

class RootServiceComponent(Component):
    path = 'components'
    data_key = 'RootServiceComponents'
    relationships = {
        'host_components': RootServiceHostComponents,
    }

class RootService(Service):
    data_key = 'RootService'
    fields = ('service_name')
    relationships = {
        'components': RootServiceComponent,
    }


class AlertTarget(base.QueryableModel, base.GeneratedIdentifierMixin):
    min_version = (2,0,0)
    path = 'alert_targets'
    data_key = 'AlertTarget'
    primary_key = 'id'
    fields = ('name', 'description', 'notification_type', 'global', 'properties', 'alert_states')

    @events.evented
    def create(self, validate=False, **kwargs):
        """Create a new alert target.

        :param validate: If `True`, test the target against the alerting backend before creating.
            Will throw an exception if a test alert fails, e.g. the server is unable to connect to
            the SMTP server for the `EMAIL` notification type.
        :returns: A new instance of AlertTarget
        """
        if self.primary_key in kwargs:
            del kwargs[self.primary_key]
        data = self._generate_input_dict(**kwargs)
        self.load(self.client.post(self.url, params={'validate_config': bool(validate)}, data=data))
        return self
