# -*- mode: python -*-
# -*- coding: utf-8 -*-
#
# Copyright © 2019-2025  CINCH Enterprises, Ltd and Rod Pullmann.  All rights reserved.

"""
Skeleton API client SDK: covers Swagger-generated API, instantiating API client objects for all resource groups.
"""
# pylint:disable=ungrouped-imports,wrong-import-position,wrong-import-order
import sys
import os
from pathlib import Path
import re
import socket

from unittest.mock import MagicMock

# noinspection PyPackageRequirements,PyUnresolvedReferences
from cinch_pyutils.imports import (import_module_source, apply_environ, update_environ, add_sys_path)
# noinspection PyPackageRequirements,PyUnresolvedReferences
from cinch_pyutils.networking import get_ipaddr

THISDIR = Path(__file__).resolve().parent

# Include externally-generated code on module path (necessary because of how imports are specified in that code)
CLIENT_DIR = add_sys_path(THISDIR.parent, prepend=True)
EXT_DIR = add_sys_path(THISDIR.joinpath('ext'), prepend=True)
sys.modules.pop('sdk', None)
sys.modules.pop('sdk.models', None)

try:  # (Assume that there exists a Python SDK generated externally by swagger-codegen)
    # Imports from externally-generated SDK:
    # noinspection PyUnresolvedReferences,PyPackageRequirements
    from sdk.api_client import ApiClient as GeneratedAPIClient
    # noinspection PyUnresolvedReferences,PyPackageRequirements
    from sdk.rest import ApiException as SkeletonSDKException  # pylint:disable=unused-import
    # noinspection PyUnresolvedReferences,PyPackageRequirements
    import sdk.skeleton
    mocked_sdk = False  # pylint:disable=invalid-name
except ImportError:  # (No Python SDK)
    class GeneratedAPIClient:  # pylint:disable=missing-class-docstring,too-few-public-methods
        def __del__(self):
            pass
    sdk = MagicMock()

    class SkeletonSDKException(Exception):  # pylint:disable=missing-class-docstring,too-few-public-methods
        pass
    mocked_sdk = True  # pylint:disable=invalid-name


class APIClientMeta(type):
    """
    Metaclass for API Client class singleton to perform dynamic auto-configuration.

    NOTE: A metaclass is necessary because configuration parameters need to be resolved at client importation time.
    """
    def __init__(cls, name, bases, dct):
        super().__init__(name, bases, dct)
        config_file = Path(os.getenv('SERVICE_CONFIG', str(THISDIR.joinpath('service_config.sh')))).expanduser()
        cls.ServiceConfig = import_module_source('ServiceConfig', config_file, execute=True)
        cls.ServiceConfig.resolve_config = cls.resolve_config
        # noinspection HttpUrlsUsage
        cls.BASE_URL_FMT = "http://{}" + cls.ServiceConfig.API_BASEPATH + cls.ServiceConfig.VERSION

        # noinspection PyUnresolvedReferences
        cls.configure()

    @staticmethod
    def resolve_config(config_path):
        """
        Utility method: Resolves the absolute path to the service client configuration file specified absolutely
        or relative to this directory and with or without a default suffix.
        """
        config_path = Path(config_path)
        for suffix in [None] + (['', '.sh'] if not config_path.is_absolute() else []):
            if suffix is not None:
                config_path = Path(__file__).parent.joinpath(config_path.name)
                if suffix:
                    # noinspection PyTypeChecker
                    config_path = Path(str(config_path) + suffix)
            config_path = config_path.resolve()
            if config_path.is_file():
                break
        else:
            raise ImportError("Cannot find service configuration file '{}'".format(config_path))
        return config_path


class APIClient(GeneratedAPIClient, metaclass=APIClientMeta):
    """
    User-specific wrapper around a generic Swagger-generated API client interface.

    .. note::
     * This generic interface object is the common base for the client API corresponding to each resource group.
    """
    Singleton = None

    def __init__(self):
        # noinspection PyUnresolvedReferences
        if self.ServiceConfig.IS_HOSTED_REMOTELY and mocked_sdk:
            raise ImportError("Cannot import SDK for remote server")

        super().__init__()
        if not hasattr(self, 'NATIVE_TYPES_MAPPING'):
            self.NATIVE_TYPES_MAPPING = {}  # pylint:disable=invalid-name
        self.NATIVE_TYPES_MAPPING['BigDecimal'] = float  # (workaround: correct for BigDecimal typing goofiness)

    # pylint:disable=too-many-arguments
    @classmethod
    def init_sdk(cls, host=None, service_config=None, api_client=None, quiet=False):
        """
        Configures the API service host that the API SDK accesses.

        :param host:           Name of API service host (None => assume locally-hosted API); if specified, must be
                               fully-specified (must have a FQDN or be an IP address)
        :type  host:           Union(str, None)
        :param service_config: API service configuration object (None => use default service config)
        :type  service_config: Union(SimpleNamespace, None)
        :param api_client:     API service client object
        :type  api_client:     Union(api_client.ApiClient, None)
        :param quiet:          "Don't issue initialization warnings."
        :type  quiet:          bool

        :return: API service host
        :rtype:  str
        """
        if not service_config:
            service_config = cls.ServiceConfig
        if not api_client:
            if not cls.Singleton:
                raise ImportError("ERROR: {} not successfully imported: cannot find 'api_client'".format(cls.__name__))
            try:
                api_client = manager_api.api_client
            except (Exception, BaseException):
                api_client = services_api.api_client  # pylint:disable=used-before-assignment

        if host and host != 'localhost':  # (remote host specified)
            try:
                port = getattr(service_config, 'HTTP_SERVICE_PORT', None)
                if not port:
                    raise AttributeError("unspecified port number")
            except (Exception, BaseException) as exc:
                raise AttributeError("ERROR: Misconfigured API service port for Swagger API") from exc
        else:  # (localhost or host unspecified => assume local hosting)
            flask_host = service_config.FLASK_HOST
            port = int(service_config.FLASK_PORT)
            if host != flask_host and not quiet:
                print("WARNING: No Swagger API server hostname specified or configured, assuming '{}'"
                      .format(flask_host))
            host = flask_host
            setattr(service_config, 'IS_HOSTED_REMOTELY', False)
        os.environ['HTTP_SERVICE_HOST'] = host
        os.environ['HTTP_SERVICE_PORT'] = str(port)
        os.environ['HTTP_SERVICE_SOCKADDR'] = "{}:{}".format(host, port)

        # Construct SDK, using specified/configured API server hostname/instance.
        return api_client.configure(host=host, instance=api_client)

    @classmethod  # noqa:C901
    def configure(cls, host=None, instance=None, update_env=False, **_):
        """
        Applies API Server configuration overrides from environment symbols and specifies the server hostname.

        :param host:       Host for service (None => unknown; resolve from configuration)
        :type  host:       Union(str, None)
        :param instance:  `APIClient` instance within which to apply configuration overrides
                          (None => only affect client module config)
        :type  instance:  Union(APIClient, None)
        :param update_env: "Update environment with all resolved configuration symbols."
        :type  update_env: bool

        :return: Resolved hostname (None => unresolved)
        :rtype:  Union(str, None)

        .. note::
         * This method is typically invoked from API clients to configure the SDK, but is also invoked from
           the Swagger API server to resolve its host configuration.
        """
        if not instance:
            instance = cls

        # Determine whether this client vs. server and is running on a local workstation or a "remote" server.
        is_server = os.getenv('SwaggerAPI')
        is_hosted_remotely = os.getenv('IS_HOSTED_REMOTELY', cls.ServiceConfig.IS_HOSTED_REMOTELY)
        if isinstance(is_hosted_remotely, str):
            is_hosted_remotely = is_hosted_remotely.lower() not in ('0', 'false')
        cls.ServiceConfig.IS_HOSTED_REMOTELY = bool(is_hosted_remotely)

        # Determine the remote server and client hostname, as possible.
        environ = os.environ.copy()
        port = os.getenv('HTTP_SERVICE_PORT', '')
        if is_hosted_remotely:
            host = os.getenv('HTTP_SERVICE_HOST')
        if not host:
            if is_hosted_remotely:
                if is_server:  # (Swagger API server on "remote" system)
                    host = cls.resolve_hostname()
                    if host:
                        environ['HTTP_SERVICE_HOST'] = host
                        environ['HTTP_SERVICE_SOCKADDR'] = ':'.join((host, port))
            if not is_hosted_remotely or not is_server:
                host = host or cls.ServiceConfig.FLASK_HOST
                cls.ServiceConfig.HTTP_SERVICE_HOST = cls.resolve_hostname()

        # Apply configuration overrides to module client configuration.
        cls.ServiceConfig = apply_environ(cls.ServiceConfig, environ=environ)
        cls.ServiceConfig.IS_HOSTED_REMOTELY = is_hosted_remotely
        flask_port = os.getenv('FLASK_PORT')
        if flask_port:
            cls.ServiceConfig.FLASK_PORT = int(flask_port)

        # Also apply overrides to existing instance, if specified.
        if hasattr(instance, 'configuration'):
            instance.configuration.host = cls.url()

        # Write back all configuration parameters to environment, if specified.
        if update_env:
            update_environ(cls.ServiceConfig)

        return host

    @classmethod
    def url(cls, path=''):
        """
        Composes the full URL for a specific Swagger API service endpoint.

        :param path: Path to endpoint (empty => base URL)
        :type  path: str

        :return: Full base URL of endpoint, sans params
        :rtype:  str
        """
        host = os.getenv('HTTP_SERVICE_HOST', '') or cls.ServiceConfig.FLASK_HOST
        if host == cls.ServiceConfig.FLASK_HOST:
            sockaddr = ':'.join((host, str(cls.ServiceConfig.FLASK_PORT)))
        else:
            sockaddr = cls.ServiceConfig.HTTP_SERVICE_SOCKADDR
        url = cls.BASE_URL_FMT.format(sockaddr)
        if path:
            url = '/'.join((url, path))
        return url

    @classmethod
    def get_service_config(cls, as_env=False):
        """
        Returns Swagger API service configuration.

        :param as_env: "Return configuration in shell env form." (else as a dictionary)
        :type  as_env: bool

        :return: Service configuration, represented as specified
        :rtype:  Union(dict, str)
        """
        config = {key: value for key, value in vars(cls.ServiceConfig).items() if not key.startswith('__')}
        if as_env:
            config = '\n'.join(["{}='{}'".format(*item) for item in config.items()])
        return config

    @classmethod
    def resolve_hostname(cls):
        """ Resolves the specific local hostname however possible, resorting to 'localhost' if all else fails. """
        host = getattr(cls.ServiceConfig, 'FLASK_HOST', 'localhost')

        # Determine if client is running locally on a "remote" server machine, or as a remote client.
        try:
            host = socket.gethostname().partition('.')[0]  # (remote client: get client's host name)
        except (Exception, BaseException):
            pass

        # If specific client host cannot be determined any other way, try to extract name from the shell prompt.
        if host in ('localhost', '0.0.0.0'):
            try:
                host = re.fullmatch(r".*@(.*):.*", os.getenv('PS1', ''))[1]
            except (Exception, BaseException):
                host = get_ipaddr()

        return host

    def __del__(self):
        """ Destructor override: fail silently. """
        try:
            super().__del__()
        except (Exception, BaseException):
            pass


# Instantiate the generic Skeleton API client SDK.
APIClient.Singleton = APIClient()

# ----- Instantiate client API for each Controller resource group:
sdk = getattr(sdk, 'skeleton', sdk)  # (adjust for redefinition of 'sdk' symbol)
try:
    # noinspection PyUnresolvedReferences
    APIClient.Singleton.manager_api = manager_api = sdk.ManagerApi(APIClient.Singleton)
    # noinspection PyUnresolvedReferences
    APIClient.Singleton.operations_api = operations_api = sdk.OperationsApi(APIClient.Singleton)
except (Exception, BaseException):
    # noinspection PyUnresolvedReferences
    APIClient.Singleton.services_api = services_api = sdk.ServicesApi(APIClient.Singleton)


# Purge client SDK tree from sys.path to avoid conflict with other Swagger SDKs.
sys.path.pop(sys.path.index(str(EXT_DIR)))
