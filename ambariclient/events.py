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

from collections import namedtuple
import logging
import inspect

LOG = logging.getLogger(__name__)

EVENT_HANDLERS = {}
state_list = ['ANY', 'STARTED', 'FAILED', 'FINISHED', 'PROGRESS']
states = namedtuple('EventStates', state_list)(*state_list)

def evented(method):
    def replacement(self, *args, **kwargs):
        publish(self, method.__name__, states.STARTED)
        try:
            return method(self, *args, **kwargs)
        except Exception:
            publish(self, method.__name__, states.FAILED)
            raise
        finally:
            publish(self, method.__name__, states.FINISHED)

    return replacement


def publish(obj, event, event_state, **kwargs):
    """Publish an event from an object.

    This is a really basic pub-sub event system to allow for tracking progress
    on methods externally.  It fires the events for the first match it finds in
    the object hierarchy, going most specific to least.  If no match is found
    for the exact event+event_state, the most specific event+ANY is fired
    instead.

    Multiple callbacks can be bound to the event+event_state if desired.  All
    will be fired in the order they were registered.
    """
    # short-circuit if nothing is listening
    if len(EVENT_HANDLERS) == 0:
        return

    if inspect.isclass(obj):
        pub_cls = obj
    else:
        pub_cls = obj.__class__
    potential = [x.__name__ for x in inspect.getmro(pub_cls)]

    # if we don't find a match for this event/event_state we fire the events
    # for this event/ANY instead for the closest match
    fallbacks = None
    callbacks = []
    for cls in potential:
        event_key = '.'.join([cls, event, event_state])
        backup_key = '.'.join([cls, event, states.ANY])
        if event_key in EVENT_HANDLERS:
            callbacks = EVENT_HANDLERS[event_key]
            break
        elif fallbacks is None and backup_key in EVENT_HANDLERS:
            fallbacks = EVENT_HANDLERS[backup_key]

    if fallbacks is not None:
        callbacks = fallbacks

    for callback in callbacks:
        callback(obj, **kwargs)
    return


def subscribe(obj, event, callback, event_state=None):
    """Subscribe an event from an class.

    Subclasses of the class/object will also fire events for this class,
    unless a more specific event exists.
    """
    if inspect.isclass(obj):
        cls = obj.__name__
    else:
        cls = obj.__class__.__name__

    if event_state is None:
        event_state = states.ANY

    event_key = '.'.join([cls, event, event_state])
    if event_key not in EVENT_HANDLERS:
        EVENT_HANDLERS[event_key] = []

    EVENT_HANDLERS[event_key].append(callback)
    return

