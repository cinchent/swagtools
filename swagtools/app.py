#!/usr/bin/env python3
# -*- mode: python -*-
# -*- coding: utf-8 -*-
#
# Copyright © 2019-2025  CINCH Enterprises, Ltd and Rod Pullmann.  All rights reserved.

"""
Main entry point module for API Server.
"""
# pylint:disable=ungrouped-imports,wrong-import-position,wrong-import-order
import sys
import os
from pathlib import Path
import argparse
import signal
from types import SimpleNamespace
import time
import threading
if sys.version_info >= (3, 7):
    OrderedDict = dict
else:
    from collections import OrderedDict

from flask import (Flask, Blueprint, json)
from flask_cors import CORS
import requests

# noinspection PyPackageRequirements
from cinch_pyutils.imports import (add_sys_path, import_module_source, apply_environ)
THISDIR = Path(__file__).resolve().parent
add_sys_path(THISDIR.parent, prepend=True)
os.environ['SwaggerAPI'] = str(os.getpid())  # (indicate server-side operation for shared server/client code)

from swagtools.swagger_base import FlaskRESTXOptions
# noinspection PyUnresolvedReferences
from swagtools_skeleton_client.skeleton_client.client import APIClient
from swagtools.api import (AUTO_GEN, API_INFO, api, generate_api, ServiceConfig, ControllerSingletons)
from swagtools.controller import Controller
import swagtools.resources.resource_base
from swagtools.resources.resource_base import (endpoint_get_swagger_spec, define_all_api_resources,
                                                default_error_handler, api as global_api)

if not AUTO_GEN:
    # pylint:disable=unused-import
    # noinspection PyUnresolvedReferences
    from swagtools.resources import (manager, operations)  # noqa:F401 # (order determines ordering in Swagger UI)
RESOURCE_GROUPS = [module for name, module in sys.modules.items()
                   if name.startswith('swagtools.resources.')]

app = Flask(__name__)
CORS(app)
if not api:
    api = generate_api(API_INFO['title'], API_INFO['description'], API_INFO['basepath'], API_INFO['version'],
                       default_error_handler=default_error_handler)
log = api.log


def initialize_app(_app, _api, _params, resource_groups=None):
    """
    Initializes Flask app as a RESTful API, registering a collection of resource namespaces.

    :param _app:            Flask application object
    :param _api:            Flask-RESTX API object
    :param _params:         Command-line parameters specified
    :type  _params:         argparse.Namespace
    :param resource_groups: Collection of resource group modules to add as Flask blueprints
    :type  resource_groups: Iterable

    .. note::
     * Each module in `resource_group` is presumed to define the member `namespace`, which specifies the Flask-RESTX
       namespace to add as the Flask blueprint.
    """
    _app.config.update(vars(FlaskRESTXOptions))

    # Register API as a Flask blueprint, and within that, each API resource group within its own
    # Flask-RESTX namespace.
    blueprint = Blueprint('api', __name__, url_prefix=_api.basepath)
    _api.init_app(blueprint)

    for module in resource_groups or []:
        namespace = getattr(module, 'namespace', None) if module else None
        if namespace:
            _api.add_namespace(namespace)

    _app.register_blueprint(blueprint)
    _api.app = _app

    os.environ['PYTHONIOENCODING'] = 'utf-8'  # (autoconvert stdin/stdout/stderr traffic to text instead of bytes)


def override_config(filespec, config_module=None):
    """
    Overrides/supplements existing application configuration with definitions from a specified module file.

    :param filespec:      File specification of Python module source file containing new configuration parameters
    :type  filespec:      str
    :param config_module: Specific configuration module containing definitions to override/supplement (None => default)
    :type  config_module: Union(ModuleType, None)

    .. note::
     * The module source file may contain non-Python syntax lines; these are ignored if present.
    """
    if not config_module:
        config_module = ServiceConfig
    config = vars(import_module_source('config', filespec, execute=True))  # (execute to resolve symbolic substitutions)
    config = SimpleNamespace(**OrderedDict((('THISDIR', Path(filespec).resolve().parent),
                                            *((k, v) for k, v in vars(config_module).items() if k not in config),
                                            *config.items())))
    config = apply_environ(config, environ={})
    for key, val in vars(config).items():
        if not key.startswith('__') and not hasattr(val, '__dict__'):
            setattr(config_module, key, val)


def generate_swagger_spec(_api, filespec, server_pid=None):
    """
    Generates a Swagger (a.k.a. OpenAPI) specification file (schema) for this API.

    :param _api:       Generated API object
    :param filespec:   File to which to write Swagger specification for API (- => standard output: may be squelched)
    :type  filespec:   str
    :param server_pid: PID for server; if specified, terminated after retrieval request completes (or times out)
    :type  server_pid: Union(int, None)

    :return: N/A -- if `server_pid` terminates server (parent) process, so should not return

    .. note::
     * The Swagger schema can only be retrieved from the server in a Flask request context; thus, this function
       is presumed to run in an independent thread or process and generates a request to the server to retrieve it.
    """
    url = APIClient.url(_api.SWAGGER_SPEC_ENDPOINT)
    error = None
    for _ in range(3):
        time.sleep(2)  # (server needs time to start)
        try:
            response = requests.get(url, timeout=20)
            if response.ok:
                swagger_spec = response.json()
                with (sys.stdout if filespec == '-' else open(filespec, 'wt', encoding='utf-8')) as ofd:
                    print(json.dumps(swagger_spec, indent=4, sort_keys=False), file=ofd)
                log.info("Swagger spec generated successfully to local file '{}'".format(Path(filespec).resolve()))
                break
            error = response.reason
        except (Exception, BaseException) as exc:
            error = str(exc)
    else:
        log.info("Swagger spec generation unsuccessful: {}".format(error))
    if server_pid:
        os.kill(server_pid, signal.SIGTERM)


def start_swagger_client(_api, filespec):
    """
    Launches a Swagger client in a thread to retrieve the Swagger specification file from the API server
    (which may not yet be launched).

    :param _api:     Generated API object
    :param filespec: File specification for file to contain retrieved Swagger specification (- => standard output)
    :type  filespec: str
    """
    endpoint = _api.SWAGGER_SPEC_ENDPOINT
    app.add_url_rule("{}/{}".format(_api.basepath, endpoint), endpoint=endpoint, view_func=endpoint_get_swagger_spec)
    client = threading.Thread(target=generate_swagger_spec, args=(_api, filespec,),
                              kwargs=dict(server_pid=os.getpid()))
    client.start()


def main(_api, _params):
    """
    Entry point for API Server.

    :param _api:    Generated API object
    :param _params: Command-line arguments specified
    :type  _params: argparse.Namespace
    """
    initialize_app(app, _api, _params, resource_groups=RESOURCE_GROUPS)

    # '--swagger' command-line parameter => Start temporary instance of server and fire up a thread running a thin
    #                                       client that retrieves the Swagger spec from the server and writes it
    #                                       to the specified file (see `generate_swagger_spec()` for more info)
    if _params.swagger:
        start_swagger_client(_api, _params.swagger)

    # Start the API server.
    log.info("======== Starting API Server Skeleton at {}".format(APIClient.url()))
    log.info("API Swagger doc hosted at {}".format(APIClient.url() + '/doc/'))
    if ServiceConfig.IS_HOSTED_REMOTELY:
        base_url = APIClient.BASE_URL_FMT.format(ServiceConfig.HTTP_SERVICE_HOSTNAME)
        log.info("         Remote access based at {}".format(base_url))
        log.info("         Swagger UI access at {}{}".format(base_url, ServiceConfig.HTTP_SERVICE_DOCPATH))
    server_params = dict(host=ServiceConfig.FLASK_HOST, port=ServiceConfig.FLASK_PORT,
                         debug=ServiceConfig.FLASK_DEBUG, use_reloader=False)
    if _params.single_process:
        server_params.update(dict(threaded=False, processes=1))
        log.info("Running in single-process mode")
    try:
        app.run(**server_params)
    except OSError as exc:
        # Special handling for case where the API server is already running when '--swagger' is specified:
        # skip starting temporary server instance and just sleep indefinitely -- client thread will terminate this.
        if not _params.swagger or "already in use" not in str(exc):
            raise exc
        while True:
            time.sleep(3600)


def bind_controller(_api, namespace, controller_class, models=None, **controller_params):
    """
    Auto-generates a Swagger API to wrap the specified controller class using the specified API namespace.

    :param _api:              Generated API object
    :param namespace:         API resource group name (a.k.a. "namespace") under which to expose controller methods
    :type  namespace:         str
    :param controller_class:  Controller class consisting of controller methods to expose via the API
    :param models:            Swagger models to use for API service (None => use discovered models)
    :type  models:            Union(dict, None)
    :param controller_params: Optional parameters to pass when instantiating the controller class

    :return: API object, with services bound
    """
    # Instantiate the controller class singleton, and record it in the global services "registry".
    ControllerSingletons.setdefault(controller_class.__name__, controller_class(**controller_params))

    # Define the Flask-RESTX namespace to use.
    namespace = _api.namespace(namespace, description=controller_class.__doc__.strip())

    # Capture and propagate any Swagger models defined globally.
    if not getattr(_api, 'models', {}):
        _api.models = models or getattr(global_api, 'models', {})

    # Replace temporary global API with auto-generated API.
    swagtools.resources.resource_base.api = _api

    # Add all controller methods to the namespace as resources -- use :http: method from docstring, if any.
    define_all_api_resources(controller_class, namespace)

    return _api


# pylint:disable=protected-access
def run_api_server(_api, **kwargs):
    """
    Starts a Flask server to service the defined API.

    :param _api:   Generated API object
    :param kwargs: Arguments for server execution (contains 'parse' => parse from command line)
    """
    parser = argparse.ArgumentParser()
    parser.add_argument('--instance', metavar='<num>', type=int, default=0,
                        help="Instance %(metavar)s for non-production instance of API server")
    parser.add_argument('--env', metavar='<file>', type=str, default=None,
                        help="Environment shell script %(metavar)s to apply for configuration item values")
    parser.add_argument('--swagger', metavar='<file>', type=str, default=None,
                        help="Generate Swagger (OpenAPI) specification to %(metavar)s (- => standard output)")
    parser.add_argument('--single_process', action='store_true',
                        help="Run server in single-process mode (for debugging)")

    if 'parse' in kwargs:
        params = parser.parse_args()
    else:
        # noinspection PyProtectedMember,PyUnresolvedReferences
        params_dict = {**{k.lstrip('-'): getattr(s, 'default') for s in parser._optionals._actions
                          if not isinstance(s, argparse._HelpAction) for k in getattr(s, 'option_strings')},
                       **kwargs}
        params = argparse.Namespace(**params_dict)

    # Select server instance to launch.
    max_instance = int(ServiceConfig.HTTP_SERVICE_MAXINSTANCES) - 1
    if not 0 <= params.instance <= max_instance:
        sys.exit("Specified --instance ({}) out of range (0-{})".format(params.instance, max_instance))
    if params.instance > 0:
        ServiceConfig.FLASK_PORT += params.instance
        ServiceConfig.HTTP_SERVICE_PORT += params.instance
        ServiceConfig.HTTP_SERVICE_SOCKADDR = ':'.join([ServiceConfig.HTTP_SERVICE_SOCKADDR.partition(':')[0],
                                                        str(ServiceConfig.HTTP_SERVICE_PORT)])
        if ')' in api.title:
            api.title = api.title.replace(')', ": instance {})".format(params.instance))

    # Apply any configuration overrides/supplementation specified.
    if params.env:
        override_config(params.env)

    # Start the server.
    main(_api, params)


# =============================================================================
if __name__ == "__main__":  # (main Python app)
    if AUTO_GEN:
        bind_controller(api, 'services', Controller)
    else:
        ControllerSingletons.setdefault(Controller.__name__, Controller())
    run_api_server(api, **dict(parse=True))

elif "flask run" in ' '.join(sys.argv):  # (run directly from Flask launcher)
    initialize_app(app, api, argparse.Namespace(), resource_groups=RESOURCE_GROUPS)  # (no command-line parameters)
