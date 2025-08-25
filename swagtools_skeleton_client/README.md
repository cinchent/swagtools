# swagtools_swagger_client

This is the client-side access API and Python Software Development Kit (SDK)
for the Swagger Tools Skeleton Server (see GitHub repo `eapy/swagtools` for
more information about this server).

The Python SDK for this repo, as well as SDK documentation and unittest scripts,
all reside in the `ext` subtree.  IMPORTANT NOTE: The entire `ext` subtree is
*auto-generated* by the Swagger code generator; this subtree must be considered
as read-only, as any manual amendments will be clobbered whenever the code
auto-generator is run.


### Installation

```bash
$ git clone https://github.com/cinchent/swagtools/swagtools_skeleton_client
```

This will download the repo into a local subdirectory `swagtools_skeleton_client`
(presumed for the rest of this document); optionally, appending a directory
name to the above command line will use that directory instead.

On Swagger Tools server-side systems, this repo must be installed as a subrepo
of the `swagtools` repo, as various definitions and modules from this
package are shared with the Swagger Tools Skeleton Server.


### Deployment

The `setup.py` script can be used to generate deployable bundles for this
package in the standard Pythonic way, or install it into `site-packages` on the
local system, like this:
```bash
$ python3 setup.py install
```

The `skeleton_client/service_config.sh` file contains default configuration
parameters and definitions shared between the client and server sides of the
Swagger Tools Skeleton.  This file is both a bash script that can be sourced to
provide default environment symbols and a Python module that can be imported.
It is not intended that settings in this file be modified by editing it.
Instead, all symbol definitions in that file can be overridden by environment
symbols of the same name; indeed, the `skeleton_client/service_config.local.sh`
file is the set of environment overrides necessary for launching the Swagger
Tools Skeleton Server locally on any system.

Of note, the particular Swagger Tools Skeleton Server that is to be accessed
by this API client is specified by `HTTP_SERVICE_HOST` environment symbol.


### Usage

Client-side access to Swagger Tools Skeleton Server endpoints is always
available via standard HTTP tools, e.g., web browsers or the Python `requests`
package.

Documentation for the Swagger Tools Skeleton Server HTTP endpoints constituting
this client API can be found at the `/api/v1/doc/` server endpoint (for example,
for the `my_server` system):
```
http://my_server.some_domain.net:7100/api/v1/doc/  # (note the trailing slash)
```
The Swagger UI presented there also serves as an interactive execution engine
for submitting individual requests and visulizing status and response data.

Alternatively, the Python Swagger Skeleton client SDK provided in this repo
offers a simpler means of issuing requests to the API.  Using the SDK is
preferred andn recommended; advantages are that submitting a request becomes
a simple function call, request parameters can be passed directly as function
parameters, and HTTP error-handling and response data extraction is performed
by each SDK function, not the caller.  Additionally, an SDK eliminates the need
to construct URLs, and the fact that HTTP is used at all for the transport layer
remains hidden from business logic code, in case that architecture ever changes.

The Python SDK provides a pair of functions for each Swagger Tools Skeleton
resource, one that is a simple variant and one (with a `_with_http_info` name
suffix) that returns more detailed HTTP information associated with the request.
(Names for SDK functions are similar, but not identical, to their corresponding
resource endpoint names.)

Presuming that this repo is installed (as described above) in the standard way
as the Python `skeleton_client` package, the following recipes illustrate use
of the Python SDK corresponding to the examples in `eapy/swagtools` repo
`README.md` file:
```python
# Initialize the individual client API resource group(s) desired from the SDK:
from skeleton_client.client import (manager_api, category_api)

# Use the SDK functions:
manager_api.is_hosted_remotely()  # (acts as "ping" for the server)

category_api.get_service_config()
category_api.set_service_config('SOME_KEY', 'SOME_VALUE')
category_api.get_service_state()
category_api.set_service_state('NEW_STATE')
```

Note that importing the individual resource API groups from
`skeleton_client.client` (as shown in the first line of the example above)
uses the standard environment symbol to specify the Swagger Tools Skeleton
Server hostname, and performs other canonical initialzation chores.

That recipe is single-line shorthand for the much more verbose importation
recipe required by native Swagger SDK usage:
```python
from skeleton_client.ext.sdk.api_client import ApiClient
from skeleton_client.ext.sdk.swagtools.manager_api import ManagerApi
from skeleton_client.ext.sdk.swagtools.category_api import CategoryApi
apicli = ApiClient()
apicli.configuration.host = "http://my_server.some_domain.net:7100/api/v1"
manager_api = ManagerApi(apicli)
category_api = CategoryApi(apicli)
```
