# -*- mode: python -*-
# -*- coding: utf-8 -*-
#
# Copyright © 2019-2025  CINCH Enterprises, Ltd and Rod Pullmann.  All rights reserved.

"""
Generic reference implementation for project-specific base class, utilities, and global/common definitions pertaining
to all Flask-RESTX API resources.
"""
# pylint:disable=wrong-import-position,import-outside-toplevel
import os
import sys
if sys.version_info < (3, 7):  # (pre-Python 3.7)
    from collections import OrderedDict
else:
    OrderedDict = dict
from http import HTTPStatus
from base64 import (b64decode, b64encode)
import uuid
from contextlib import suppress
import traceback
import logging

# pylint:disable=unused-import
# noinspection PyUnresolvedReferences
from flask import (request as flask_request, Response as FlaskResponse, jsonify, stream_with_context)  # noqa:F401
from flask_restx import abort

# noinspection PyPackageRequirements,PyUnresolvedReferences
from cinch_pyutils.authentication import (password_plaintext, password_validate_local, password_validate_oauth2)
# noinspection PyPackageRequirements,PyUnresolvedReferences
from cinch_pyutils.networking import get_ipaddr

from swagtools.swagger_base import (ResponseDesc, RequestLocationGet, RequestLocationOther,
                                     SwaggerResource, SwaggerModel, PythonFuncDoc)
from swagtools.api import (api, ControllerSingletons)
from swagtools.service_exceptions import (ServiceError, ServiceParameterError)

if not api:
    class GlobalAPI:
        """ Dummy global API defined until actual API is auto-generated. """
        @staticmethod
        def errorhandler(func):
            """ Null decorator. """
            return func

        def __init__(self):
            """ Placeholder for global Swagger model definitions. """
            self.models = {}

        def model(self, _name, _dict):
            """ Define a Swagger model. """
            from flask_restx.model import Model
            model = Model(_name, _dict)
            self.models.setdefault(_name, model)
            return model

    api = GlobalAPI()
    api.log = logging.getLogger(__file__)  # pylint:disable=attribute-defined-outside-init

DEFAULT_HTTP_METHOD = 'POST'
DEFAULT_RESPONSE = ResponseDesc(HTTPStatus.OK, "Success", None)
REAL_IP_HEADERS = ('HTTP_X_REAL_IP', 'HTTP_X_TINYPROXY')  # (possible request headers containing real origin IP address)
UUID_NAMESPACE = uuid.UUID(bytes=bytes((__name__ + 16 * ' ')[:16], encoding='utf-8'))


def client_ipaddr(actual=False):
    """ Determines remote IPv4 address from which client submitted request, if applicable. """
    try:
        addrs = (flask_request.environ.get(sym) for sym in REAL_IP_HEADERS)
        addr = ([addr for addr in addrs if addr] + [flask_request.remote_addr])[0]
    except RuntimeError:
        addr = None
    if actual and addr in ('localhost', '127.0.0.1'):
        addr = get_ipaddr()
    return addr


def trivial_obfuscate(_str):
    """
    Trivially obfuscates a sensitive string.

    .. note::
     * String is obfuscated such that inverse function to return it to plaintext is `password_plaintext()`.
     * Nested obfuscation is prevented here, as it is not immediately apparent whether the input string is already
       obfuscated.
    """
    return b64encode(bytes(password_plaintext(_str) or '', encoding='utf-8')).decode().rstrip('=')[::-1]


def get_authorization_headers(authorization_type=None):
    """
    Retrieves all authorization credentials of the specified Authorization type (or any), present in request headers,
    if any.

    :param authorization_type: Authorization header type to retrieve ('Bearer' or 'Basic'); None => all types
    :type  authorization_type: Union(str, None)

    :return: Credentials found: list of (username, password) pairs, where a vacuous username => password is bearer token
    :rtype:  list
    """
    creds = []
    if flask_request:
        authorization_type = authorization_type.capitalize() if authorization_type else None
        for header_key in ('Authorization', 'X-Authorization'):
            header = flask_request.headers.get(header_key) or ''
            for auth in header.split(','):
                with suppress(Exception):
                    *authtype, token = auth.strip().split(maxsplit=1)
                    if authtype and authtype[0].capitalize() == 'Basic':
                        if authorization_type in (None, 'Basic'):
                            creds.append(b64decode(token).decode().split(':', maxsplit=1))
                    elif authorization_type in (None, 'Bearer'):  # (assume 'Bearer')
                        creds.append((None, token))
    return creds


def authorization_check(username=None, password=None, resource_token=None, validator=None,
                        oauth2_client_id=None, oauth2_client_secret=None, insecure=False):
    """
    Validates credentials according to the specified authorization regime.

    :param username:             Username for password check: None => special:
                                   - no `username` provided => extract username from `SWAGGER_USERNAME` or
                                                               HTTP Basic Authorization header
                                   - `username` unspecified by either above => token authentication only
    :type  username:             Union(str, None)
    :param password:             Password to check: None => special:
                                   - no `password` provided => extract password from `SWAGGER_PASSWORD` or
                                                               HTTP Basic Authorization header
    :type  password:             Union(str, Password, None)
    :param resource_token:       Resource-specific expected (known) token or password to attempt to validate;
                                 None => no known credentials to validate against
    :type  resource_token:       Union(str, None)
    :param validator:            Custom validator function to use for password/token comparison;
                                 None => use internal comparison function `_is_valid()` (see func header below for info)
    :type  validator:            Union(Callable, None)
    :param oauth2_client_id:     OAuth2 Client ID: None => local user authentication
    :type  oauth2_client_id:     Union(str, None)
    :param oauth2_client_secret: OAuth2 Client Secret: None => local user authentication
    :type  oauth2_client_secret: Union(str, None)
    :param insecure:             "Allow insecure propagation of password/token as `token` in returned client ID."
    :type  insecure:             bool

    :return: Resource client ID for validated client (None => validation failure)
    :rtype:  Union(ClientID, None)

    .. note::
     * The envirosym `SWAGGER_USERNAME`, if defined non-vacuously, will alternatively provide `username` if the latter
       is not passed here explicitly, and likewise for the envirosym `SWAGGER_PASSWORD` and `password`.
     * `password` may also be passed as a Flask `Password` object, which contains the password plaintext as an
       attribute.
     * Alternatively or supplemental to passing in credentials here explicitly, they may be also be extracted from
       the HTTP request via HTTP-standard 'Authentication' headers (or using the 'X-Authentication' header keyword
       as a synonym); if provided this way, the standard headers supported here are:
         - RFC 7617 Basic Authentication: provides trivially obfuscated username/password presented to be authorized
         - RFC 6750 Bearer Authentication: provides bearer token for authorization presented to be authorized
     * `password` and/or `resource_token` (as well as credentials present in HTTP headers) may be a trivial (base-64)
       obfuscation of its plaintext value (see `trivial_obfuscate()` and `password_plaintext()`).
     * When `resource_token` is provided, it is an "expected token", and all authorization will be token-based,
       validating the token(s) provided against this specified `resource_token`, which may be used arbitrarily by
       `validator`.  For token-based authorization, if `password` is specified, it is considered as a token to be
       validated before any token(s) presented via HTTP Bearer headers.
     * Otherwise, when `resource_token` is vacuous, basic (`username`/`password`-based) authorization is performed using
       all (username, password) pairs presented; any username/password pair provided explicitly is authenticated first,
       followed by any pair(s) presented via HTTP Basic headers.  For basic authorization:
        - SSO validation with `username` as the NTID is attempted, iff both OAuth2 client parameters are provided
        - otherwise, if either OAuth2 client parameter is vacuous, local OS account username validation is attempted
     * The result of this function is a client ID object for the authorized client (`None` => authorization failure);
       if multiple credentials are presented, the first successful validation will determine the client identity.
     * CAUTION! If `insecure` is in effect, then when basic authorization is used and successful, the returned
       client ID private portion is the valid token/password, only trivially obfuscated; custody and safeguarding
       of this becomes the responsibility of the caller, subject to retention terms imposed by the credential provider.
     * Authorization is a pass/fail operation: no special capabilities or degrees of authorization are differentiated;
       it is the responsibility of the caller to extract such "scopes" from the token (if present there), or use any
       other means at its disposal to make such determination.
    """

    def _is_valid(_specified, _expected, **_):
        """
        Default validator function for password/token: simple string comparison of deobfuscated strings.

        :param _specified: Representation of password/token provided by requester (must be plaintext)
        :type  _specified: str
        :param _expected:  Representation of correct password/token (may be obfuscated)
        :type  _expected:  str

        .. note::
         * This default method allows the expected password/token to be trivially base64-obfuscated.
         * Custom validators may allow other string representations of the specified and/or expected password/token
           to be provided (e.g., hash values).
         * This default method is not dependent on username for the validity comparison; `username` may be passed
           as a keyword argument to custom validators.
        """
        return _specified == password_plaintext(_expected)

    # Determine explicit password/token validator to use.
    token_validator = validator if callable(validator) else _is_valid

    # Determine username/password explicitly provided.
    if password:
        if password.__class__.__name__ == 'Password':  # (Flask Password object)
            password = password.default
    if not password:
        password = os.getenv('SWAGGER_PASSWORD')
    if not username:
        username = os.getenv('SWAGGER_USERNAME')

    # Validate presented credentials according to authorization type.
    valid = None
    explicit_creds = [(username, password)] if password else []
    if resource_token:  # (token authorization)
        # Authorize any validated token presented.
        # pylint:disable=redefined-argument-from-local
        for username, token in explicit_creds + get_authorization_headers(authorization_type='Bearer'):
            if token:
                token = password_plaintext(token)
                valid = token_validator(token, resource_token, username=username)
                if valid:
                    resource_token = token
                    break
    else:  # (username/password authorization)
        # Determine whether to use local or OAuth2 authentication.
        validator_params = dict(client_id=oauth2_client_id, client_secret=oauth2_client_secret)
        if all(p for p in validator_params.values()):
            basic_validator = password_validate_oauth2
        else:
            basic_validator = password_validate_local
            validator_params = {}

        # Authorize any validated username/password pair provided.
        # pylint:disable=redefined-argument-from-local
        for username, password in explicit_creds + get_authorization_headers(authorization_type='Basic'):
            if username and password:
                password = password_plaintext(password)
                valid = basic_validator(username=username, password=password, **validator_params) is None
                if valid:
                    resource_token = password
                    break

    # Construct a client ID from the first valid credential authorized, if any.
    client_id = valid or None
    if client_id and client_id.__class__.__name__ != 'ClientID':
        client_id = resource_client(client_name=username, client_token=trivial_obfuscate(resource_token))
    if client_id and not insecure:
        client_id.token = None
    return client_id


def resource_client(client_name=None, client_token=None):
    """
    Determines the client ID for the requesting client agent.

    :param client_name:  Client name (public portion) for client ID
                         (vacuous => use dotted-quad IPv4 address representation)
    :type  client_name:  Union(str, None)
    :param client_token: Client token (private portion) for client ID
                         (vacuous => generate UUID deterministically from `client_name`)
    :type  client_token: Union(str, None)

    :return: Client ID, a public/private pair identifying the client:
              * .name: the public, human-readable name of the client
              * .token: the private, secret key identifying the client for internal use
    """
    class ClientID:  # pylint:disable=too-few-public-methods
        """ Class to implement individual API service client identifier (simplistic: use IP address). """
        def __init__(self):
            self.name = client_name or client_ipaddr()
            self.token = client_token or (str(uuid.uuid3(UUID_NAMESPACE, (16 * ' ' + self.name)[-16:]))
                                          if self.name else None)

        def __str__(self):
            return str(self.name) if self.name else ''

    return ClientID()


@api.errorhandler
def default_error_handler(exc, tracestack=None):
    """
    Catch-all error handler for general exceptions occurring within the API Server.

    :param exc:        Python exception to catch
    :type  exc:        BaseException
    :param tracestack: Traceback stack from original error handler (None => capture Python traceback)
    :type  tracestack: Union(list, None)

    :return: Result pair:
              [0]: dict: Exception description (JSONifiable)
              [1]: int: HTTP status code
    :rtype:  tuple
    """
    if not tracestack:
        tracestack = traceback.format_exception(type(exc), exc, exc.__traceback__)
    trace = ''.join(tracestack).rstrip()

    if isinstance(exc, ServiceError):
        status, errtext = error_status_desc(HTTPStatus.UNPROCESSABLE_ENTITY)
        api.log.debug(errtext if errtext else "Service processing error: {}".format(trace))
        message = errtext or str(exc)

    elif isinstance(exc, ServiceParameterError):
        status, errtext = error_status_desc(HTTPStatus.BAD_REQUEST)
        api.log.debug(errtext if errtext else "Request specification error: {}".format(trace))
        message = errtext or str(exc)

    else:
        status = HTTPStatus.INTERNAL_SERVER_ERROR
        api.log.error(trace)
        message = "An unhandled exception occurred: {}".format(exc)

    return dict(message=message), status


def error_status_desc(status, message=None, path=None, method=None):
    """
    Constructs a canonical status descriptor for error conditions occurring within API request handlers.

    :param status:  HTTP status code for error
    :type  status:  int
    :param message: Specific message to include with status (None => look up in responses defined for request)
    :type  message: Union(str, None)
    :param path:    HTTP path where error occurred (None => extract from current Flask request)
    :type  path:    Union(str, None)
    :param method:  HTTP method (e.g., GET, POST, etc.) for request (None => extract from current Flask request)
    :type  method:  Union(str, None)

    :return: Result pair:
              [0]: int: HTTP status code
              [1]: str: Error description text
    :rtype:  tuple
    """
    if not message:
        path = (path or flask_request.path.split(api.basepath)[-1]).split('/')
        method = method or flask_request.method
        paths = api.refresolver.referrer.get('paths', {})
        for index in paths:
            parts = index.split('/')
            npts = sum(not p.startswith('{') for p in parts)
            if parts[:npts] == path[:npts]:
                break
        else:
            index = None
        path = paths[index] if index is not None else {}
        responses = path.get(method.lower(), {}).get('responses', {})
        message = responses.get(str(status), responses.get(status, {})).get('description', "")
    return status, message


def endpoint_get_swagger_spec():
    """ Returns the JSON representation of the Swagger schema for this application. """
    return jsonify(api.__schema__)


def canonical_route(path, method=None):
    """ Returns the "canonical" route description for resource endpoints in this application. """
    _ = method  # (HTTP method, in case "canonical" routes vary accordingly)
    return "/{}".format(path)


def request_dispatcher(self, **reqargs):
    """
    HTTP method dispatcher: parse and validate parameters, and invoke controller target method.

    :param self:    Flask resource class instance for API request
    :type  self:    SwaggerResource
    :param reqargs: Request arguments
    :type  reqargs: dict

    :return: Result pair (standard Flask request handler return value):
              [0]: response data
              [1]: HTTP status code
    :rtype:  Union(FlaskResponse, tuple)

    .. note::
     * This is a standard Flask resource method handler (e.g., get(), post(), etc.), normally embedded directly
       in the resource class.
    """
    # Parse and validate request parameters.
    func, args, kwargs = self.parse_args()

    # Find the controller object or class corresponding to the service request.
    clsname = '.'.join(func.__qualname__.split('.')[:-1])
    svcobj = ControllerSingletons.get(clsname, None)
    if not svcobj:
        svcobj = getattr(sys.modules.get(func.__module__, object()), clsname, None)  # (use class as global "object")

    # Prepend controller object as 'self' to invoke as method call, and pass Flask request object to every resource.
    if svcobj:
        args = (svcobj,) + args
        svcobj.flask_request = flask_request

    # Invoke the controller target function.
    result = func(*args, **{**kwargs, **reqargs})

    # Capture and convert exception occurring during request processing.
    if isinstance(result, BaseException):
        result, status = self.handle_request_exception(result)
    else:
        if result and isinstance(result, (list, tuple)) and isinstance(result[0], HTTPStatus):
            status, *result = result
            result = result[0] if len(result) > 0 else None
        else:
            success_response = SwaggerResource.DEFAULT_SUCCESS_FMT.format(method=flask_request.method.upper())
            status = getattr(self, success_response, DEFAULT_RESPONSE).status

    # Compose request response (and status).
    if not isinstance(result, FlaskResponse):
        result = SwaggerModel.instance_as_dict(api, result), status

    # Return request response and status.
    return result


def define_api_resource(namespace, target=None, route=None, route_params=None,  # pylint:disable=too-many-arguments
                        canonical=True, responses=None, methods=(DEFAULT_HTTP_METHOD,), location=None, auth=None,
                        hidden=False, doc_classes=None):
    """
    Boilerplate function to define an API resource: see `SwaggerResource.define_class()` for detailed documentation.

    .. note::
     * :param canonical: "Use canonical route definition." (see `canonical_route()`)
     * :param location: Specify how request parameters are provided (ala Flask-RESTX); this is provided
       to allow for overriding, in special usage cases, the restrictive location defaults that prevail because
       of severe `swagger-codegen` deficiencies (see note in `swagger_base` module).
     * :doc_classes: Collection of other (derived) classes in which to search for resource documentation (None => N/A)
     * If no `route` is provided, uses the target method name as the base route path.
     * :dispatcher: Dispatcher for resource (default: use local dispatcher)
    """
    # If not provided, extract target name from first method handler specified.
    if not target:
        if methods and isinstance(methods, dict):
            target, _ = next(iter(methods.values()))
        if not target:
            raise ValueError("Unknown target specification")

    # Inherit name of target method for endpoint name (route), unless overridden.
    if not route:
        route = target.__name__ if callable(target) else target

    # Assign defaults for responses and route parameters, and adjust route according to canonical pattern.
    if canonical:
        route = canonical_route(route, method=(next(iter(methods)) if len(methods) == 1 else None))
        if not responses:
            responses = (DEFAULT_RESPONSE,)
    else:
        route = '/' + route

    # For a base device class method, process method docstrings for its subclasses too.
    # pylint:disable=too-many-nested-blocks
    if callable(target):
        docfuncs = OrderedDict(((None, target),))
        if doc_classes:
            basecls = getattr(sys.modules.get(target.__module__, object()), target.__qualname__.split('.')[0], None)
            if basecls:
                for cls in doc_classes.values() if isinstance(doc_classes, dict) else doc_classes:
                    if issubclass(cls, basecls):
                        docfunc = getattr(cls, target.__name__, None)
                        if docfunc and docfunc not in docfuncs.values():
                            docfuncs[cls.__name__] = docfunc
    else:
        docfuncs = None

    # Create and register the resource class definition in the API namespace.
    assert namespace
    assert target
    assert route
    resource_class = SwaggerResource.define_class(namespace, target, request_dispatcher, route,
                                                  route_params=route_params, base_class=ResourceBase,
                                                  responses=responses, methods=methods, docfuncs=docfuncs,
                                                  location=location, auth=auth, hidden=hidden)
    return resource_class


def define_all_api_resources(cls, namespace, methods=(DEFAULT_HTTP_METHOD,)):
    """
    Boilerplate function to define API resources for all methods in a controller class.

    :param cls:       Controller class for which to define API resources
    :type  cls:       class
    :param namespace: Flask-RESTX namespace to register all resources within
    :type  namespace: flask_restx.Namespace
    :param methods:   HTTP method(s) to support (e.g., 'GET', 'POST', etc.)
    :type  methods:   Union(Iterable, dict)
    """
    for objname in dir(cls):
        func = getattr(cls, objname)
        if callable(func) and not objname.startswith('_'):
            *_, method = PythonFuncDoc.extract_annotations(func)
            define_api_resource(namespace, func, methods=(method,) if method else methods)


def exit_server():
    """ Terminates the API Flask server. """
    shutdown = flask_request.environ.get('werkzeug.server.shutdown')
    if callable(shutdown):
        shutdown()


class ResourceBase(SwaggerResource):
    """
    Base class for all Flask-RESTX API resources.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)  # (for future inheritance)

    @staticmethod
    def clone_parser(parser, method=None):
        """
        Copies all characteristics of an existing request parameter parser, associating the cloned parser with
        (a) different HTTP method(s).

        :param parser: Parser to clone
        :type  parser: flask_restx.RequestParser
        :param method: HTTP method(s) to associate with cloned parser
        :type  method: Union(str, Iterable)
        """
        parser = parser.copy()
        if method:
            old_method = getattr(parser, 'method', '').upper()
            if old_method != method:
                for arg in parser.args:
                    arg.location = RequestLocationGet if method == 'GET' else RequestLocationOther
        return parser

    @staticmethod
    def abort_request(code=HTTPStatus.INTERNAL_SERVER_ERROR, message=None, **kwargs):
        """ Cover function: Wraps Flask-RESTX abort() method, to allow for special processing. """
        abort(code=code, message=message, **kwargs)
