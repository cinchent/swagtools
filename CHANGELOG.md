## `swagtools` Version History

### Prehistoric (version 0.0.5) and earlier:

(before change tracking added)


### Version 0.0.6

* Documents rules and guidelines for parameter and result type specifications,
  and acceptable forms of input for some of the former.

* Adds support for List(<swagger model>) parameter and result types.


### Version 0.0.7

* Fixes list parsing for simple types.

* Uses different (Python string template) syntax for specifying globals
  substitutions with presented resource comments.

* Now recognizes ASCII VT (\v) character as an explicit vertical whitespace
  separator.

* Adds support for List(None) parameter/result type specifier.

* Adds support for nested lists of models in model definitions.

* Converts to using pyutils-based Python setup scripting.


### Version 0.0.8

* Adds path resolver for configuration file.


### Version 0.0.9

* Supports either of two different types of username/password authentication:
  local (OS user account) or OAuth2.

* Now uses UUID for private portion of client ID, generated deterministically
  from the IP address instead of being that address itself.


### Version 0.0.10

* Supports either Basic (username/password) and/or Bearer (token-based)
  authorizations for protected resources using standard 'Authorization'
  request header.

* Allows for specification of custom header parameters via docstring
  annotations.

### Version 0.0.11

* Uses `password_plaintext()` function from `cinch_pyutils` repo instead of
  local implementation.

* Supports passing a custom validator function to the `authorization_check()`
  function.


## Version 0.1.1

* Authorization algorithm and method changes.

* Adapts to using new public-domain `swagger-python-codegen` as a replacement
  for the broken `swagger-codegen` OpenAPI code generator.

* Supports inclusion of `swagger-python-codegen` as a git subrepo ("submodule")
  within this repo, and for installation of both via `pip`.

* Implements a callable standard wrapper script for the new Swagger SDK code
  generator, to avoid the need to reimplement this for all Swagger-based API
  projects that need to scrape the OpenAPI specification from the API service
  to use as a basis for the SDK.

### Version 0.1.2

* Implements various enhancements in the `resource_base` module to support more
  advanced client identification and authorization scenarios.

* Now supports the same complex typing for Model attributes as was supported for
  API method parameters and return values.

* Ensures that `trivial_obfuscate()` avoids unlimited string growth that can
  arise from nested obfuscation.

### Version 0.1.3

* Now supports Python `typing` module-compatible type specifications for
  parameter and return value descriptors.

### Version 0.1.4

* Now supports use of Python `requests` package as underlying HTTP client agent
  (instead of `urllib3`) via `-D library=requests` command-line option, which
  is specified by default in the `sdk-codegen.sh` shell script.

* Supports generating actual IP address instead of `127.0.0.1` or `localhost`
  in `client_ipaddr()` utility function.

### Version 0.1.5

* Supports compatibility mode for OpenAPI spec (`swagger.json`) generation,
  using schema-compliant numeric string keys for HTTP response definitions;
  for use with OpenAPI 2.0 -> 3.0 spec migration tools.

* Internal refactor: Renames `service` module and similarly-named associated
  references to `controller` for more conceptual adherence to traditional MVC
  nomenclature.

* No longer remove client directory from module path after import; only remove
  externally-generated subpath.


### Version 0.2.0

* Supports parameter, return value, and model field definitions specified by
  Python annotation types compatible with the `typing` module.

* Now includes helper methods to "sanitize" objects for serialization as JSON,
  and to serialize model objects, and automatically ensures that result values
  returned from resources are automatically sanitized before JSON serialization.

* Supports controller methods that are wrapped by a decorator.

* Also excludes `this` (ala `self`) from controller method argument scanning.

#### Version 0.2.1

* Compatible with version 0.3.5 and later definition of `pyutils.OmniDict`,
  which is properly a subclass of `dict`.

#### Version 0.2.2

* Exposes `Password` model class, allowing specification as a type-checked
  resource parameter.

#### Version 0.2.3

* Fixes proper handling of request body parameters, broken in 0.2.0 as part
  model support enhancements.

* Fixes marshalling of model objects, broken in 0.2.1.

#### Version 0.2.4

* Marshals parameter objects recursively, converting models into dictionaries.
