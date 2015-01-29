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

import argparse
import functools
import json
import logging
import os

from ambariclient.client import Ambari, ENTRY_POINTS
from ambariclient import events, base, models, utils

# TODO: override the logger level somehow
logging.basicConfig(level=logging.CRITICAL)
LOG = logging.getLogger(__name__)


def model_event(event, event_state, obj, **kwargs):
    line_end = "\n" if event_state == events.states.FINISHED else ""
    print "%s %s '%s': %s%s" % (utils.normalize_underscore_case(event),
                           utils.normalize_camel_case(obj.__class__.__name__),
                           obj.identifier, event_state, line_end)


def request_progress(request, **kwargs):
    print "Wait for %s: %.2f%%" % (request.request_context, request.progress_percent)


def request_done(request, **kwargs):
    print "Wait for %s: FINISHED\n" % (request.request_context)


def bootstrap_progress(bootstrap, **kwargs):
    hostnames = [x.host_name for x in bootstrap.hosts]
    print "Wait for Bootstrap Hosts %s: %s" % (hostnames, bootstrap.status)


def bootstrap_done(bootstrap, **kwargs):
    hostnames = [x.host_name for x in bootstrap.hosts]
    print "Wait for Bootstrap Hosts %s: FINISHED\n" % (hostnames)


def reference(model_class=None, stack=None):
    if stack is None:
        stack = ['ambari']

    if model_class:
        relationships = model_class.relationships
    else:
        relationships = ENTRY_POINTS

    for rel in sorted(relationships.keys()):
        new_stack = list(stack)
        new_stack.append(rel)
        print '.'.join(new_stack)
        rel_model_class = relationships[rel]
        if rel_model_class.primary_key is not None:
            new_stack[-1] = "%s(%s)" % (new_stack[-1], rel_model_class.primary_key)
            print '.'.join(new_stack)
            reference(model_class=rel_model_class, stack=new_stack)


def get_default_config():
    return {
        "host": "http://c6401.ambari.apache.org:8080",
        "username": "admin",
        "password": "admin"
    }


def parse_config_file():
    config_path = os.path.expanduser('~/.ambari')
    if os.path.isfile(config_path):
        with open(config_path, 'r') as config_file:
            return json.load(config_file)
    return {}


def parse_cli_opts():
    args = os.environ.get('AMBARI_SHELL_ARGS')
    if args:
        parser = argparse.ArgumentParser(prog='ambari-shell')
        parser.add_argument('--host',
                           help='hostname for the ambari server '
                                '(i.e. ambari.apache.org or http://ambari.apache.org:8080)')
        parser.add_argument('--port', type=int,
                           help='port for the ambari server '
                                '(can be included in the host)')
        parser.add_argument('--protocol', choices=['http', 'https'],
                           help='protocol for the ambari server '
                                '(can be included in the host)')
        parser.add_argument('--username',
                           help='username for the ambari server')
        parser.add_argument('--password',
                           help='password for the ambari server')
        opts = vars(parser.parse_args(args.split()))
        return {x: opts[x] for x in opts if opts[x] is not None}

    return {}


def log(level):
    logging.getLogger().setLevel(level)


def help():
    print "Ambari Shell Help"
    print " - log(new_level) will reset the logger level"
    print " - reference() will show you all available client method chains"


if os.environ.get('PYTHONSTARTUP', '') == __file__:
    for event in ['create', 'update', 'delete']:
        for event_state in [events.states.STARTED, events.states.FINISHED]:
            callback = functools.partial(model_event, event, event_state)
            events.subscribe(base.Model, event, callback, event_state)

    events.subscribe(models.Request, 'wait', request_progress, events.states.PROGRESS)
    events.subscribe(models.Request, 'wait', request_done, events.states.FINISHED)
    events.subscribe(models.Bootstrap, 'wait', bootstrap_progress, events.states.PROGRESS)
    events.subscribe(models.Bootstrap, 'wait', bootstrap_done, events.states.FINISHED)

    config = get_default_config()
    config.update(parse_config_file())
    config.update(parse_cli_opts())

    ambari = Ambari(**config)

    print "\nAmbari client available as 'ambari'"
    print " - Ambari Server is %s" % ambari.base_url
    print " - Ambari Version is %s\n" % utils.version_str(ambari.version)
    print "help() for help\n"
