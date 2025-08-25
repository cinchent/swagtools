## `swagger-python-codegen` Version History

### Version 0.0.1

Initial release to public.

### Version 0.0.2

* Fixes mis-parsing of `--fix` command-line option.

* Adds `--fix` recipe to allow `multiprocessing.ThreadPool` instance in API
  client object of SDK to be modifiable (supports copying of client object),
  and custom renderer for the API client module to effect that patch.

### Version 0.0.3

* Adds `--fix` recipe to correct non-canonical initial Python module comments
  post-text rendering due to misformatted templates inherited from the public
  `swagger-codegen` release.  This option causes well-formed initial comments
  to be produced, which consist of a U**x-compatible shell script shebang line
  followed by a PEP 263-conformant character encoding specification
  (see `partial_header.mustache`).  All content currently generated presumes
  UTF-8 encoding, but alternate encodings may be supported in the future.

### Version 0.0.4

* Adds Mustache template for `rest.py` to generate code to use Python 'requests'
  package instead of the default ('urllib3') as the underlying HTTP client agent,
  specified by `-D library=requests`.

* Fixes misimplementation of snake_to_camel() utility function.

### Version 0.0.4

* Adds Mustache template for `api_client.py` to generate code to optionally use
  Python 'concurrent.futures' package instead of the default ('multiprocessing')
  as the underlying asynchronous request mechanism engaged by `async_req=True`,
  specified by `-D multiprocessing=concurrent_futures`.

* Adds capability to append additional -D options onto the `sdk-codegen.sh`
  command line, interpreted by the 'generate' script.
