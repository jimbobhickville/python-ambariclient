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


def test_normalize_camel_case():
    assert(utils.normalize_camel_case('camelCase') == 'Camel Case')
    assert(utils.normalize_camel_case('CamelCase') == 'Camel Case')
    assert(utils.normalize_camel_case('camelcase') == 'Camelcase')
    assert(utils.normalize_camel_case('camelcasE') == 'Camelcas E')
    assert(utils.normalize_camel_case('CAMELCASE') == 'CAMELCASE')
    assert(utils.normalize_camel_case('cAMELCASE') == 'C AMELCASE')
    assert(utils.normalize_camel_case('camelCaseTrio') == 'Camel Case Trio')

def test_normalize_underscore_case():
    assert(utils.normalize_underscore_case('underscore_case') == 'Underscore Case')
    assert(utils.normalize_underscore_case('UNDERSCORE_CASE') == 'Underscore Case')
    assert(utils.normalize_underscore_case('UnderScore_Case') == 'Underscore Case')
    assert(utils.normalize_underscore_case('underscoreCase') == 'Underscorecase')
    assert(utils.normalize_underscore_case('underscore_case_trio') == 'Underscore Case Trio')

def test_version_tuple():
    assert(utils.version_tuple('1.7.0') == (1, 7, 0))
    assert(utils.version_tuple((1, 7, 0)) == (1, 7, 0))
    with pytest.raises(ValueError):
        utils.version_tuple('One Seven Zero')

def test_version_str():
    assert(utils.version_str('1.7.0') == '1.7.0')
    assert(utils.version_str((1, 7, 0)) == '1.7.0')
    with pytest.raises(ValueError):
        utils.version_str(('One', 'Seven', 'Zero'))

def test_generate_base_url():
    assert(utils.generate_base_url('http://www.example.com/') == 'http://www.example.com:80')
    assert(utils.generate_base_url('http://www.example.com/some/thing') ==
           'http://www.example.com:80')
    assert(utils.generate_base_url('https://www.example.com:8080/') ==
           'https://www.example.com:8080')
    assert(utils.generate_base_url('http://www.example.com') == 'http://www.example.com:80')
    assert(utils.generate_base_url('https://www.example.com') == 'https://www.example.com:443')
    assert(utils.generate_base_url('https://www.example.com:9090') ==
           'https://www.example.com:9090')
    assert(utils.generate_base_url('www.example.com', protocol='http') ==
           'http://www.example.com:80')
    assert(utils.generate_base_url('www.example.com', protocol='https') ==
           'https://www.example.com:443')
    assert(utils.generate_base_url('www.example.com', protocol='https', port=9090) ==
           'https://www.example.com:9090')
    assert(utils.generate_base_url('www.example.com', port=9090) ==
           'http://www.example.com:9090')
    assert(utils.generate_base_url('www.example.com:9090', protocol='https') ==
           'https://www.example.com:9090')
    assert(utils.generate_base_url('www.example.com:9090') ==
           'http://www.example.com:9090')
    with pytest.raises(ValueError):
        utils.generate_base_url('ftp://www.example.com')
    with pytest.raises(ValueError):
        utils.generate_base_url('www.example.com', protocol='ftp')
    with pytest.raises(ValueError):
        utils.generate_base_url('www.example.com', port='foo')
    with pytest.raises(ValueError):
        utils.generate_base_url('www.example.com:foo')
