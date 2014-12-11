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

import re


def normalize_underscore_case(name):
	"""Normalize an underscore-separated descriptor to something more readable.

	i.e. 'NAGIOS_SERVER' becomes 'Nagios Server', and 'host_components' becomes
    'Host Components'
	"""
	normalized = name.lower()
	normalized = re.sub('_(\w)', lambda match: ' ' + match.group(1).upper(),
                        normalized)
	return normalized[0].upper() + normalized[1:]


def normalize_camel_case(name):
    """Normalize a camelCase descriptor to something more readable.

    i.e. 'camelCase' or 'CamelCase' becomes 'Camel Case'
    """
    normalized = re.sub('([a-z])([A-Z])',
                        lambda match: ' '.join([match.group(1), match.group(2)]),
                        name)
    return normalized[0].upper() + normalized[1:]


def version_tuple(version):
    """Convert a version string or tuple to a tuple.

    Should be returned in the form: (major, minor, release).
    """
    if isinstance(version, str):
        return tuple(version.split('.'))
    elif isinstance(version, tuple):
        return version
    else:
        raise Exception("Invalid version: %s" % version)


def version_str(version):
    """Convert a version tuple or string to a string.

    Should be returned in the form: major.minor.release
    """
    if isinstance(version, str):
        return version
    elif isinstance(version, tuple):
        return '.'.join([str(x) for x in version])
    else:
        raise Exception("Invalid version: %s" % version)
