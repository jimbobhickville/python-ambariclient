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

import pytest
from ambariclient import utils


@pytest.mark.parametrize("original,expected", [
    ('camelCase', 'Camel Case'),
    ('CamelCase', 'Camel Case'),
    ('camelcase', 'Camelcase'),
    ('camelcasE', 'Camelcas E'),
    ('CAMELCASE', 'CAMELCASE'),
    ('cAMELCASE', 'C AMELCASE'),
    ('camelCaseTrio', 'Camel Case Trio'),
])
def test_normalize_camel_case(original, expected):
    assert utils.normalize_camel_case(original) == expected

@pytest.mark.parametrize("original,expected", [
    ('underscore_case', 'Underscore Case'),
    ('UNDERSCORE_CASE', 'Underscore Case'),
    ('UnderScore_Case', 'Underscore Case'),
    ('underscoreCase', 'Underscorecase'),
    ('underscore_case_trio', 'Underscore Case Trio'),
])
def test_normalize_underscore_case(original, expected):
    assert utils.normalize_underscore_case(original) == expected

@pytest.mark.parametrize("original,expected", [
    ('1.7.0', (1, 7, 0)),
    ((1, 7, 0), (1, 7, 0)),
])
def test_version_tuple(original, expected):
    assert utils.version_tuple(original) == expected

@pytest.mark.parametrize("original,exc", [
    ('One Seven Zero', ValueError),
])
def test_version_tuple_exc(original, exc):
    pytest.raises(exc, utils.version_tuple, original)

@pytest.mark.parametrize("original,expected", [
    ((1, 7, 0), '1.7.0'),
    ('1.7.0', '1.7.0'),
])
def test_version_str(original, expected):
    assert utils.version_str(original) == expected

@pytest.mark.parametrize("original,exc", [
    (('One', 'Seven', 'Zero'), ValueError),
])
def test_version_str_exc(original, exc):
    pytest.raises(exc, utils.version_str, original)

@pytest.mark.parametrize("host,protocol,port,expected", [
    ('http://www.example.com/', None, None, 'http://www.example.com:80'),
    ('http://www.example.com/some/thing', None, None, 'http://www.example.com:80'),
    ('https://www.example.com:8080/', None, None, 'https://www.example.com:8080'),
    ('http://www.example.com', None, None, 'http://www.example.com:80'),
    ('https://www.example.com', None, None, 'https://www.example.com:443'),
    ('https://www.example.com:9090', None, None, 'https://www.example.com:9090'),
    ('www.example.com', 'http', None, 'http://www.example.com:80'),
    ('www.example.com', 'https', None, 'https://www.example.com:443'),
    ('www.example.com', 'https', 9090, 'https://www.example.com:9090'),
    ('www.example.com', None, 9090, 'http://www.example.com:9090'),
    ('www.example.com:9090', 'https', None, 'https://www.example.com:9090'),
    ('www.example.com:9090', None, None, 'http://www.example.com:9090'),
])
def test_generate_base_url(host, protocol, port, expected):
    assert utils.generate_base_url(host, protocol=protocol, port=port) == expected

@pytest.mark.parametrize("exc,host,protocol,port", [
    (ValueError, 'ftp://www.example.com', None, None),
    (ValueError, 'www.example.com', 'ftp', None),
    (ValueError, 'ftp://www.example.com', None, 'foo'),
    (ValueError, 'www.example.com:foo', None, None),
])
def test_generate_base_url_exc(exc, host, protocol, port):
    pytest.raises(exc, utils.generate_base_url, host, protocol=protocol, port=port)
