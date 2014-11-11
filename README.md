Python bindings to the Apache Ambari API
==================================================

All syntax examples will assume you are using the client against the test host
created by following the Ambari Quick Start Guide.  I've set up a 5 node cluster
which has hostnames c6401-c6405.ambari.apache.org.  The examples will translate
to other clusters, just the hostnames and number of hosts might change, obviously.

Basic API bindings design
----------

The starting point for users is the Ambari class in ambariclient.client

    >>> from ambariclient.client import Ambari
    >>> client = Ambari('c6401.ambari.apache.org', port=8080, username='admin', password='admin')

All of the various resources are broken down into what are known as collections.
Each collection contains one or more models, which represent resources in the
Ambari API.  For example, to get the usernames of all users in the system:

    >>> for user in client.users:
    ...     user.user_name
    ...
    u'admin'

You can get a specific model from a collection if you have the primary identifier
for that model.  So, for a user, the user_name is the primary identifier.  To get
the 'admin' user:

    >>> user = client.users('admin')
    >>> user.user_name
    'admin'

Each model can then, in turn, contain collections of models that are subordinate
to it.  In the case of users, there is a relationship to what are called
privileges:

    >>> for privilege in client.users('admin').privileges:
    ...     privilege.permission_name
    ...
    u'AMBARI.ADMIN'

The API tries to mimic a promises-style API (also called futures).  It will only
load data when it is required to proceed.  So, for example, in the previous
example, we had to issue a GET request when we called privilege.permission_name
because permission_name was not known until that point.  However, if we simply
needed to get the permission_id instead, that information is returned by the
GET request on the user object. I'm including the relevant debug log statements
to show the difference:

    >>> for privilege in client.users('admin').privileges:
    ...     privilege.permission_name
    ...
    DEBUG:requests.packages.urllib3.connectionpool:"GET /api/v1/users/admin HTTP/1.1" 200 416
    DEBUG:ambariclient.client:Response: {
      "href" : "http://c6401.ambari.apache.org:8080/api/v1/users/admin",
      "Users" : {
        "active" : true,
        "admin" : true,
        "groups" : [ ],
        "ldap_user" : false,
        "user_name" : "admin"
      },
      "privileges" : [
        {
          "href" : "http://c6401.ambari.apache.org:8080/api/v1/users/admin/privileges/1",
          "PrivilegeInfo" : {
            "privilege_id" : 1,
            "user_name" : "admin"
          }
        }
      ]
    }
    DEBUG:requests.packages.urllib3.connectionpool:"GET /api/v1/users/admin/privileges/1 HTTP/1.1" 200 287
    DEBUG:ambariclient.client:Response: {
      "href" : "http://c6401.ambari.apache.org:8080/api/v1/users/admin/privileges/1",
      "PrivilegeInfo" : {
        "permission_name" : "AMBARI.ADMIN",
        "principal_name" : "admin",
        "principal_type" : "USER",
        "privilege_id" : 1,
        "type" : "AMBARI",
        "user_name" : "admin"
      }
    }
    u'AMBARI.ADMIN'

Notice that two GET requests were sent to load the appropriate data.  The first
is sent as soon as you call .privileges on client.users('admin').  Most people
would expect it to be sent on client.users('admin') but at that point you aren't
attempting to access any data unknown to the object, so no API call is sent.
Accessing a relationship requires the object to be populated as the relationship
data is often returned in the original request, saving a separate API call later.
Now, back to the example:

    >>> for privilege in client.users('admin').privileges:
    ...     privilege.privilege_id
    ...
    DEBUG:requests.packages.urllib3.connectionpool:"GET /api/v1/users/admin HTTP/1.1" 200 416
    DEBUG:ambariclient.client:Response: {
      "href" : "http://c6401.ambari.apache.org:8080/api/v1/users/admin",
      "Users" : {
        "active" : true,
        "admin" : true,
        "groups" : [ ],
        "ldap_user" : false,
        "user_name" : "admin"
      },
      "privileges" : [
        {
          "href" : "http://c6401.ambari.apache.org:8080/api/v1/users/admin/privileges/1",
          "PrivilegeInfo" : {
            "privilege_id" : 1,
            "user_name" : "admin"
          }
        }
      ]
    }
    1

In this case, only the GET request for the user object was required, since it
provided the needed 'privilege_id' information.

The last concept you need to be aware of is the .wait() method that exists on
nearly all objects in the system, both collections and models.  Calling .wait()
will force a sync operation to occur.  What this means in practical terms is:

* if the object is backed by a URL, it will be loaded with fresh data from the
server
* if the object had a method called on it that generated a 'Request' object on
the server (i.e. a long-running asynchronous process), it will poll that request
until it is completed

The basic idea is to wait until the object is in a 'ready' state, so that it can
be further acted upon.  The method is designed for method-chaining, so you can do
fun things like:

    >>> host.components.install().wait().start().wait()

It's most-commonly useful after a create() call:

    >>> cluster = client.clusters.create(name, blueprint=bp_name,
                                         host_groups=host_groups,
                                         default_password=pwd
                                        ).wait(timeout=1800, interval=30)

You can override the default timeout and interval settings if you have a good
idea of how long you expect the process to take.  Both values are in seconds.
The default is to poll every 15s for an hour, which is often excessive.

Host bootstrapping
-----------

For testing things out, the bootstrap API is very useful.  To start a bootstrap
process using this library, it's pretty simple:

    >>> hosts = ["c6401.ambari.apache.org", "c6402.ambari.apache.org", "c6403.ambari.apache.org", "c6404.ambari.apache.org"]
    >>> ssh_key = ''
    >>> with open("/path/to/insecure_private_key") as f:
    ...    ssh_key = f.read()
    ...
    >>> bootstrap = client.bootstrap.create(hosts=hosts, sshKey=ssh_key, user='vagrant')
    >>> bootstrap.wait()

There is no way to retrieve a list of bootstrap operations, so don't lose track
of the one you started.  This is a server-side API restriction:

    >>> client.bootstrap.wait()
    ambariclient.exceptions.MethodNotAllowed: HTTP request failed for GET http://c6401.ambari.apache.org:8080/api/v1/bootstrap: Method Not Allowed 405: {
      "status": 405,
      "message": "Method Not Allowed"
    }

More example usage can be found in the integration tests.

Testing
-----------

Since doing good unit tests for this library would require mocking pretty much
the entire Ambari API, we didn't see a lot of benefit in that.  There will be
some unit tests to cover some basics and make sure the collection and model
classes behave as expected, but the majority of the testing is done via
integration testing.  To run those tests, you'll need the 5 node Ambari Quick
Start environment mentioned at the top of the article running, with ambari-server
installed and runnning on c6401.  At that point, you can do a full suite of
integration tests against the running Ambari installation:

    $ tox -e integration

For the unit tests, just run tox normally:

    $ tox -e py27
    $ tox -e py33
    $ tox -e

Ambari Versions
-----------

The goal of the client is to work with multiple versions of Ambari by smoothing
out the differences for the user.  There is work to be done to make that happen,
but there is support for passing a version in to the client.

    >>> client = Ambari(..., version="1.7.0")

This client has only been tested against Ambari 1.7+.  If you need
support for older versions, you might need to submit patches for anything
that was changed after that time.  Supporting anything prior to 1.6 is
problematic as the basic method of creating clusters changed to require
blueprints in that release, but if you have a good idea on how to make it
seamless, then we can try to integrate the solution.

Python Versions
-----------

The goal is to support Python 2.7+ and 3.3+. I'm not opposed to adding 2.6
support, but someone else will need to do the work.

Command-Line Interface
-----------

A CLI was originally planned, but never implemented.  Some methods that require
a large JSON body are not amenable to a CLI, but we could easily build one for
other methods if people want one.  We'll revisit this at a later date.
