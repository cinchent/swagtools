# swagtools
Swagger integration with Flask.


### Overview

Swagger (a.k.a. OpenAPI, see https://swagger.io/) is a state-of-the art RESTful
web API development toolchain, whose feature set is well worth the added
implementation complexity to integrate with a Python Flask API.  The third-party
Python package Flask-RESTX (https://flask-restx.readthedocs.io/en/stable/)
provides an excellent foundation for providing Swagger support within a Flask
web API, and is frequently used to do just that by itself.

However, Flask-RESTX has a number of key design deficiencies and coding
omissions that encumber such an implementation.  This repo offers some
supplemental tooling that eases those complications.  It also provides
a skeletal Swagger-capable Flask web API server which can be cloned and used
as the basis for implementing production-quality API servers with a high
degree of ease, elegance, and maintainability.


### Key Features

 * Parameter and return type auto-scraping from controller code
 * Integrated support parameter and return value validation
 * Integrated support for parameter and return value models
 * Integrated support for file upload to server
 * Integrated authentication support
 * Standardized service exception handling
 * Single-line decorator-free declarative resource endpoint definition
 * Construction of Swagger specification file from same server
 * Server configuration as bash script/Python module
 * Software Development Kit (SDK) generation
 * Skeleton API server


### API Server Skeleton

Simple API Server launching:
```shell
$ PYTHONPATH=. python3 app.py
```
Consult the server logging emitted to see the API base URL.

By default, the Swagger UI for the server can be accessed from that base URL
(for the default "version 1" API) at: http://localhost:5000/api/v1/doc/
(note the trailing /, a quirk of the Swagger UI).

The API Server implements a few dummy endpoints to illustrate request parameter
parsing and validation, and response generation.

Default server (and client) configuration is provided in the `service_config.sh`
script.  Generally, this file is intended to provide defaults for the defined
configuration items, and **not** be edited directly.  Instead, it is recommended
that any individual overrides to the defaults be provided as shell environment
symbols, each having the same name as the applicable configuration item.
Alternatively, this script can be cloned, edited, and invoked via the `source`
command to define all configuration items explicitly before then launching the
server.


### Quick Start: Auto-generating a Swagger API

This Swagger generation toolkit makes life as easy and lazy as a programmer
should be...

Given some "controller" service class that does useful stuff, here's how to
quickly overlay an auto-generated Swagger API over that class.

*FIRST*: In the controller class definition, format each controller method's
docstring to be exposed as an API endpoint using "sections" containing
Sphinx-compatible reStructuredText (RST) directives -- sections are separated
with a blank line, and appear in the order:
 * Service endpoint description (arbitrary text format)
 * (optional) Parameter descriptions and types
 * (optional) Return value and type
 * (optional) HTTP method designation
 * (optional) Additional information to include in the Swagger UI

The HTTP method section, if present, consists of an :http: directive followed
by which standard HTTP "access method" to use for invoking the endpoint via
an HTTP request, one of:

  {`GET`, `POST`, `PUT`, `DELETE`, `PATCH`, `HEADER`}  (default: `GET`)

(NOTE: Private controller class methods (i.e., those whose names begin with '_')
are not exposed as service endpoints.)

#### Controller Class Example:

```python
class Controller:
    """ Generic service controller to illustrate Swagger UI construction. """

    def __init__(self):
        self.service_state = 'INITIALIZED'

    # NOTE CAREFULLY: The use of docstrings here is critical; it is the means
    #                 by which parameters and return values and their types
    #                 are conveyed to the definition of service endpoints, and
    #                 by which documentation for the OpenAPI GUI is provided.
    def get_service_state(self):
        """
        Retrieves the "state" of the service.

        :return: My service "state"
        :rtype:  str

        :http: GET
        """
        return self.service_state

    def set_service_state(self, state):
        """
        Sets the current "state" of the service.

        :param state: "State" to set for my service
        :type  state: str

        :return: "State set successfully."
        :rtype:  bool

        :http: POST

        ..note::
         * "State" here is an arbitrary string used simply for illustrative
           purposes.
        """
        self.service_state = state

    # ... and other service controller methods.
```

*NEXT:* Create your API object that will wrap this service controller by
defining basic Swagger characteristics:

```
api = generate_api(title='My Handy API', description='RESTful Flask Server',
                   basepath='/api/', version='v1')
```

*FINALLY*: Create your server application by binding the controller class
to the generated API, and starting the server up.

#### Server Application Example:

```python
from swagtools.api import generate_api
from swagtools.app import (bind_controller, run_api_server)
from swagtools.controller import Controller

if __name__ == '__main__':
    api = generate_api('MyServiceApp', 'Service App description... lorem ipsum',
                       api_basepath='/api/', api_version='v1')
    bind_controller(api, 'my_service', Controller)
    run_api_server(api)
```

Quick and easy.  Boom, bam, done.

If there are multiple controller classes that you want to wrap into the same
(or different) endpoint namespace groupings, simply add a `bind_controller()`
call for each.

The `swagtools` package can, of course, be used to wrap more complex API
servers consisting of multiple controller classes and differing endpoint
namespace groupings that have many special cases.  In such configurations,
the API server would not use the  auto-generation mechanism described above,
and would instead be constructed using explicit `define_api_resource()` calls,
with each resource namespace being aggregated into a separate module in the
`resources` directory.  To demo this same example implementation using that
technique, simply set the `AUTO_GEN` flag in `app.py` to `False`
(alternatively, assign the `AUTO_GEN` envirosym to `'False'`in the shell).


### Client-Side Usage

Resources (a.k.a. "endpoints") defined by the Swagger Skeleton API are segregated
into various resource groups, each of which is the first path component of the
URL suffix appended to the base API URL.  The following resource groups are
currently defined (this may change in future revisions):

| Path component | Description                                                |
| -------------- | ---------------------------------------------------------- |
|`manager`       | Resources related to this API as a whole                   |
|`operations`    | Resources related to some service-specific functional      |
|                | operations                                                 |

Individual endpoints within each resource group are ordered alphabetically
(a quirk of the Swagger documentation UI).

For this version of the API, all RESTful API services are available at the path
prefix `/api/v1`.


#### Web Browser access

Navigate to wherever the Swagger server is hosted (the trailing slash is
required, another Swagger UI quirk) -- for example, the local instance:
```
http://localhost:5000/api/v1/doc/
```

This will display the full documentation for all endpoints of the API,
as presented by the Swagger UI.  As with all Swagger-integrated documentation
sites, this API site is actually a web application that also provides an
interactive gateway into the Swagger Skeleton server system.

To use this interactive web app, click on the colored HTTP method (e.g., GET)
display for an endpoint, click "Try it out", fill in any applicable HTTP
request parameters in the `Parameters` section, then click "Execute".

The following HTTP requests are example API usages:

 * Submit a `operations/get_service_config` GET request to present the
   configuration settings used to launch this service.

 * Submit a `operations/set_service_config` POST request to set some key within
   the configuration settings to some value.  (This doesn't actually affect
   the running server or its persistent configuration, it's just offered as
   an example implementation of a service resource.)

 * Submit a `operations/get_service_state` GET request to retrieve a "state"
   value implemented by the service (also meaningless, provided as an
   example).

 * Submit a `operations/set_service_state` POST request to set the "state"
   value to an arbitrary string value.


#### Shell access

With `curl`, you can submit API requests to the Swagger Skeleton API server
directly from shell command lines or scripts.  Request parameters can be
specified either as JSON-formatted request data (using `curl -d`) or as
query parameters appended to the request URL.

The `curl` counterparts to the interactive actions described in the previous
section would be (presuming access to device 'a6' is available):

```shell
export API_BASE="http://localhost:5000/api/v1"
curl -X GET ${API_BASE}/manager/is_hosted_remotely  # (ping the server host)
curl ${API_BASE}/operations/get_service_config  # (-X GET is default)
curl -X POST -d '{"some_key": "some_value"}' ${API_BASE}/operations/set_service_config
curl ${API_BASE}/operations/get_service_config  # (read back to see added key)
curl -X POST -d '{"some_key": null}' ${API_BASE}/operations/set_service_config
# (null => delete the custom key)
curl ${API_BASE}/operations/get_service_config  # (read back)

curl ${API_BASE}/operations/service_state
curl -X POST ${API_BASE}/operations/service_state?state=SOME_NEW_STATE
curl ${API_BASE}/operations/service_state  # (read back to see state change)
```


#### Python access

The recipes for accessing the API via Python using the `requests` package
would be nearly identical to the `curl` recipes described above:

```python
import requests
API_BASE = "http://localhost:5000/api/v1"
requests.get(API_BASE + "/manager/is_hosted_remotely")
requests.get(API_BASE + "/operations/get_service_config")
requests.post(API_BASE + "/operations/set_service_config",
              data=dict(some_key="some_value"))  # (pass as body data)
requests.get(API_BASE + "/operations/get_service_config")
requests.post(API_BASE + "/operations/set_service_config",
              data=dict(some_key=None))  # (None => delete the key)
requests.get(API_BASE + "/operations/get_service_config")
requests.get(API_BASE + "/operations/get_service_config")

requests.get(API_BASE + "/operations/service_state")
requests.post(API_BASE + "/operations/service_state",
              params="SOME_NEW_STATE")  # (pass as query params)
requests.get(API_BASE + "/operations/service_state")
```

Alternatively, the Swagger integration in the Python implementation of the API
allows a Software Development Kit (SDK) to be generated automatically from the
Swagger specification created by the API.  SDKs can be generated for any of a
large variety of programming languages; the SDK for Python is a package whose
modules correspond to the resource groupings of the API.

Use of the Python SDK instead of interacting with the API via the `requests`
package simplifies the process and is highly preferred.  See the section below
and `README.md` file in the `swagtools_skeleton_client` directory for details about
how to use the SDK.


### API SDK Generation

Native SDK code generation from Swagger leaves much to be desired.  (Refer to
:module:`swagger_base` for a brief description of some of the deficiencies.)
Nonetheless, it is highly desirable to use an SDK as opposed to issuing HTTP
requests and processing responses manually, and the limitations in the generated
SDK are generally tolerable.

To generate the SDK:
```shell
$ ./sdk-codegen.sh
```

This will execute a temporary instance of the example Swagger API server, and
use that to generate the Swagger specification file (`swagger.json`), which is
an OpenAPI specification describing all defined elements of the API; to only
generate this file, run: `./app.py --swagger`.

The Swagger specification is then passed to the open-source `swagger-codegen`
tool, which will generate the SDK code modules and associated documentation
(HTML).

Note that the generation of this SDK is sensitive to the `AUTO_GEN` flag used
by the example service -- the SDK generated on any given run of this script
will be compatible with either the auto-generated API or the more advanced
manually-defined API.  Make sure to set this environment symbol to `'True'`
or `'False'` accordingly before running the SDK code generation script.
(As committed to this code repo, both SDK variants are generated.)

See the `swagtools_skeleton_client/skeleton_client/example/test_skeleton.py` as an
example of how to use the generated SDK instead of using `requests` explicitly,
using either the auto-generated or the non-auto-generated variant.

### Design and Implementation Notes

#### Swagger integration

##### Overview

Creation of any RESTful API for a service can be a laborious process, if for
no other reason than the sheer volume of descriptive definitions and text
needed to adequately document it for external users.  Swagger, a.k.a. OpenAPI
(see https://swagger.io), provides a huge step forward in facilitating this
process: given a **Swagger specification** for the API, then documentation,
an interactive web application, and SDK bindings for all major (and many minor)
languages can be generated automatically through simple, stable tools.

The catch is that generating a Swagger specification is also in turn a laborious
prospect: it entails creating a JSON or YAML file that defines all HTTP
endpoints in the API, their request parameters, response statuses and data,
"model" data types, and detailed documentation for all of that.

Fortunately, for Python-implemented APIs, the `flask-restx` package rides
to the rescue.  Using `flask-restx` for the Flask implementation of the API
server, each endpoint handler function for which it is desired to provide
documentation, interactive exposure, and inclusion within an SDK can be
annotated using a variety of provided decorators wrapping that function.
Data types for request parameters and response data items are provided as
decorator parameters, and automatic request validators can be generated to
vastly simplify the job of making each endpoint robust.  For more complex
request and response data, `flask-restx` models and serializers/deserializers
can be defined to aggregate these data items manageably and repeatably.

However, in practice -- since multiple of these `flask-restx` decorators
need to be applied to each API class and handler method -- this is quite
tedious and verbose, rendering the resulting code that implements the API
difficult to read and maintain.  Mastering exactly which decorators to use
where and with what parameter syntax is somewhat tricky as well.  Worse,
this leads to a great deal of respecification: the code that implements the
underlying service (a.k.a. the "controller" layer in traditional MVC terms
typically has function header comments or function annotations to document
its functionality and the data types of its parameters and return values,
information that needs to be replicated in the decorators wrapping the API
that presents the service externally.

As the final step in easing the API development process, this `swagtools`
project introduces a way to shortcut, simplify, and standardize the boilerplate
API methods that expose the underlying service implementation, and to eliminate
the redundancy between these layers.  This technique uses Python introspection
to examine the methods of the class(es) that implement the services underlying
the API, extract the header documentation and parameter information from them,
and specify that information to the `flask-restx` decorators in a canonical
way.  In nearly all cases, this allows full specification of the boilerplate API
functions to be collapsed into an easily-produced and -read one-liner for each
endpoint.

##### Implementation

In this project, the underlying service controller layer implementation
encapsulated in the generic `controller.Controller` class, which provides
a trivial set of operations for illustrative purposes.  To make use of the
automatic API boilerplating capability that exposes the operations of this
controller class as API endpoints, as described in the previous section,
each method defined in the `Controller` class that is to be exposed _must_
be **fully** documented with header comments in standard Sphinx-compatible
reStructuredText.  (Harvesting this information from Python 3 annotations
is not yet supported.)  This includes three mandatory blank-line-separated
sections: 1) descriptive summary text, 2) enumeration of **all** method
parameters with their types, and 3) the return value (if any)
and its type.  (Parameters or return value sections can be omitted if
inapplicable.)  Any implementation or usage notes that are to have external
visibility in the Swagger UI can follow, in any arbitrary formatting.

For the purposes of API organization, endpoints are aggregated into the
functional categories of "resource groups", each group being collected in
a separate module within the `resources` directory.  (In this example, only
a single `top` resource group is defined.)  Each API endpoint in each resource
group module is a separate API handler **class**, implemented either using
explicit `flask-restx` decorations (e.g., as seen in `manager.py`) or by
a call to the `swagger_base` module `SwaggerResource.define_class()` function,
which creates and automatically decorates the handler class dynamically when
the resource group module is imported.

It is the `define_class()` function, as wrapped for this API by the function
`resources.resource_base.define_api_resource()`, that does the heavy lifting
of scraping the documentation from each exposed `Controller` target method,
transmogrifying that information into the forms suitable for specification
to `flask-restx` decorators, dynamically creating an API endpoint class
definition corresponding to that target method, and applying those decorators
to the API class and its handler methods.  Each API endpoint class typically
supports only a single HTTP "method" (overloaded term) function for external
access, but multiple of these can be generated if specified distinctly to
`define_api_resource()`.

Finally, if it is intended to provide access to all (or a group of)
underlying controller operations by wrapping them with API endpoints that all
use the same uniform HTTP method(s), this can be accomplished with a single
call to the `resources.resource_base.define_all_api_resources()` helper
function.  This function walks the underlying controller class and calls the
`define_api_resource()` function for each, defining an API endpoint for
every controller method defined there.  (Private methods -- i.e., those named
with a leading `_` are not exposed.)  `define_all_api_resources()` is what
is called to perform API auto-generation in this project when that is enabled.
