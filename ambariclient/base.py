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
Defines all the base classes for response objects.
"""

from datetime import datetime, timedelta
import logging
import time

from ambariclient import events, exceptions

LOG = logging.getLogger(__name__)


class PollableMixin(object):
    """A mixin class that allows for polling for status updates automatically.

    It modifies the behavior of the wait() method to poll the Ambari API until
    a certain precondition is met.  That precondition is defined by the
    is_finished property which must be defined by the subclass that mixes this
    one in.

    You can also set default_interval on the subclass to define the polling
    interval, and default_timeout to define the amount of time before it will
    give up.
    """
    default_interval = 15
    default_timeout = 3600

    @property
    def has_failed(self):
        raise NotImplementedError("'has_failed' must be defined by subclasses")

    @property
    def is_finished(self):
        raise NotImplementedError("'is_finished' must be defined by subclasses")

    @events.evented
    def wait(self, interval=None, timeout=None):
        if not interval:
            interval = self.default_interval
        if not timeout:
            timeout = self.default_timeout

        end = datetime.utcnow() + timedelta(seconds=timeout)
        while datetime.utcnow() < end:
            if self.has_failed:
                raise exceptions.Failed(model=self)
            elif self.is_finished:
                return self
            else:
                events.publish(self, 'wait', events.states.PROGRESS)
                time.sleep(interval)
                self.refresh()

        raise exceptions.Timeout(timeout, "Long-running task failed to complete")


class GeneratedIdentifierMixin(object):
    @property
    def identifier(self):
        """These models have server-generated identifiers.

        If we don't already have it in memory, then assume that it has not
        yet been generated.
        """
        if self.primary_key not in self._data:
            return 'Unknown'
        return str(self._data[self.primary_key])


class ModelCollection(object):
    """A collection of Ambari model objects.

    This collection can be empty, in the which case it will load the appropriate
    data on demand, if it can. This class serves as a common base class for
    collections of two types of objects, QueryableModel and DependentModel.  The
    differences between those are explained in more detail below.

    These collections are iterable, so you can do things like:

    for model in collection:
        model.do_something()

    They are also callable as methods, which lets you filter the collection to
    a subset, as such:

    model = collection(model_id)
    for model in collection([model_id, model_id]):
        model.do_something()

    for model in collection(model_id, model_id):
        model.do_something()

    for model in collection([model_dict, model_dict]):
        model.do_something()

    This is what enables things like:

    cluster = client.clusters(cluster_name)
    for host in client.clusters(cluster_name).hosts(hostname, hostname):
        host.enable_maintenance()
    """
    def __init__(self, client, model_class, parent=None):
        self.client = client
        self.model_class = model_class
        self.parent = parent
        self._is_inflated = False
        self._models = []
        self._iter_marker = 0

    def __iter__(self):
        self.inflate()
        return self

    def next(self):
        if self._iter_marker >= len(self._models):
            raise StopIteration
        model = self._models[self._iter_marker]
        self._iter_marker += 1
        return model

    def __call__(self, *args):
        raise NotImplementedError("'__call__' must be defined by subclasses")

    def inflate(self):
        raise NotImplementedError("'inflate' must be defined by subclasses")

    def refresh(self):
        self._is_inflated = False
        return self.inflate()

    def remove(self, model):
        self._models = [x for x in self._models if x.identifier != model.identifier]
        return

    @events.evented
    def wait(self, **kwargs):
        """Wait until the collection is loaded."""
        return self.inflate()

    def to_dict(self):
        self.inflate()
        return [x.to_dict() for x in self._models]


class QueryableModelCollection(ModelCollection):
    """A collection of QueryableModel objects.

    These collections are backed by a url that can be used to load and/or
    reload the collection from the server.  For the most part, they are
    lazy-loaded on demand when you attempt to access members of the collection,
    but they can be preloaded with data by passing in a list of dictionaries.
    This comes in handy because the Ambari API often returns related objects
    when you do a GET call on a specific resource.  So for example:

    client.clusters(cluster_name).hosts

    Will call GET /clusters/<cluster_name>
    Which returns all of the basic host information that then pre-populates
    the hosts collection and avoids having to query the server for that data
    when you act on the host objects it contains.
    """
    def __init__(self, *args, **kwargs):
        self.request = None
        super(QueryableModelCollection, self).__init__(*args, **kwargs)

    def __call__(self, *args):
        if len(args) == 1:
            if isinstance(args[0], list):
                # allow for passing in a list of ids and filtering the set
                items = args[0]
            else:
                identifier = str(args[0])
                return self.model_class(self, href='/'.join([self.url, identifier]),
                                        data={self.model_class.primary_key: identifier})
        else:
            items = args

        if len(items) > 0:
            self._models = []
            self._is_inflated = True
            for item in items:
                if isinstance(item, dict):
                    # we're preloading this object from existing response data
                    model = self.model_class(self, href=item['href'])
                    model.load(item)
                else:
                    # we only have the primary id, so create an deflated model
                    model = self.model_class(self, href='/'.join([self.url, item]),
                                             data={self.model_class.primary_key: item})
                self._models.append(model)

        # TODO - pagination support?  Other filters on collections?

        return self

    @property
    def url(self):
        """The url for this collection."""
        if self.parent is None:
            # TODO: differing API Versions?
            pieces = [self.client.base_url, 'api', 'v1']
        else:
            pieces = [self.parent.url]

        pieces.append(self.model_class.path)

        return '/'.join(pieces)

    def inflate(self):
        """Load the collection from the server, if necessary."""
        if not self._is_inflated:
            self.load(self.client.get(self.url))

        self._is_inflated = True
        return self

    @events.evented
    def load(self, response):
        """Parse the GET response for the collection.

        The response from a GET request against that url should look like:
            { 'items': [ item1, item2, ... ] }

        While each of the item objects is usually a subset of the information
        for each model, it generally includes the URL needed to load the full
        data in an 'href' key.  This information is used to lazy-load the
        details on the model, when needed.

        In some rare cases, a collection can have an asynchronous request
        triggered.  For those cases, we handle it here.
        """
        if 'Requests' in response:
            from ambariclient.models import Request
            self.request = Request(self.parent.cluster.requests,
                                   href=response.get('href'),
                                   data=response['Requests'])
        if 'items' in response:
            self._models = []
            for item in response['items']:
                model = self.model_class(
                    self,
                    href=item.get('href')
                )
                model.load(item)
                self._models.append(model)

    def create(self, *args, **kwargs):
        """Add a resource to this collection."""
        href = self.url
        if len(args) == 1:
            kwargs[self.model_class.primary_key] = args[0]
            href = '/'.join([href, args[0]])

        model = self.model_class(self, href=href, data=kwargs)
        model.create(**kwargs)
        self._models.append(model)
        return model

    def update(self, **kwargs):
        """Update all resources in this collection."""
        self.inflate()
        for model in self._models:
            model.update(**kwargs)
        return self

    def delete(self):
        """Delete all resources in this collection."""
        self.inflate()
        for model in self._models:
            model.delete()
        return

    @events.evented
    def wait(self, **kwargs):
        """Wait until any pending asynchronous requests are finished for this collection."""
        if self.request:
            self.request.wait(**kwargs)
            self.request = None
        return self.inflate()


class DependentModelCollection(ModelCollection):
    """A collection of DependentModel objects.

    Since these are always preloaded by parent objects, we just need to instantiate
    the model objects when a collection is called with a list of dictionaries
    provided by another API response.  There's no lazy-loading here and no way
    to regenerate the collection other than refreshing the parent object.
    """
    def __call__(self, *args):
        """Generate the models for this collection.

        Since these models aren't backed by URLs, any information they contain
        should have been included in the parent's response.  This makes it easy
        to generate the list of model objects with that data, as such:

            parent.collection_name(dict1, dict2, dict3,...)
        -or-
            parent.collection_name([dict1, dict2, dict3,...])

        Unlike QueryableModelCollection objects, there is no lazy-loading here.
        What you start with is all you ever get.  If the parent resource is
        reloaded, it should create new collections for these resources.
        """
        items = []
        if len(args) == 1:
            if isinstance(args[0], list):
                items = args[0]
            else:
                matches = [x for x in self._models if x.identifier == args[0]]
                if len(matches) == 1:
                    return matches[0]
                elif len(matches) > 1:
                    raise ValueError("More than one {0} with {1} '{2}' found in "
                                     "collection".format(self.model_class.__class__.__name__,
                                                         self.model_class.primary_key, args[0]))
                return None

        if len(items) > 0:
            self._models = []
            for item in items:
                model = self.model_class(self, data=item)
                self._models.append(model)

        return self

    def inflate(self):
        self._is_inflated = True
        return self


class Model(object):
    """An Ambari model represents a resource in the Ambari API.

    This is the base class with common functionality between objects that are
    backed by URLs on the Ambari server (QueryableModel) and those that are
    just metadata objects returned by other API calls (DependentModel).

    All of the field names defined in the 'fields' list are retrievable via
    attributes.  These are readonly at the moment. There is no way to modify
    the values once set, although that behavior differs for some subclasses.

    'relationships' defines a map between attribute names and the model class
    that should be associated with their collections.  So for example:

    relationships = {
        'hosts': Host
    }

    model.hosts will return a ModelCollection of Host objects.

    """
    primary_key = None
    fields = []
    relationships = {}

    def __init__(self, parent, data=None):
        self._data = data if data is not None else {}
        self.parent = parent
        self.client = parent.client
        self._is_inflated = False
        self._relationship_cache = {}

    @property
    def identifier(self):
        """A model's identifier is the value of its primary key."""
        if self.primary_key is None:
            return None

        if self.primary_key not in self._data:
            self.inflate()
        return str(self._data[self.primary_key])

    def __getattr__(self, attr):
        """Lazy-load related objects or object data.

        Any fields in self.fields or relationship names in self.relationships
        can be accessed as attributes on the object.  They will only load data
        if it can't reasonably be derived from already-loaded information.  i.e.
        they won't do an http request unless they have to.
        """
        if attr in self.relationships:
            self.inflate()
            if attr not in self._relationship_cache:
                rel_class = self.relationships[attr]
                self._relationship_cache[attr] = rel_class.collection_class(
                    self.client, rel_class,
                    parent=self,
                )
            return self._relationship_cache[attr]

        if attr in self.fields:
            # if it came from a parent inflation, we might only have partial data
            if attr not in self._data:
                self.inflate()
            return self._data.get(attr)

        LOG.error("Missing attr %s: %s", self.__class__.__name__, attr)

        raise AttributeError(attr)

    def refresh(self):
        """Reload a model from its data source."""
        self._is_inflated = False
        return self.inflate()

    @property
    def cluster(self):
        """A helper method to find the parent cluster of an object.

        Many times you need to reference something else belonging to the same
        cluster, this method saves you the effort of figuring that out manually
        and should work for all cases where an object belongs to a cluster at
        some level.
        """
        from ambariclient.models import Cluster
        model = self
        while model is not None and not isinstance(model, Cluster):
            model = model.parent
        if model is None:
            if 'cluster_name' in self.fields:
                return self.client.clusters(self.cluster_name)
            raise exceptions.ClientError("This model does not belong to a cluster: %s"
                                         % self.to_dict())
        return model

    def inflate(self):
        """Inflate a model by loading it's data from whatever backend it uses.

        Any methods that need access to information that doesn't yet exist will
        lazy-load their data using this method.  Subclasses should implement
        this method for their particular type of data.
        """
        raise NotImplementedError("'inflate' must be defined by subclasses")

    def to_dict(self):
        """Convert a model to a dictionary."""
        self.inflate()
        return self._data

    # TODO: this is only being used in one place so far, maybe nix it?
    def to_json_dict(self):
        """Convert the object to a dictionary for JSON serialization.

        This is most commonly used when passing objects from one API call into
        the create method on another object.  Rather than having to manually
        convert to the appropriate dictionary value, this method will implicitly
        do it for you.  If your Model requires anything other than the default
        of { primary_key: id }, then you can overload it and do what is needed.
        """
        return { self.primary_key: self.identifier }

    @events.evented
    def wait(self, **kwargs):
        """Calling wait() on a model makes it wait until the object is in a valid state.

        So, for example, if you wait() on a cluster after creating it, it will
        not return until that cluster is activated and running.  In some cases,
        it will just immediately return because the resource is already in the
        desired state.  This method is intended to be overloaded by models that
        define 'ready' in a different way, but the default behavior is to just
        delegate to the 'inflate' method on the object for objects that don't
        require any additional effort.
        """
        return self.inflate()


class DependentModel(Model):
    """A dependent model is model that is not accessible directly via a URL.

    Many Ambari objects have related data that is just returned by the API
    but not directly accessible via a specific URL other than that of the parent
    object.  This class attempts to make those objects generally interchangeable
    with models that are backed by URLs.
    """

    collection_class = DependentModelCollection

    def inflate(self):
        self._is_inflated = True
        return self


class QueryableModel(Model):
    """A queryable model is a model that is backed by a URL.

    Most resources in the Ambari API are directly accessible via a URL, and this
    class serves as a base class for all of them.  Things like a Host, Cluster,
    etc, that map to a URL all stem from here.

    There are some nice convenience methods like create(), update(), and
    delete().  Unlike some ORMs, there's no way to modify values by updating
    attributes directly and then calling save() or something to send those to
    the server.  You must call update() with the keyword arguments of the fields
    you wish to update.  I've always found that allowing for attribute updates
    is problematic as some users expect that the update will happen immediately,
    when in reality they still have to call another method like save() to make
    those changes permanent. I might recant if enough people request the addition
    of attribute setters.

    All of the data in these objects is lazy-loaded.  It will only do the API
    request at a point where it needs to in order to proceed.  These cases are:

        * accessing an attribute that isn't already loaded
        * accessing a relationship
        * calling 'inflate()' directly
        * calling wait()

    If you hit a situation where you want to force an already-loaded object to
    get the latest data from the server, the refresh() method will do that for
    you.
    """

    collection_class = QueryableModelCollection
    path = None
    data_key = None
    relationships = {}

    def __init__(self, *args, **kwargs):
        self.request = None
        if 'href' in kwargs:
            self._href = kwargs.pop('href')
        else:
            self._href = None
        self._is_inflating = False
        super(QueryableModel, self).__init__(*args, **kwargs)

    @property
    def url(self):
        """Gets the url for the resource this model represents.

        It will just use the 'href' passed in to the constructor if that exists.
        Otherwise, it will generated it based on the collection's url and the
        model's identifier.
        """
        if self._href is not None:
            return self._href
        if self.identifier:
            return '/'.join([self.parent.url, self.identifier])
        raise exceptions.ClientError("Not able to determine object URL")

    def inflate(self):
        """Load the resource from the server, if not already loaded."""
        if not self._is_inflated:
            if self._is_inflating:
                # catch infinite recursion when attempting to inflate
                # an object that doesn't have enough data to inflate
                msg = ("There is not enough data to inflate this object.  "
                       "Need either an href: {} or a {}: {}").format(
                          self._href, self.primary_key,
                          self._data.get(self.primary_key)
                      )
                raise exceptions.ClientError(msg)

            self._is_inflating = True
            self.load(self.client.get(self.url))
            self._is_inflated = True
            self._is_inflating = False
        return self

    def _generate_input_dict(self, **kwargs):
        if self.data_key:
            data = { self.data_key: {}}
            for field in kwargs:
                if field in self.fields:
                    data[self.data_key][field] = kwargs[field]
                else:
                    data[field] = kwargs[field]
            return data
        else:
            return kwargs

    @events.evented
    def load(self, response):
        """The load method parses the raw JSON response from the server.

        Most models are not returned in the main response body, but in a key
        such as 'Clusters', defined by the 'data_key' attribute on the class.
        Also, related objects are often returned and can be used to pre-cache
        related model objects without having to contact the server again.  This
        method handles all of those cases.

        Also, if a request has triggered a background operation, the request
        details are returned in a 'Requests' section. We need to store that
        request object so we can poll it until completion.
        """
        if 'Requests' in response and 'Requests' != self.data_key:
            from ambariclient.models import Request
            self.request = Request(self.cluster.requests,
                                   href=response.get('href'),
                                   data=response['Requests'])
        else:
            if 'href' in response:
                self._href = response.pop('href')
            if self.data_key and self.data_key in response:
                self._data.update(response.pop(self.data_key))
                # preload related object collections, if received
                for rel in [x for x in self.relationships if x in response]:
                    rel_class = self.relationships[rel]
                    collection = rel_class.collection_class(
                        self.client, rel_class, parent=self
                    )
                    self._relationship_cache[rel] = collection(response[rel])
            elif not self.data_key:
                self._data.update(response)

    @events.evented
    def create(self, **kwargs):
        """Create a new instance of this resource type.

        As a general rule, the identifier should have been provided, but in
        some subclasses the identifier is server-side-generated.  Those classes
        have to overload this method to deal with that scenario.
        """
        if self.primary_key in kwargs:
            del kwargs[self.primary_key]
        data = self._generate_input_dict(**kwargs)
        self.load(self.client.post(self.url, data=data))
        return self

    @events.evented
    def update(self, **kwargs):
        """Update a resource by passing in modifications via keyword arguments.

        For example:

            model.update(a='b', b='c')

        is generally converted to:

            PUT model.url { model.data_key: {'a': 'b', 'b': 'c' } }

        If the request body doesn't follow that pattern, you'll need to overload
        this method to handle your particular case.
        """
        data = self._generate_input_dict(**kwargs)
        self.load(self.client.put(self.url, data=data))
        return self

    @events.evented
    def delete(self):
        """Delete a resource by issuing a DELETE http request against it."""
        self.load(self.client.delete(self.url))
        self.parent.remove(self)
        return

    @events.evented
    def wait(self, **kwargs):
        """Wait until any pending asynchronous requests are finished."""
        if self.request:
            self.request.wait(**kwargs)
            self.request = None
        return self.inflate()
