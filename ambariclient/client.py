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

import copy
import functools
import io
import json
import logging
import tarfile

import requests

from ambariclient import models, utils, base, exceptions
from ambariclient.exceptions import handle_response

LOG = logging.getLogger(__name__)
LOG.addHandler(utils.NullHandler())

# this defines where the Ambari client delegates to for actual logic
ENTRY_POINTS = {
    'actions': models.Action,
    'alert_targets': models.AlertTarget,
    'blueprints': models.Blueprint,
    'bootstrap': models.Bootstrap,
    'clusters': models.Cluster,
    'groups': models.Group,
    'hosts': models.Host,
    'services': models.RootService,
    'stacks': models.Stack,
    'users': models.User,
    'views': models.View,
}


class Ambari(object):
    """The Ambari client

    This is the entry point to the Ambari API. Create this client and then
    use one of the entry points to start hitting Ambari object collections.

    Ex:

    client = Ambari('localhost', port=8080, username='admin', password='admin')
    for host in client.hosts:
        host.maintenance.enable()

    client.clusters.create('my-cluster', blueprint='my-blueprint', host_groups=[...])

    for component in client.clusters('my-cluster').services('HBASE').components:
        print component.to_dict()

    """
    def __init__(self, host, port=None, username=None, password=None,
                 identifier=None, protocol=None, validate_ssl=True,
                 timeout=10, max_retries=5):

        self.base_url = utils.generate_base_url(host, port=port, protocol=protocol)

        if identifier is None:
            identifier = 'python-ambariclient'

        self.client = HttpClient(host=self.base_url, username=username,
                                 password=password, identifier=identifier,
                                 validate_ssl=validate_ssl, timeout=timeout,
                                 max_retries=max_retries)
        self._version = None

    def __dir__(self):
        return self.__dict__.keys() + ENTRY_POINTS.keys()

    def check_version(self):
        if self.version < base.OLDEST_SUPPORTED_VERSION:
            raise exceptions.ClientError(
                "Version %s unsupported, must be %s or higher"
                % (utils.version_str(self.version),
                   utils.version_str(base.OLDEST_SUPPORTED_VERSION)))
        return

    @property
    def version(self):
        if self._version is None:
            version_str = str(
                self.services('AMBARI').components('AMBARI_SERVER').component_version
            )
            self._version = utils.version_tuple(version_str)
        return self._version

    def __getattr__(self, attr):
        if attr in ENTRY_POINTS:
            rel_class = ENTRY_POINTS[attr]
            return rel_class.collection_class(self, rel_class)

        if getattr(requests, attr):
            # forward get/post/put/head/delete to the http client
            return getattr(self.client, attr)

        raise AttributeError(attr)


class HttpClient(object):
    """Our HTTP based REST client.

    It handles some of the dirty work like automatic serialization/deserialization
    of JSON data, converting error responses to exceptions, etc.  For the most
    part it should mimic a requests client. You can call methods like get, post,
    put, delete, and head and expect them to work the same way.  But instead of
    a response object, you get a dictionary.  A response of None means no response
    was supplied by the API.  This should be uncommon except for error cases, but
    cases do exist either due to Ambari bugs or other mitigating circumstances.
    """
    def __init__(self, host, username, password, identifier, validate_ssl=True,
                 timeout=10, max_retries=5):

        self.request_params = {
            'headers': {'X-Requested-By': identifier},
            'auth': (username, password),
            'verify': validate_ssl,
            'timeout': timeout,
        }
        # automatically retry requests on connection errors
        self.session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(max_retries=max_retries)
        self.session.mount(host, adapter)

    def request(self, method, url, content_type=None, **kwargs):
        # doing it this way keeps the magic for following redirects intact
        requests_method = getattr(self.session, method)
        params = copy.deepcopy(self.request_params)
        params.update(kwargs)

        if content_type is not None:
            params['headers']['Content-type'] = content_type
        LOG.debug("Request headers: %s", params['headers'])

        if 'data' in params and isinstance(params['data'], dict):
            params['data'] = json.dumps(params['data'], cls=AmbariJsonEncoder)
            LOG.debug("Request body: %s", params['data'])

        response = requests_method(url, **params)

        # any error responses will generate exceptions here
        handle_response(response)

        LOG.debug("Response headers: %s", response.headers)
        LOG.debug("Response: %s", response.text)

        if response.headers.get('content-length') is None:
            # Log bad methods so we can report them
            LOG.debug("Missing content-length for %s %s: %s", method,
                      url, response.headers.get('content-type'))

        # there is no consistent way to determine response type
        # so assume json if it's not an empty string
        if len(response.text) > 0:
            if 'application/x-ustar' in response.headers.get('content-type'):
                tarstream = io.BytesIO(response.content)
                tarstream.seek(0)
                return tarfile.open(fileobj=tarstream)
            elif 'application/json' not in response.headers.get('content-type'):
                # Log bad methods so we can report them
                LOG.debug("Wrong response content-type for %s %s: %s", method,
                          url, response.headers.get('content-type'))
            return response.json()

        return {}

    def __getattr__(self, attr):
        if getattr(requests, attr):
            return functools.partial(self.request, attr)
        raise AttributeError(attr)


class AmbariJsonEncoder(json.JSONEncoder):
    """Converts Ambari model objects into dictionaries that can be JSON-encoded

    This allows for passing in models and ModelCollections into related objects'
    create/update methods and having it handle the conversion automatically.
    """
    def default(self, obj):  # pylint: disable=method-hidden
        if isinstance(obj, base.ModelCollection):
            dicts = []
            for model in obj:
                dicts.append(model.to_json_dict())
            return dicts
        elif isinstance(obj, base.Model):
            return obj.to_json_dict()
        # Let the base class default method raise the TypeError
        return super(AmbariJsonEncoder, self).default(obj)
