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


Ambari Shell
-----------

The Ambari Shell will automatically set up the ambari client for you and let you
play around with the API to learn the syntax.  To load it run the ambari-shell executable.
It should have been put in a system path for you automatically at install time, but if
you're just playing with the source code, you can call 'bin/ambari-shell' directly.  It
is based on the IPython shell, so for more comprehensive documentation of all the
capabilities provided by that, refer to their documentation:

http://ipython.org/ipython-doc/stable/interactive/index.html


    Python 2.7.6 (default, Sep  9 2014, 15:04:36)
    [GCC 4.2.1 Compatible Apple LLVM 6.0 (clang-600.0.39)] on darwin
    Type "help", "copyright", "credits" or "license" for more information.
    Logging level set to 50
    Python 2.7.6 (default, Sep  9 2014, 15:04:36)
    Type "copyright", "credits" or "license" for more information.
    
    IPython 3.1.0 -- An enhanced Interactive Python.
    ?         -> Introduction and overview of IPython's features.
    %quickref -> Quick reference.
    help      -> Python's own help system.
    object?   -> Details about 'object', use 'object??' for extra details.
    
    
    Ambari client available as 'ambari'
     - Ambari Server is http://c6401.ambari.apache.org:8080
     - Ambari Version is 2.0.0
    
     - log(new_level) will reset the logger level
     - ambari_ref() will show you all available client method chains
    
    In [1]:

You can then just reference the 'ambari' variable as the client.  The client is configurable via 
command-line options and/or a config file.  The defaults are those for the Ambari Quick Start 
setup.  Username and password are defaulted to 'admin', and the host is defaulted to 
http://c6401.ambari.apache.org:8080 

You can override them by creating a JSON configuration file in $HOME/.ambari:

    {
        "host": "my.ambari.server.com",
        "port": 80,
        "username": "my-username",
        "password": "my-password"
    }

You can also pass in any of those options on the CLI:

    ambari-shell --host http://my.ambari.server.com --username my-username --password my-password

Or you can specify some in the config file and then override some using the CLI switches.

You can also override the logger level by passing it in or putting it in the config file:

    ambari-shell --logger INFO

To get more information about the switches, run `ambari-shell --help`


Basic Examples
-----------

All of the various resources are broken down into what are known as collections.
Each collection contains one or more models, which represent resources in the
Ambari API.  For example, to get the usernames of all users in the system:

    >>> for user in ambari.users:
    ...     user.user_name
    ...
    u'admin'

You can get a specific model from a collection if you have the primary identifier
for that model.  So, for a user, the user_name is the primary identifier.  To get
the 'admin' user:

    >>> user = ambari.users('admin')
    >>> user.user_name
    u'admin'

Each model can then, in turn, contain collections of models that are subordinate
to it.  In the case of users, there is a relationship to what are called
privileges:

    >>> for privilege in ambari.users('admin').privileges:
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

    >>> for privilege in ambari.users('admin').privileges:
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
is sent as soon as you call .privileges on ambari.users('admin').  Most people
would expect it to be sent on ambari.users('admin') but at that point you aren't
attempting to access any data unknown to the object, so no API call is sent.
Accessing a relationship requires the object to be populated as the relationship
data is often returned in the original request, saving a separate API call later.
Now, back to the example:

    >>> for privilege in ambari.users('admin').privileges:
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

    >>> cluster = ambari.clusters.create(name, blueprint=bp_name,
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
    >>> bootstrap = ambari.bootstrap.create(hosts=hosts, sshKey=ssh_key, user='vagrant')
    >>> bootstrap.wait()

There is no way to retrieve a list of bootstrap operations, so don't lose track
of the one you started.  This is a server-side API restriction:

    >>> ambari.bootstrap.wait()
    ambariclient.exceptions.MethodNotAllowed: HTTP request failed for GET http://c6401.ambari.apache.org:8080/api/v1/bootstrap: Method Not Allowed 405: {
      "status": 405,
      "message": "Method Not Allowed"
    }

API Hierarchy
-----------

For reference, this is the currently-supported hierarchy of collections and models
available for you to use.  This list can be regenerated by calling reference()
in the ambari-shell.  We'll try to keep it up-to-date:

* ambari.actions
* ambari.actions(action_name)
* ambari.alert_targets
* ambari.alert_targets(id)
* ambari.blueprints
* ambari.blueprints(blueprint_name)
* ambari.blueprints(blueprint_name).host_groups
* ambari.blueprints(blueprint_name).host_groups(name)
* ambari.bootstrap
* ambari.bootstrap(requestId)
* ambari.clusters
* ambari.clusters(cluster_name)
* ambari.clusters(cluster_name).alert_definitions
* ambari.clusters(cluster_name).alert_definitions(id)
* ambari.clusters(cluster_name).alert_groups
* ambari.clusters(cluster_name).alert_groups(id)
* ambari.clusters(cluster_name).alert_history
* ambari.clusters(cluster_name).alert_history(id)
* ambari.clusters(cluster_name).alert_notices
* ambari.clusters(cluster_name).alert_notices(id)
* ambari.clusters(cluster_name).alerts
* ambari.clusters(cluster_name).alerts(id)
* ambari.clusters(cluster_name).configurations
* ambari.clusters(cluster_name).configurations(type)
* ambari.clusters(cluster_name).host_components
* ambari.clusters(cluster_name).host_components(component_name)
* ambari.clusters(cluster_name).hosts
* ambari.clusters(cluster_name).hosts(host_name)
* ambari.clusters(cluster_name).hosts(host_name).alert_history
* ambari.clusters(cluster_name).hosts(host_name).alert_history(id)
* ambari.clusters(cluster_name).hosts(host_name).alerts
* ambari.clusters(cluster_name).hosts(host_name).alerts(id)
* ambari.clusters(cluster_name).hosts(host_name).components
* ambari.clusters(cluster_name).hosts(host_name).components(component_name)
* ambari.clusters(cluster_name).privileges
* ambari.clusters(cluster_name).privileges(privilege_id)
* ambari.clusters(cluster_name).requests
* ambari.clusters(cluster_name).requests(id)
* ambari.clusters(cluster_name).requests(id).tasks
* ambari.clusters(cluster_name).requests(id).tasks(id)
* ambari.clusters(cluster_name).services
* ambari.clusters(cluster_name).services(service_name)
* ambari.clusters(cluster_name).services(service_name).alert_history
* ambari.clusters(cluster_name).services(service_name).alert_history(id)
* ambari.clusters(cluster_name).services(service_name).alerts
* ambari.clusters(cluster_name).services(service_name).alerts(id)
* ambari.clusters(cluster_name).services(service_name).components
* ambari.clusters(cluster_name).services(service_name).components(component_name)
* ambari.clusters(cluster_name).services(service_name).components(component_name).host_components
* ambari.clusters(cluster_name).services(service_name).components(component_name).host_components(component_name)
* ambari.clusters(cluster_name).services(service_name).components(component_name).metrics
* ambari.clusters(cluster_name).services(service_name).components(component_name).metrics(name)
* ambari.clusters(cluster_name).upgrades
* ambari.clusters(cluster_name).upgrades(request_id)
* ambari.clusters(cluster_name).upgrades(request_id).groups
* ambari.clusters(cluster_name).upgrades(request_id).groups(group_id)
* ambari.clusters(cluster_name).upgrades(request_id).groups(group_id).items
* ambari.clusters(cluster_name).upgrades(request_id).groups(group_id).items(stage_id)
* ambari.clusters(cluster_name).upgrades(request_id).groups(group_id).items(stage_id).tasks
* ambari.clusters(cluster_name).upgrades(request_id).groups(group_id).items(stage_id).tasks(id)
* ambari.groups
* ambari.groups(group_name)
* ambari.groups(group_name).members
* ambari.groups(group_name).members(user_name)
* ambari.hosts
* ambari.hosts(host_name)
* ambari.services
* ambari.services(service_name)
* ambari.services(service_name).components
* ambari.services(service_name).components(component_name)
* ambari.stacks
* ambari.stacks(stack_name)
* ambari.stacks(stack_name).versions
* ambari.stacks(stack_name).versions(stack_version)
* ambari.stacks(stack_name).versions(stack_version).operating_systems
* ambari.stacks(stack_name).versions(stack_version).operating_systems(os_type)
* ambari.stacks(stack_name).versions(stack_version).operating_systems(os_type).repositories
* ambari.stacks(stack_name).versions(stack_version).operating_systems(os_type).repositories(repo_id)
* ambari.stacks(stack_name).versions(stack_version).services
* ambari.stacks(stack_name).versions(stack_version).services(service_name)
* ambari.stacks(stack_name).versions(stack_version).services(service_name).components
* ambari.stacks(stack_name).versions(stack_version).services(service_name).components(component_name)
* ambari.stacks(stack_name).versions(stack_version).services(service_name).configurations
* ambari.users
* ambari.users(user_name)
* ambari.users(user_name).privileges
* ambari.users(user_name).privileges(privilege_id)
* ambari.views
* ambari.views(view_name)
* ambari.views(view_name).versions
* ambari.views(view_name).versions(version)
* ambari.views(view_name).versions(version).instances
* ambari.views(view_name).versions(version).instances(instance_name)
* ambari.views(view_name).versions(version).permissions
* ambari.views(view_name).versions(version).permissions(permission_id)

Testing
-----------

Since doing good unit tests for this library would require mocking pretty much
the entire Ambari API, we didn't see a lot of benefit in that.  There are some basic unit tests
that will be expanded upon over time, but most testing is currently done manually.

    $ tox -e py27
    $ tox -e py33
    $ tox -e

Ambari Versions
-----------

The goal of the client is to work with multiple versions of Ambari by smoothing
out the differences for the user.  The client can automatically detect the version
of Ambari running on the server:

    >>> ambari.version
    ('1', '7', '0')

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
other methods if people want one.  We replaced the idea with the Ambari Shell for
now, but are open to revisiting this if demand is present.

