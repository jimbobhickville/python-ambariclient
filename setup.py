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

import setuptools

setuptools.setup(
    name="python-ambariclient",
    version=0.1,
    author="Rackspace",
    author_email="greg.hill@rackspace.com",
    description="Client library for Apache Ambari.",
    url="https://www.github.com/rackerlabs/python-ambariclient",
    packages=setuptools.find_packages(exclude=['tests', 'tests.*']),
    install_requires=['requests'],
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Intended Audience :: Information Technology",
        "License :: Apache 2 License",
        "Operating System :: OS Independent",
        "Programming Language :: Python"
    ],
)
