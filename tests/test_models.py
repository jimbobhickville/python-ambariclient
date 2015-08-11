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

from mock import patch, MagicMock
from ambariclient.client import Ambari


def test_lazy_loading():
    patch_method = 'ambariclient.client.HttpClient.request'
    with patch(patch_method, MagicMock(return_value={})) as http_request:
        client = Ambari('localhost')

        clusters = client.clusters
        assert http_request.call_count == 0, "Sent a request prior to inflation"

        clusters.inflate()
        assert http_request.call_count == 1, "inflating collection didn't hit the server"

        clusters('testcluster')
        assert http_request.call_count == 1, "getting a single cluster hit the server again"

        clusters('testcluster').inflate()
        assert http_request.call_count == 2, "inflating model didn't hit the server"

    with patch(patch_method, MagicMock(return_value={})) as http_request:
        client = Ambari('localhost')

        cluster = client.clusters('testcluster')
        assert http_request.call_count == 0, "getting model inflated collection"

        cluster.hosts
        assert http_request.call_count == 0, "accessing relationship on model inflated it"

        cluster.hosts.to_dict()
        assert http_request.call_count == 1, "to_dict on relationship didn't inflate it"

    with patch(patch_method, MagicMock(return_value={})) as http_request:
        client = Ambari('localhost')

        cluster = client.clusters('testcluster')
        assert http_request.call_count == 0, "getting model inflated collection"

        cluster.cluster_name
        assert http_request.call_count == 0, "accessing prepopulated field on model inflated it"

        cluster.health_report
        assert http_request.call_count == 1, "accessing field on model didn't inflate it"
