# swagtools_skeleton_client

This is the client-side access API and Python Software Development Kit (SDK)
for the Swagger Skeleton API Server (see GitHub repo `eapy/swagtools` for
more information about this server).

The Python SDK for this repo, as well as SDK documentation and unittest scripts,
all reside in the `ext` subtree.  IMPORTANT NOTE: The entire `ext` subtree is
*auto-generated* by the Swagger code generator; this subtree must be considered
as read-only, as any manual amendments will be clobbered whenever the code
auto-generator is run.

See the auto-generated README file in the `ext` subtree for detailed SDK
documentation.


### Installation

For example purposes, this is distributed as part of the `swagtools` repo,
which implements the server side of this client, so is installed automatically
along with that repo.

However, when implementing a real-world service API based on this example code,
it is highly desired to split out this entire client-side subtree (i.e., the
`swagtools_skeleton_client` directory) into a separate Git repo so that the SDK for
this API can be installed separately from the server-side code.

Becase there may be many definitions, configuration items, and utilities shared
or specified/implemented in common between the client- and server-side code,
though, it is recommended that the client repo be installed as a "subrepo"
(a.k.a. submodule) within the main server-side repo.  This subrepo would be
installed at the same level of the main server-side tree where the client-side
code is currently embedded.

This is left as a exercise for the adapter of this example skeleton.  Once split
into a separate repo, the client-side SDK would be installed like this:

```bash
$ git clone https://github.com/cinchent/swagtools/swagtools_skeleton_client
```
(or wherever the client-side SDK repo actually resides)

This will download the repo into a local subdirectory `swagtools_skeleton_client`
(presumed for the rest of this document); optionally, appending a directory
name to the above command line will use that directory instead.


### Deployment

The `setup.py` script can be used to generate deployable bundles for this
package in the standard Pythonic way, or install it into `site-packages` on the
local system, like this:
```bash
$ python3 setup.py install
```

The `skeleton_client/service_config.sh` file contains default configuration
parameters and definitions shared between the client and server sides of the
Skeleton API.  This file is both a bash script that can be sourced to
provide default environment symbols and a Python module that can be imported.
It is not intended that settings in this file be modified by editing it.
Instead, all symbol definitions in that file can be overridden by environment
symbols of the same name.

Of note, the particular Skeleton API Server that is to be accessed by this
API client is specified by `HTTP_SERVER_HOST` environment symbol.


### Usage

Client-side access to Swagger Skeleton API Server endpoints is always available
via standard HTTP tools, e.g., web browsers or the Python `requests` package.

Documentation for the Skeleton API Server HTTP endpoints constituting this
client API can be found at the `/api/v1/doc/` server endpoint (for example,
for the `my_server` server system, hosted on remote port 7000):
```
http://my_server.somewhere.net:7000/api/v1/doc/  # (note the trailing slash)
```
The Swagger UI presented there also serves as an interactive execution engine
for submitting individual requests and visulizing status and response data.

Alternatively, the Python Skeleton client SDK provided in this repo offers
a simpler means of issuing requests to the API.  Using the SDK is preferred and
recommended; advantages are that submitting a request becomes a simple function
call, request parameters can be passed directly as function parameters, and HTTP
error-handling and response data extraction is performed by each SDK function,
not the caller.  Additionally, an SDK eliminates the need to construct URLs,
and the fact that HTTP is used at all for the transport layer is hidden from
business logic code, in case that architecture ever changes.

The Python SDK provides a pair of functions for each Skeleton API
resource, one that is a simple variant and one (with a `_with_http_info` name
suffix) that returns more detailed HTTP information associated with the request.
(Names for SDK functions are similar, but not identical, to their corresponding
resource endpoint names.)

Presuming that this repo is installed (as described above) in the standard way
as a standalone Python `skeleton_client` package, the following recipes
illustrate use of the Python SDK corresponding to the examples in
the `eapy/swagtools` repo `README.md` file.  (These example recipes presume
that the `swagtools` server was launched with `AUTO_GEN=False`.)
```python
# Initialize the individual client API resource group(s) desired from the SDK:
from skeleton_client.client import (manager_api, category_api)

# Configure the API server host to be accessed by the SDK:
manager_api.api_client.configure(instance=manager_api.api_client)

 # Use the SDK functions:
manager_api.is_hosted_remotely()  # (acts as "ping" for the server)

category_api.get_service_config()
category_api.set_service_config('some_key', value='some_value')
category_api.get_service_config()  # (read back to see added key)
category_api.set_service_config('some_key')  # (no value => delete the key)
category_api.get_service_config()  # (read back)

category_api.get_service_state()
category_api.set_service_state('some_new_state')
category_api.get_service_state()  # (read back to see state change)
```

These "service" (controller) resources are nonsensical operations implemented
here for illustrative purposes, and would be replaced by actual semantically
meaningful operations in a real-world adaptation of this skeleton.

Note that importing the individual resource API groups from
`skeleton_client.client` (as shown in the first line of the example above)
uses the environment symbol defined in `service_config.sh` to specify the
Skeleton API Server hostname, and performs other canonical initialzation
chores.

That recipe is single-line shorthand for the much more verbose importation
recipe required by native Swagger SDK usage:
```python
from skeleton_client.ext.sdk.api_client import ApiClient
from skeleton_client.ext.sdk.skeleton.manager_api import ManagerApi
from skeleton_client.ext.sdk.skeleton.category_api import CategoryApi
apicli = ApiClient()
apicli.configuration.host = "http://my_server.somewhere.net:7000/api/v1/doc/"
manager_api = ManagerApi(apicli)
category_api = CategoryApi(apicli)
```
