# -*- mode: python -*-
# -*- coding: utf-8 -*-
#
# Copyright © 2019-2025  CINCH Enterprises, Ltd and Rod Pullmann.  All rights reserved.

"""
Base class, utilities, and global/common definitions for a Swagger-compatible Flask-RESTX API, its resource definitions,
and request processing utilities.
"""
# pylint:disable=too-many-lines,ungrouped-imports,wrong-import-position,wrong-import-order
import sys
import re
from types import SimpleNamespace
if sys.version_info < (3, 7):  # (pre-Python 3.7)
    from collections import OrderedDict
else:
    OrderedDict = dict
from collections import namedtuple
from contextlib import suppress
from functools import partial
from itertools import (compress, repeat)
from textwrap import dedent
from string import Template
from http import HTTPStatus
import json
import typing
from enum import Enum
import inspect
import traceback

import introspection.typing.introspection as introspectyping

from flask import (request as flask_request, url_for)
from flask_restx import (Api, Resource, reqparse, fields, inputs)
from flask_restx.namespace import Namespace
from flask_restx.model import Model
from flask_restx.utils import camel_to_dash
import flask_restx.swagger
from werkzeug.datastructures import FileStorage
import werkzeug.exceptions
from werkzeug.exceptions import HTTPException
from werkzeug.serving import WSGIRequestHandler

# noinspection PyPackageRequirements,PyUnresolvedReferences
from cinch_pyutils.strings import (safe_eval, str_to_dict)
# noinspection PyPackageRequirements,PyUnresolvedReferences
from cinch_pyutils.containers import (OmniDict, dictify)
# noinspection PyPackageRequirements,PyUnresolvedReferences
from cinch_pyutils.iteration import feedback


# pylint:disable=invalid-name
# noinspection PyPep8Naming
def HTTPStatus_from_code(status_code):
    """ Performs reverse-lookup of the HTTPStatus enum value corresponding to a numeric status code. """
    # pylint:disable=no-member
    return ([e for e in HTTPStatus.__members__.values() if e == status_code] + [status_code])[0]


FlaskRESTXOptions = SimpleNamespace(
    SWAGGER_UI_DOC_EXPANSION='list',
    RESTX_VALIDATE=True,
    RESTX_MASK_SWAGGER=False,
    ERROR_404_HELP=False,
)

RequestLocationGet = ('json', 'values')  # (location(s) for request parameters on GET requests)
RequestLocationOther = ('json', 'values')  # (location(s) for request parameters on other HTTP methods)
ResponseDesc = namedtuple('ResponseDesc', "status help type")
DefaultHTTPMethod = 'GET'  # pylint:disable=invalid-name


class SwaggerSpecError(Exception):  # noqa:E302
    """ Exceptions related to Swagger specification processing. """

class SwaggerAPIError(Exception):  # noqa:E302
    """ Exceptions related to Swagger specification processing. """


class DefaultField(fields.Raw):
    """
    Default field type to use as a last resort when Flask-RESTX field type cannot be otherwise resolved/refined.
    """
    # noinspection PyShadowingBuiltins
    def __init__(self, *args, format=None, **kwargs):  # pylint:disable=redefined-builtin
        super().__init__(*args, **kwargs)
        if format:
            self.format = format  # (formatter function: (value) -> formatted_value)

class ArrayField(DefaultField):  # noqa:E302
    """
    Custom Flask-RESTX field type to use for a general array of arbitrary (possibly heterogeneous) elements,
    akin to a Python list.

    .. note::
     * Specify `format` argument in constructor to change list representation (e.g., format=tuple) or provide
       a custom array formatter callable.
    """
    def format(self, value):
        return list(value)

class NestedField(fields.Nested):  # noqa:E302
    """
    Field type to use to represent a model/parameter/return value that is itself dictionary-like object
    (other than an actual model).

    .. note::
     * This must be used instead of a Flask-RESTX `fields.Nested` such that the later representation of this item
       within a Swagger spec does not use the (currently unsupported) 'allOf' OpenAPI container specification.
    """
    def schema(self):
        schema = super().schema()
        if 'allOf' in schema:
            schema.update(schema.pop('allOf')[0])  # (denest incorrectly nested subfield)
        return schema

class Password(fields.String):  # noqa:E302
    """ Field extension: Hidden-input string field. """
    __schema__ = dict(type='string', format='password')


def is_basic_type(obj):  # noqa:E302
    """ Determines whether an object is a non-parameterized non-generic Python type. """
    return isinstance(obj, type)

if sys.version_info < (3, 9):  # noqa:E305 # (pre-Python 3.9)
    def is_generic_type(obj):
        """ Determines whether an object is a Python generic type as defined within the 'typing' module. """
        return introspectyping.is_typing_type(obj)
else:
    def is_generic_type(obj):
        """
        Determines whether an object is a Python generic type as defined within the 'typing' module.

        .. note::
           * introspectyping.is_typing_type() is incomplete in identifying all 'typing' types.
        """
        # pylint:disable=protected-access
        # noinspection PyUnresolvedReferences,PyProtectedMember
        return isinstance(obj, (typing.GenericAlias, typing._GenericAlias, typing._Final))

def is_type(obj):  # noqa:E302
    """ Determines whether an object is any kind of type. """
    # return is_basic_type(obj) or is_generic_type(obj)
    return introspectyping.is_type(obj, allow_forwardref=False) and obj is not None

def is_field_type(obj):  # noqa:E302
    """ Determines whether an object is a Flask-RESTX 'fields' type or object thereof. """
    return any(cls.__module__ == 'flask_restx.fields' for cls in (obj,) + obj.__class__.__mro__)

def is_model(obj):  # noqa:E302
    """ Determines whether an object refers to a resolved Swagger model defined in the Swagger API. """
    return isinstance(obj, Model)


class TypingJig:
    """ Utilities for type conversion of model fields, request parameter types, and response return values.  """

    # Mapping from Python built-in type names to Flask-RESTX field types.
    TYPE_TO_FIELD = {
        'int': fields.Integer,
        'str': fields.String,
        'bytes': fields.String,
        'bool': fields.Boolean,
        'float': fields.Float,
        'dict': fields.Raw,  # (generic)
        'None': fields.Raw,
        # ('list' and 'tuple' handled as container fields)
    }

    # Reverse mapping from Flask-RESTX field types to Python built-in types.
    FIELD_TO_TYPE = {
        fields.String: str,
        fields.Boolean: bool,
        fields.Integer: int,
        fields.Float: float,
        fields.Raw: dict,
        DefaultField: dict,
    }

    # Mapping from Python built-in or 'typing' module abstract base classes to 'typing' generic types
    # (for which corresponding 'flask_restx.fields' definitions should exist).
    TYPE_TO_GENERIC = {
        'list': typing.List,
        'tuple': typing.List,
        'set': typing.List,
        'List': typing.List,
        'Tuple': typing.List,
        'Set': typing.List,
        'FrozenSet': typing.List,
        'MutableSet': typing.List,
        'Container': typing.List,
        'Iterable': typing.List,
        'Sequence': typing.List,
        'MutableSequence': typing.List,
        'Collection': typing.List,

        'Union': typing.Union,
        'Optional': typing.Optional,

        'dict': typing.Dict,
        'Dict': typing.Dict,
        'Hashable': typing.Dict,
        'Mapping': typing.Dict,
        'MutableMapping': typing.Dict,
        'ItemsView': typing.Dict,
    }

    class TypeResolutionError(Exception):  # noqa:E302
        """ Failure to resolve type. """

    class RecursionError(TypeResolutionError):  # noqa:E302
        """ Bottomless recursion guard triggered. """

    @staticmethod
    def get_typename(generic_type):
        """ Retrieve 'typing' typename of a generic type (independent of Python version).  """
        return getattr(generic_type, '__name__', type(generic_type).__name__.lstrip('_'))

    @staticmethod
    def to_type(typespec, **symbols):  # noqa:E302
        """
        Translates a native or composite type specification string ala 'typing' module into a built-in or 'typing'
        expression.

        :param typespec: Type specification string or 'typing' annotation string or any composite
        :type  typespec: Union(str, type)

        :return: Canonical form for type (None => type specification does not resolve to a type)
        :rtype:  Union(type, None)

        .. note::
         * Supports legacy composite type descriptors such as 'list<int>'.
        """
        if isinstance(typespec, str):
            typespec = re.sub(r'[(<]', '[', re.sub(r'[)>]', ']', typespec))
        with suppress(Exception):
            typespec = safe_eval(typespec, symbols={**vars(typing), **__builtins__, **symbols})
        return typespec if is_type(typespec) else None

    @staticmethod
    def get_parameterized_type(native_type):
        """
        Determines the base type and type parameters, if any, for any (possibly parameterized) native Python type.

        :param native_type: Native Python type, possibly a parameterized generic type (e.g., List[str])
        :type  native_type: type

        :return: Result:
                   [0]: base type
                   [1]: argument types, if parameterized
        :rtype:  tuple
        """
        base_type, type_params = native_type, ()
        if introspectyping.is_parameterized_generic(native_type):
            base_type = introspectyping.get_generic_base_class(native_type)
            type_params = list(introspectyping.get_type_arguments(native_type))
        return base_type, type_params

    # pylint:disable=too-many-nested-blocks
    @classmethod
    def generic_to_field(cls, api, fldname, typing_type, **kwargs):
        """
        Converts a 'typing' package type specification into a Flask-RESTX field type object.

        :param api:         Global Flask-RESTX API within which to access any Swagger models/types referenced
        :type  api:         flask_restx.Api
        :param fldname:     Name of pertinent model field or request parameter
        :type  fldname:     str
        :param typing_type: Python native type or generic 'typing' package type to decompose/convert
        :type  typing_type: type
        :param kwargs:      Model/request definition attributes to propagate, if any

        :return: Flask-RESTX 'fields' type instance (None => could not resolve type into a field)
        :rtype:  object
        """
        fldtype = typing_type
        depth = kwargs['_depth'] = kwargs.setdefault('_depth', 0) + 1
        if depth > kwargs.get('max_depth', 10):
            raise cls.RecursionError(f"for '{fldname}' ({fldtype})")
        if not is_generic_type(fldtype):
            substype = cls.TYPE_TO_GENERIC.get(fldtype.__name__)
            if substype:
                fldtype = substype
            fldtype = cls.field_def_to_field(api, fldname, dict(type=fldtype), **kwargs)
        else:
            base, args = cls.get_parameterized_type(typing_type)
            if base == typing.Any:  # pylint:disable=comparison-with-callable
                fldtype = DefaultField(**kwargs)
            else:
                fldtype = None
                base = cls.TYPE_TO_GENERIC.get(cls.get_typename(base), base)
                if base == typing.Union:  # pylint:disable=comparison-with-callable
                    for null in None, type(None):
                        if null in args:
                            args.remove(null)
                            kwargs.update(dict(required=False, default=None))
                    if len(args) == 1:
                        base = typing.Optional
                    else:
                        unargs = []
                        for arg in args:
                            arg = cls.generic_to_field(api, fldname, arg, **kwargs)
                            if type(arg) not in [type(t) for t in unargs]:
                                unargs.append(arg)
                        fldtype = DefaultField(x_alternatives=tuple(unargs), **kwargs)
                if not fldtype:
                    if base == typing.Optional:  # pylint:disable=comparison-with-callable
                        kwargs.update(dict(required=False, default=None))
                        fldtype = cls.generic_to_field(api, fldname, args[0], **kwargs)
                    elif base == typing.List:
                        elem_type = cls.generic_to_field(api, fldname, args[0], **kwargs) if args else DefaultField
                        fldtype = fields.List(elem_type, **kwargs)
                    elif issubclass(base, typing.Dict):
                        fldtype = DefaultField(**kwargs)
        return fldtype

    @classmethod
    def field_def_to_field(cls, api, fldname, flddef, nest_model=True, **kwargs):
        """
        Creates a Flask-RESTX field type object from a model field or input parameter description dictionary.

        :param api:        Global Flask-RESTX API within which to access any Swagger models/types referenced
        :type  api:        flask_restx.Api
        :param fldname:    Name of pertinent model field or request parameter
        :type  fldname:    str
        :param flddef:     Flask-RESTX model field/request parameter definition
        :type  flddef:     dict
        :param nest_model: "When processing a model type, enclose it within a 'NestedField' object."
        :type  nest_model: bool
        :param kwargs:     Supplemental/overriding model/request definition attributes for model/parameter field

        :return: Flask-RESTX 'fields' type instance (None => could not resolve type into a field)
        :rtype:  object
        """
        flddef.update(kwargs)
        typespec = flddef.get('type', DefaultField)
        fldtype = cls.typespec_to_type(api, typespec)
        if is_model(SwaggerModel.get(api, fldtype)) and nest_model:
            # noinspection PyTypeChecker
            fldtype = NestedField(fldtype, **flddef)
        elif is_basic_type(fldtype):
            fldtype = cls.TYPE_TO_FIELD.get(fldtype.__name__, fldtype)
            if is_field_type(fldtype):
                fldtype = fldtype(**flddef)
        if not fldtype:
            fldtype = cls.to_type(typespec, **{**globals(), **api.model_types})
        if fldtype and is_type(fldtype) and not is_field_type(fldtype):
            fldtype = cls.generic_to_field(api, fldname, fldtype, **kwargs)
        return fldtype

    @classmethod
    def typespec_to_type(cls, api, typespec):
        """
        Determines Python or model type corresponding to a type specification.

        :param api:      Global Flask-RESTX API within which to access any Swagger models/types referenced
        :type  api:      flask_restx.Api
        :param typespec: Python type specification or string representation thereof, or a Swagger model type or
                         reference class
        :type  typespec: Union(str, type)

        :return: Native Python or 'typing' generic type
        :rtype:  type

        .. note::
         * String representations of Python composite types recognized here include legacy forms (e.g., 'list<int>',
           'Union(str, None)', etc.) and support both native and 'typing' package forms (e.g., Dict and dict).
        """
        typeval = SwaggerModel.get(api, typespec)
        if not is_model(typeval):
            # noinspection PyUnresolvedReferences
            typeval = __builtins__.get(typespec, typespec)
            if is_basic_type(typeval):
                if issubclass(typeval, Enum):
                    # noinspection PyUnresolvedReferences
                    typeval = [t for t in typeval.__mro__ if t in __builtins__.values()][0]
            else:
                typeval = cls.to_type(typeval, **globals())
        return typeval

    @classmethod
    def typespec_to_param_converter(cls, api, param_type, param_def):
        """
        Creates a Flask-RESTX request parameter value conversion function from a field typename or Python type/typename.

        :param api:        Global Flask-RESTX API within which to access any Swagger models/types referenced
        :type  api:        flask_restx.Api
        :param param_type: Type or type specifier or model corresponding to a request parameter
        :type  param_type: Union(type, str, Model)
        :param param_def:  Request parameter definition dictionary
        :type  param_def:  dict

        :return: Converter function for input values to the corresponding parameter type
        :rtype:  Callable
        """
        if is_model(SwaggerModel.get(api, param_type)):
            param_handler = param_type
        else:
            param_type = cls.typespec_to_type(api, param_type)
            base, args = cls.get_parameterized_type(param_type)
            typename = introspectyping.get_type_name(base)
            generic_converter = getattr(cls.FieldConverter, typename, None)
            param_handler = generic_converter(*args, argdef=param_def) if callable(generic_converter) else param_type
            param_handler = cls.FieldConverter.input_converter(param_handler)
        return param_handler

    class FieldConverter:
        """ Internal helper class to support dynamic data conversions for supported Swagger field types. """

        # pylint:disable=invalid-name,possibly-unused-variable
        # noinspection PyPep8Naming,PyUnusedLocal
        @classmethod
        def Union(cls, *args, **kwargs):
            """
            Evaluates a Union (polymorphic) type specification.

            .. note::
             * During value extraction/validation, the first conformant type matched in the Union is the type used
               to convert the parameter value, and `str` always matches, so order types in the Union accordingly.
            """
            typelist = args
            if None in typelist:  # (Special-case handling for Union with None: make nullable and remove from type list)
                typelist = tuple(a for a in args if a is not None)
                argdef = kwargs.get('argdef')
                if argdef:
                    argdef['nullable'] = True
            if len(typelist) == 1:  # (single-type Union: no Union at all, just a simple type)
                union_type = typelist[0]
            else:  # (type Union: create a type class to encapsulate the polymorphic type)
                # pylint:disable=invalid-name
                def converter(value, schema=None):
                    alternatives = ()
                    try:
                        alternatives = schema.get('x_alternatives', alternatives)
                        try:
                            pyvalue = safe_eval(value)
                        except (Exception, BaseException):
                            pyvalue = value
                        for cvtr in alternatives:
                            try:
                                value = cls.input_converter(cvtr, other_types=alternatives, value=pyvalue)(pyvalue)
                                break
                            except (Exception, BaseException):
                                pass
                        else:
                            value = NotImplemented
                        ok = value is not NotImplemented
                    except (Exception, BaseException):
                        ok = str in alternatives
                    if not ok:
                        raise ValueError(f"Must be convertible to one of: {alternatives}")
                    return value

                union_type = partial(converter, schema=dict(x_alternatives=typelist))
            return union_type

        # pylint:disable=invalid-name,possibly-unused-variable
        # noinspection PyPep8Naming,PyUnusedLocal
        @classmethod
        def Optional(cls, *args, **kwargs):
            """ Same as Union(..., None) """
            return cls.Union(*args, None, **kwargs)

        # pylint:disable=invalid-name,possibly-unused-variable
        # noinspection PyPep8Naming,PyUnusedLocal
        @classmethod
        def List(cls, *args, **_):
            """
            Evaluates a list-of-type specification.

            .. note::
             * The subordinate type specification for list items must be evaluable or defined ala 'typing' module.
            """
            def converter(value, schema=None):
                itemstype = str
                try:
                    itemstype = schema.get('x_itemstype', itemstype)
                    if isinstance(value, str):
                        try:
                            value = safe_eval(value)
                        except (BaseException, Exception):
                            if itemstype != str:
                                raise
                            value = [v.strip() for v in value.split(',')]
                    ok = (isinstance(value, typing.Sequence) and
                          all(elem is None or isinstance(elem, itemstype) for elem in value))
                except (Exception, BaseException):
                    ok = False
                if not ok:
                    raise ValueError(f"List items must be of type {itemstype}")
                return list(value)

            args = args[0] if len(args) == 1 else None
            return partial(converter, schema=dict(x_itemstype=args))

        # pylint:disable=invalid-name,possibly-unused-variable
        # noinspection PyPep8Naming
        @staticmethod
        def Dict(*_, **__):
            """ Collapses a dictionary-of-type specification to a generic Python dictionary converter. """
            return dict

        @classmethod
        def input_converter(cls, typeval, other_types=(), value=''):
            """
            Determines the function to use for converting an externally specified parameter value to an internal
            data value.

            :param typeval:     Target type specifier for a field value
            :type  typeval:     type
            :param other_types: All types permissible for field value (unspecified => don't care)
            :type  other_types: Iterable
            :param value:       Field value (unspecified => don't care)

            :return: Converter function for parameter value transmutation
            :rtype:  Callable
            """
            if typeval is bool:
                typeval = inputs.boolean
            elif typeval is dict:
                typeval = str_to_dict
            elif typeval in (tuple, list, typing.Iterable):
                if isinstance(value, str) and ',' not in value:
                    if str in other_types:
                        typeval = str
                    else:
                        typeval = lambda s: safe_eval(f"[{s}]")  # noqa:E731
            return typeval


class SwaggerNamespace(Namespace):
    """ Wrapper class for Flask-RESTX :class:`Namespace` to allow customization overrides. """
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('ordered', True)
        super().__init__(*args, **kwargs)

    @staticmethod
    def canonical_status_code(code):
        """ Represents HTTP status code as unprefixed symbolic HTTP status string. """
        with suppress(Exception):
            code = HTTPStatus(int(code))
        return str(code).split('HTTPStatus.', maxsplit=1)[-1]

    def response(self, code, description, model=None, **kwargs):
        """ Normalize HTTP response codes to be symbolic rather than numeric in the Swagger UI. """
        # noinspection PyTypeChecker
        return super().response(self.canonical_status_code(code), description, model=model, **kwargs)


class SwaggerAPI(Api):
    """ Encapsulates an HTTP API Server which is Swagger-compatible. """
    SWAGGER_SPEC_ENDPOINT = 'swagger.json'

    def __init__(self, basepath=None, logger=None, **kwargs):
        super().__init__(**kwargs)
        self.basepath = basepath or ''
        if logger:
            self.log = logger
        self.model_types = {}

        # Override Flask-RESTX :class:`Swagger` with a custom class, to permit supplemental processing.
        # noinspection PyUnresolvedReferences,PyPep8Naming
        api_module = sys.modules['flask_restx.api']
        api_module.Swagger = SwaggerWrapper
        api_module.Namespace = SwaggerNamespace

    @property
    def __schema__(self):
        SwaggerWrapper.SWAGGER_NUMERIC_STATUS_CODES = getattr(self, 'SWAGGER_NUMERIC_STATUS_CODES', False)
        return super().__schema__

    @property
    def specs_url(self):
        """
        Overrides the retrieval of the Swagger specification to do so internally, from the same site, obviating the
        need for user agents to handle URL redirects and for the hosting (proxy) environment to implement CORS.
        """
        return url_for(self.endpoint('specs'), _external=False)


# pylint:disable=too-few-public-methods
class SwaggerModel:
    """
    Swagger API model-related processing functions.

    .. note::
     * A Flask-RESTX model is a data structure whose schema is defined by an ordered dictionary containing field
       definition dictionaries, one per field.  As an extension here, a model reference class consisting of a single
       '__fields__' member, which refers to this model definition dictionary, can be used interchangeably with a model
       definition, and thus in contexts where types are required, like function parameter and result annotations.
     * A model reference class may also specify a '__options__' member: a dictionary defining other options pertaining
       to parsing or conversion of data to/from the model object; supported options:
         - (bool) store_missing: same semantics as for Flask-RESTX parameter definition
         - (bool) skip_none: same semantics as for Flask-RESTX :method:`marshal_with()`; also recognized in a param def
     * A model, or any of its fields, may optionally define an '__encoder__()' method that provides a single-argument
       conversion function to convert the native value for the model or field to its JSONifiable representation.
    """

    @staticmethod
    def define(api, typename, flddefs, options=None):
        """
        Factory method to define a Flask-RESTX Swagger API model.

        :param api:      Global Flask-RESTX API within which to define Swagger model
        :type  api:      flask_restx.Api
        :param typename: Global model name (will become a registered type)
        :type  typename: str
        :param flddefs:  Field definition dictionary -- each key is field name, each value is field definition dict:
                           * type:  Flask-RESTX field type/typename or Python type/typename in TypingJig.TYPE_TO_FIELD
                           * field: Field definition (keyword arguments meaningful to api.model)
                           * (other items ignored here)
        :type  flddefs:  dict
        :param options:  Behavioral options for model
        :type  options:  Union(dict, None)

        :return: Swagger model defined
        :rtype:  Model
        """
        model = api.model(typename, SwaggerModel.to_dict(api, flddefs))
        api.model_types[typename] = globals().get(typename, type(typename, (), dict(__fields__=model)))
        model._options = options or {}  # pylint:disable=protected-access
        return model

    @classmethod
    def to_dict(cls, api, flddefs):
        """
        Factory method to construct a dictionary of type-converted fields corresponding to a Swagger API model.

        :param api:     Global Flask-RESTX API within which Swagger model is defined
        :type  api:     flask_restx.Api
        :param flddefs: Model schema: field definition dictionary
        :type  flddefs: dict

        :return: Dictionary of Flask-RESTX field definitions suitable for construction of a Swagger model
        :rtype:  dict
        """
        return {k: TypingJig.field_def_to_field(api, k, v) for k, v in flddefs.items()}

    @classmethod
    def get(cls, api, typespec, define=True):
        """
        Retrieves Swagger model corresponding to type specification or aggregation thereof, optionally defining the
        model dynamically within the API from a reference class, if not already defined.

        :param api:      Global Flask-RESTX API within which to access any Swagger models is defined
        :type  api:      flask_restx.Api
        :param typespec: Name or class referring to Swagger model (class must consist of '__fields__' member)
        :type  typespec: Union(str, type)
        :param define:   "Define model within API from model reference class if not already defined."
        :type  define:   bool

        :return: Dictionary of Flask-RESTX field definitions suitable for construction of a Swagger model
        :rtype:  dict

        .. note::
         *
        """
        models = api.models
        typename = TypingJig.get_typename(typespec) if is_type(typespec) else getattr(typespec, 'name', typespec)
        model = (models.get(typespec.__class__.__name__) or
                 models.get(typename if isinstance(typename, typing.Hashable) else None, None))
        if model is None and define:
            model = getattr(typespec, '__fields__', None)
            if model is not None:
                if not is_type(model):
                    # noinspection PyTypeChecker
                    model = (models.get(model) if isinstance(model, OmniDict) or not isinstance(model, dict) else
                             cls.define(api, typename, model, options=getattr(typespec, '__options__', {})))
        return model

    @staticmethod
    def instance_as_dict(api, model_obj):
        """
        Represents a model instance (or dictionary representation thereof) as a "sanitized" (serializable) dictionary.

        :param api:       Global Flask-RESTX API within which to access any Swagger models is defined
        :type  api:       flask_restx.Api
        :param model_obj: Model instance or dict representation thereof
        :type  model_obj: Union(Model, object)

        :return: Sanitized dictionary corresponding to model instance contents
        :rtype:  object
        """
        if ((isinstance(model_obj, OmniDict) or not isinstance(model_obj, dict)) and
                (hasattr(model_obj, '__fields__') or is_model(SwaggerModel.get(api, model_obj, define=False)))):
            model_obj = vars(model_obj)
        return SwaggerResource.sanitize_for_json(model_obj)


class PythonFuncDoc:
    """ Python function documentation extraction class. """

    class DocToken:  # pylint:disable=too-few-public-methods
        """ Standard Sphinx-compatible ReStructuredText docstring tokens. """
        PARAM = ":param "
        PARAM_TYPE = ":type "
        RETURN = ":return:"
        RETURN_TYPE = ":rtype:"
        X_HTTP = ":http:"  # (extension to support auto-gen)
        X_HEADER = ":header"  # (extension to support header parameters)

    # noinspection RegExpRedundantEscape
    PARAM_TAG_PATT = re.compile(r'(\[.+\])?(.*)')

    DOC_SECTION_SEP = "\n\n"  # Docstring inter-section separator
    DOC_NOTES = ".. note::"  # Docstring embedded notes indicator

    @staticmethod
    def globals(func, clsname=None):
        """
        Generic utility to retrieve all module/class globals visible to the specified function/class method.

        :param func:    Function or method of class named by `clsname`
        :type  func:    Callable
        :param clsname: Name of class (vacuous => `func` is a function, or derive from class containing `func`)
        :type  clsname: Union(str, None)

        :return: Globals dictionary
        :rtype:  dict
        """
        func = getattr(func, '__wrapped__', func)
        clsvars = dict(func.__globals__)
        if not clsname:
            clsname = func.__qualname__.split('.')[0] if '.' in func.__qualname__ else ''
        if clsname:
            clsvars.update(vars(clsvars.get(clsname)))
        return clsvars

    @staticmethod
    def vtsubst(text):
        """ Generic utility to substitute ASCII VT characters with indented newline separation. """
        if '\v' in text:
            lines = text.split('\n')
            for i, line in enumerate(lines):
                subs = line.split('\v')
                lines[i] = ('\n' + ' ' * (len(subs[0]) - len(subs[0].lstrip())) if len(subs) > 1 else '').join(subs)
            text = '\n'.join(lines)
        return text

    @classmethod
    def extract_doc(cls, funcs, desc_only=False):
        """
        Generic utility to extract the Python docstring from the specified function, excluding any parameter and
        return value commentary present there.

        :param funcs:     Function or ([classname]->function) mapping from which to extract documentation
                          and parameter/return info; if multiple, first function with documentation is used
        :type  funcs:     Union(Callable, dict)
        :param desc_only: "Only extract the first (synopsis) section of the docstring."
                          (else all non-commentary sections)
        :type  desc_only: bool

        :return: Descriptive text extracted from function docstring
        :rtype:  str

        .. note::
         * When multiple functions are specified as `funcs`, the grouping represents all overloaded functions
           of the same name in inheritance lineage, where the first function in the group is expected to be the base
           (oldest ancestor) variant.  The following rules apply to a lineage group:
            - The synopsis section is taken from the first function in the group that defines it non-vacuously.
            - The non-commentary section information returned (if any) is the union of all such sections found in all
              function docstrings in the group.
        """
        if callable(funcs):
            funcs = {None: funcs}
        doc = ''
        supplinfo = ''
        doc_tokens = [v for k, v in vars(cls.DocToken).items() if not k.startswith('__')]
        for i, (_, func) in enumerate(funcs.items()):
            func = getattr(func, '__wrapped__', func)
            funcdoc = func.__doc__
            if not funcdoc:
                continue

            funcdoc = '\n'.join((line.rstrip() for line in funcdoc.split('\n')))
            sections = [s for s in funcdoc.split(cls.DOC_SECTION_SEP) if not any((dt in s for dt in doc_tokens))]
            if not doc:
                doc = re.sub(r'  +', ' ', dedent(sections[0]).strip())

            clsname = func.__qualname__.split('.')[0] if '.' in func.__qualname__ else ''
            clsvars = cls.globals(func, clsname=clsname)
            doc = Template(doc).safe_substitute(**clsvars)
            if desc_only:
                break

            notesrepl = "Notes:"
            # noinspection PyTypeChecker
            notesrepl = ((notesrepl if notesrepl not in supplinfo else '') +
                         ("{}\n<br>... [{}]".format('\n' if supplinfo else '', clsname) if i > 0 else ''))
            supplinfo += cls.vtsubst(dedent(Template(cls.DOC_SECTION_SEP.join(sections[1:])).safe_substitute(**clsvars))
                                     .strip().replace(cls.DOC_NOTES, notesrepl))
        return doc if desc_only else cls.DOC_SECTION_SEP.join((doc, supplinfo))

    @classmethod
    def extract_annotations(cls, func):
        """
        Generic utility to use Python introspection to extract function parameter and return value information for the
        specified function, combined with descriptive text and type information from any annotations and/or tagged
        commentary for those values extracted from the function docstring.

        :param func: Function to extract annotations/commentary from
        :type  func: Callable

        :return: Results:
                   [0] (dict<dict>) Information about each function parameter
                   [1] (dict) Information about the function return value (empty => no commentary)
                   [2] (str) HTTP method name associated with function (empty => no commentary)
                 Each information dictionary contains the following items (compatible with
                 :class:`flask_restx.reqparse.Argument`):
                  * help: Descriptive text about the parameter or return value
                  * type: Type of the parameter or return value
                          (may include types in Python :module:`typing` or flask-restx.inputs)
                  * required: positional parameter (missing => False)
                  * default: default value for keyword parameter (missing for positional parameters)
        :rtype:  str
        """
        # Use Python introspection to extract parameter names, default values, and positional vs. keyword.
        func = getattr(func, '__wrapped__', func)
        argspec = inspect.getfullargspec(func)
        funcname = func.__qualname__
        annotations = getattr(argspec, 'annotations', {})
        param_names = [a for a in argspec.args if a not in ('self', 'this', '_', '__')]
        npos = len(param_names) - len(argspec.defaults or ())
        params_info = OrderedDict((name,
                                   dict(required=True) if i < npos else
                                   dict(required=False, default=argspec.defaults[i - npos]))
                                  for i, name in enumerate(param_names))
        return_info = {}
        http_info = ''

        # Extract parameter/return value/HTTP method annotations and/or tagged commentary from docstring, if any
        # (first section of docstring is always presumed to contain a function synopsis).
        doc = "\n".join([line.rstrip() for line in (getattr(func, '__doc__', '') or '').split("\n")])
        docsects = doc.split(cls.DOC_SECTION_SEP)[1:]  # (docstring sections, sans synopsis)
        if docsects:
            desc_attrs = "help type".split()
            params_sect = 0  # (param commentary presumed to be in docstring section following synopsis)
            return_sect = 1  # (return commentary presumed to be in docstring section following params)

            # Extract param annotations (if present).
            params_doc = docsects[params_sect] + ' '
            ind = len(params_doc) - len(params_doc.lstrip()) + len(cls.DocToken.PARAM) + 1
            if cls.DocToken.PARAM in params_doc:
                params_list = dedent(params_doc).strip().split(cls.DocToken.PARAM)
                # pylint:disable=unnecessary-comprehension
                params_list = [([[t for t in a.strip().split(':', maxsplit=1)]
                                 for a in p.split(cls.DocToken.PARAM_TYPE, maxsplit=1)] + [['', None]])[:2]
                               for p in params_list if p]
                # (list of pairs of pairs: for each param, outer pair is (help, type), inner pair is (name, content))

                params_dict = OrderedDict((pdpairs[0][0],
                                           dict(zip(desc_attrs,
                                                    (cls.vtsubst(dedent(Template((ind + len(p[0])) * ' ' + (p[1] or ''))
                                                                        .safe_substitute(**cls.globals(func)).strip()))
                                                     for p in pdpairs))))
                                          for pdpairs in params_list)
                # (dict-of-dicts for params: outer dict keyed by param name, inner dict is help and type content)

                # Extract and validate parameter types.
                for name in params_info:
                    param_info = params_info[name]
                    param_dict = params_dict.get(name)
                    if param_dict is None:
                        continue
                    param_type = param_dict.get('type') or annotations.get(name)
                    if param_type is None:
                        raise SwaggerAPIError(f"Undefined parameter type for '{funcname}.{name}'")
                    param_info.update({**param_dict, **dict(type=param_type, store_missing=False)})

                # Handle degenerate case where return commentary is included in same section as param commentary.
                return_doc = params_doc[params_doc.find(cls.DocToken.RETURN):].strip()
            else:  # (function may have no params, in which case return commentary follows synopsis directly)
                return_sect, return_doc = params_sect, params_doc

            if not return_doc and len(docsects) > 1:
                return_doc = docsects[return_sect]  # (return commentary in section following param commentary)

            # Extract return annotation/commentary, including type (if present).
            if cls.DocToken.RETURN in return_doc:
                return_def = dedent(return_doc.strip().replace(cls.DocToken.RETURN, ' ' * len(cls.DocToken.RETURN)))
                # noinspection PyTypeChecker
                return_def = (return_def.split(cls.DocToken.RETURN_TYPE) + [None])[:2]
                return_info = dict(zip(desc_attrs, (t if t is None else t.strip() for t in return_def)))
                if return_info['type'] is None:
                    return_info['type'] = annotations.get('return')
                if not return_info['type']:
                    raise SwaggerAPIError(f"Unknown return type for '{funcname}'")
                ext_sect = return_sect + 1
            else:
                ext_sect = return_sect

            # Extract HTTP docstring commentary (if present).
            if len(docsects) > ext_sect:
                ext_info = docsects[ext_sect].strip().split('\n')
                for ext_line in ext_info:
                    ext_line = ext_line.strip()
                    if ext_line.startswith(cls.DocToken.X_HTTP):
                        http_info = ext_line.split(cls.DocToken.X_HTTP, maxsplit=1)[-1].strip()
                    elif ext_line.startswith(cls.DocToken.X_HEADER):
                        header, *_help = ext_line.split(cls.DocToken.X_HEADER, maxsplit=1)[-1].strip().split(maxsplit=1)
                        params_info[header.replace(':', '').strip()] = dict(type='header', help=''.join(_help) or None)

        return params_info, return_info, http_info


class SwaggerResource(Resource):
    """ Encapsulates a controller handler corresponding to an API resource. """

    DEFAULT_PARSER_FMT = "PARSER_{method}"
    DEFAULT_SUCCESS_FMT = "SUCCESS_{method}"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)  # (for subsequent inheritance)

    # pylint:disable=too-many-arguments,too-many-locals,too-many-branches
    @classmethod
    def define_class(cls, namespace, target, handler, route, route_params=None, responses=None,  # noqa:C901
                     base_class=None, docfuncs=None, methods=('GET', 'POST'), location=None, auth=None, hidden=False):
        """
        Creates a Flask resource class definition for a Swagger-compatible Flask endpoint binding a target controller
        function to an HTTP route processed via a request handler function, registering the resource in a Flask-RESTX
        namespace.

        :param namespace:    Flask-RESTX namespace to register the resource within
        :type  namespace:    flask_restx.Namespace
        :param target:       Target controller function to handle endpoint requests; `methods` is dict => endpoint name
        :type  target:       Union(Callable, str)
        :param handler:      Request handler function for HTTP method(s); expected to invoke `target`
                             (default => shared request handler)
        :type  handler:      Callable
        :param route:        URL route path corresponding to the resource endpoint (relative to URL base)
        :type  route:        str
        :param route_params: Dictionary providing description(s) for any path parameter(s) embedded within `route`
        :type  route_params: Union(dict, None)
        :param responses:    Additional response definitions (None => default error response, if any)
        :type  responses:    Union(Iterable, None)
        :param base_class:   Class (typically derived from this class) to use as base for the created resource class
                             (None => this class)
        :type  base_class:   Union(SwaggerResource, None)
        :param docfuncs:     Function or ([classname]->function) mapping from which to extract documentation
                             and parameter/return info (None => `target`)
        :type  docfuncs:     Union(Callable, dict, None)
        :param methods:      HTTP method(s) to support; if a dict:
                              * keys are HTTP methods
                              * values are target functions, or (target function, SDK function name) pairs
        :type  methods:      Union(Iterable, dict)
        :param location:     How request parameters are specified, ala `Flask-RESTX` usage
                             (see meaning in `request_parser`)
        :type  location:     Union(str, dict, None)
        :param auth:         Authorization type(s) for resource use: one or more of api.authorizations keys
                             (see AUTHORIZATIONS as default), space-separated if multiple specified as string;
                             True => first defined auth type
                             (None or False => no auth required)
        :type  auth:         Union(list, str, bool, None)
        :param hidden:       "Omit resource from Swagger documentation GUI."
        :type  hidden:       bool

        :return: Fully Swagger-wrapped and commented/annotated resource class definition created and registered
        :rtype:  type

        .. note::
         * Any rules-based modification to resource endpoint naming can be enacted here by affecting the `route`
           specification.

        Class definition is equivalent to the following boilerplate:
        .. code-block:: python
            @namespace.route(_route_)
            @api.doc(params=_route_params_, security=_auth_)
            @api.response(*_responses_[0])
            @api.response(...)  # ...  for each response in _responses_
            @api.marshal_with(_result_model_)  # (present if return type is a defined scalar model)
            @api.marshal_list(_result_list_)   # (present if return type is a list of defined scalar models)
            class SomeResourceClass(ResourceBase):
                PARSER_POST = request_parser(func=_target_)
                SUCCESS_POST = PARSER_POST.result
                @api.response(*SUCCESS_POST)
                @api.expect(PARSER_POST)
                def post(self, *args):
                    ...
                PARSER_GET = request_parser(func=_target_)
                SUCCESS_GET = PARSER_GET.result
                @api.response(*SUCCESS_GET)
                @api.expect(PARSER_GET)
                def get(self, *args):
                    ...
                ARGUMENT_MODEL = SwaggerModel.define(api, "GlobalModelName", ArgumentModelDefinition)
                @api.expect(ARGUMENT_MODEL)
                @api.doc(ARGUMENT_MODEL)
                @api.response(HTTPStatus.OK, "message about model", ARGUMENT_MODEL)
                def put(self, *args)
                    ...
                ...  # for each method in _methods_
        """
        api = namespace.apis[0]
        cls.namespace = namespace

        # Determine target controller handler for each HTTP method supported.
        if isinstance(methods, dict):
            methods = {m: (v, None) if callable(v) else v for m, v in methods.items()}
        else:
            assert callable(target)
            methods = dict.fromkeys(methods, (target, None))

        assert callable(handler)

        # Generate resource class definition(s) for each endpoint method:
        param_model = None
        docparam = None
        resource_attrs = {}
        orig_docfuncs = docfuncs
        for method, (target_func, sdk_name) in methods.items():
            assert callable(target_func)

            # Create an indirection function wrapper for request handler to guarantee its uniqueness.
            def handler_wrapper(*_args, **_kwargs):
                return handler(*_args, **_kwargs)  # <<<--- request handled here

            if orig_docfuncs is None:
                docfuncs = {None: target_func}

            # Extract header docstring from target function, removing parameter/return commentary, and substitute
            # it for handler function documentation.  Combine lines in the initial section, strip final period,
            # and allow embedded "periods" to form the endpoint synopsis.  When docstring has multiple sections
            # following the param/return commentary sections, those will become the endpoint header comments --
            # always begin the header comments with the SDK function name.
            doc = PythonFuncDoc.extract_doc(docfuncs)
            synopsis, *doc = doc.split(PythonFuncDoc.DOC_SECTION_SEP, maxsplit=1)
            doc = '\n\n' + doc[0] if doc else ''
            if not sdk_name:
                sdk_name = cls.construct_sdk_funcname(target_func.__name__, method.lower())
            handler_wrapper.__doc__ = (synopsis.replace('\n', ' ').strip().rstrip('.').replace('.', '\u2024') +
                                       '\n' + f"SDK: `{sdk_name}()`" + doc)

            # Create a request param parser for this request method.
            param_parser = cls.request_parser(api, target_func, docfuncs=docfuncs, method=method,
                                              route_params=route_params, location=location)
            if not docparam:
                docparam = getattr(param_parser, 'args', None)
                if docparam:
                    docparam = docparam[0]
                    if not all(hasattr(docparam, k) for k in 'name help'.split()):
                        docparam = None

            # Construct expected response data definition, if any, for successful response.
            response_def = param_parser.result
            result_typespec = response_def.type if response_def else ''
            if response_def:
                try:
                    result_type = (TypingJig.field_def_to_field(api, '<result>', dict(type=result_typespec),
                                                                nest_model=False)
                                   if result_typespec else None)
                    if result_typespec and not result_type:
                        raise TypingJig.TypeResolutionError
                except TypingJig.TypeResolutionError:
                    result_type = DefaultField()
                except (Exception, BaseException):
                    result_type = None
                # noinspection PyProtectedMember
                response_def = response_def._replace(type=result_type)
            response_type = getattr(response_def, 'type', None)
            marshaller = response_type if hasattr(response_type, 'container') else None

            # Wrap request handler function with the canonical assortment of Flask-RESTX decorators to document
            # request parameters, success response, any applicable security restrictions, and (optionally) the specific
            # SDK function name to generate, specifying Swagger models or aggregations thereof where appropriate.
            param_model = param_parser.model
            if sdk_name or param_model or auth:
                auths = getattr(api, 'authorizations') or {}
                security = auths and (auth.split() if isinstance(auth, str) else auth)
                if security:
                    if isinstance(security, bool):
                        security = [list(auths)[0]]
                    unknowns = set(compress(security, (k not in auths for k in security)))
                    if unknowns:
                        raise TypeError(f"Unknown authorization type(s): {unknowns} -- must be defined for API")
                else:
                    security = None
                resource_def = dict(body=param_model or None, id=sdk_name, security=security)
                header_params = getattr(param_parser, 'header_params', None)
                if header_params:
                    resource_def.update(dict(params=header_params))
                handler_wrapper = api.doc(**resource_def)(handler_wrapper)

            handler_wrapper = api.expect(param_parser)(handler_wrapper)
            if marshaller and not is_type(marshaller):  # (must be a field container type object)
                status_code = SwaggerNamespace.canonical_status_code(response_def.status)
                as_list = marshaller.__class__ == fields.List
                if as_list:  # (denest container(s) to bottommost contained type)
                    element = feedback(lambda fld, _: getattr(fld, 'container', None) or
                                                      (getattr(fld, 'nested', fld), StopIteration),  # noqa:E127
                                       marshaller, repeat('_'))
                    if is_model(element):
                        marshaller = element
                    elif is_field_type(element):
                        marshaller = None
                        # noinspection PyProtectedMember
                        response_def = response_def._replace(type=ArrayField())
                if marshaller:
                    handler_wrapper = api.marshal_with(marshaller, as_list=as_list, code=status_code,
                                                       description=getattr(response_def, 'help', None))(handler_wrapper)
            if not marshaller and response_def:
                handler_wrapper = api.response(*response_def)(handler_wrapper)
            for response in responses or ():
                # noinspection PyProtectedMember
                idx = ResponseDesc._fields.index('status')
                if not response_def or int(response_def[idx]) != int(response[idx]):
                    handler_wrapper = api.response(*response)(handler_wrapper)

            # Add handler-related members to the resource class.
            resource_attrs.update({method.lower(): handler_wrapper,
                                   cls.DEFAULT_PARSER_FMT.format(method=method.upper()): param_parser,
                                   cls.DEFAULT_SUCCESS_FMT.format(method=method.upper()): response_def,
                                   })

        # Generate resource class definition.
        # pylint:disable=undefined-loop-variable
        # noinspection PyUnboundLocalVariable
        target_name = (target.__name__ if callable(target) else target) or target_func.__name__
        resource_attrs['methods'] = tuple(methods)  # (bypass MethodViewType using non-deterministic set representation)
        resource_class = type(target_name, (base_class or cls,), resource_attrs)

        # Apply Swagger-able decorator to class for route parameter(s).
        if route_params:
            resource_class = api.doc(params=route_params)(resource_class)

        # If specified, hide this resource from documentation.
        if hidden:
            resource_class = api.hide(resource_class)

        # If this route has already been defined in this resource, presumably it defines a different HTTP method,
        # so merge this resource class definition into the existing resource.
        resroute = [rr for rr in namespace.resources if route in rr.urls]
        if resroute:
            resroute = resroute[0]
            existing_resource = resroute.resource
            existing_resource.methods = tuple(set(existing_resource.methods) | set(resource_class.methods))
            for key, val in vars(resource_class).items():
                if not key.startswith('__') and not hasattr(existing_resource, key):
                    setattr(existing_resource, key, val)
            classdef = resroute.resource
        else:
            # Apply the decorator to associate the route.
            classdoc = dict(params={docparam.name: docparam.help}) if docparam and param_model else None
            classdef = namespace.route(route, doc=classdoc)(resource_class)

        # Return the fully-decorated class definition.
        return classdef

    def parse_args(self, request=None, parser=None, strict=True):
        """
        Enhanced variant of the Flask-RESTX `RequestParser.parse_args()`: extracts and validates all HTTP
        request parameters ala Flask-RESTX, and segregates them into positional- vs. keyword-passed parameters
        for the handler function associated with the request, and does other parameter normalization.

        :param request: HTTP request (None => current Flask request)
        :type  request: flask.Request
        :param parser:  Flask-RESTX parser for an HTTP request (None => use canonical parser for this endpoint)
        :type  parser:  Union(flask_restx.RequestParser, None)
        :param strict:  "Parse arguments strictly, as defined by Flask-RESTX."
        :type  strict:  bool

        :return: Result:
                  [0]: Handler function associated with request
                  [1]: Positional parameters for handler
                  [2]: Keyword parameters for handler
        :rtype:  tuple
        """
        if not request:
            request = flask_request

        if not parser:
            parser = getattr(self, self.DEFAULT_PARSER_FMT.format(method=request.method.upper()), None)
        if not parser:
            args = ()
            kwargs = {}
        else:
            # Determine names of all positional parameters.
            positional = [arg.name for arg in parser.args if arg.required]

            # Accept non-standard JSON formatting extensions (if applicable).
            self.fixup_json(request)

            # Save original locations from argument definitions.
            locations = [arg.location for arg in parser.args]

            # Parse arguments, preprocessing as necessary beforehand, which may result in argument(s) being relocated
            # to query parameters (a Flask-RESTX workaround for `Argument.source()` deficiency).
            try:
                self.preprocess_args(request, parser.args, strict)
                parsed_args = parser.parse_args(request, strict=strict)  # (validate and extract param values)
            finally:
                # Reinstate original argument definition locations.
                for i, arg in enumerate(parser.args):
                    arg.location = locations[i]

            # Postprocess successfully parsed arguments: transform model types, etc.
            parsed_args = self.postprocess_args(request, parser.args, parsed_args)

            # Segregate param values by parameter-passing mode (positional vs. keyword).
            args, kwargs = (tuple(parsed_args.get(p) for p in positional),  # (segregate
                            {k: v for k, v in parsed_args.items() if k not in positional and not k.startswith('__')})
        return parser.func, args, kwargs

    @staticmethod
    def fixup_json(request):
        """
        Converts possible JSON content when specified non-conventionally in a request body.

        :param request: Flask request with JSON content possibly specified as body string or form data
        :type  request: flask.Request

        :return: Flask request with converted JSON content
        :rtype:  flask.Request

        .. note::
         * If JSON content is converted, the .json attribute of the Flask request is unassignable, so this instead
           uses the ._cached_json internal member to assign the JSON content to the request.
        """
        jsonval = None
        if request.is_json:  # (explicitly designated as (allowed) JSON content in request header)
            if not request.data:
                reqparams = request.values or request.args
                jsonval = reqparams.to_dict() if reqparams else {}
        else:  # (not designated as JSON content in request header, but may be)
            with suppress(Exception):
                if request.data:  # (body data)
                    jsonval = json.loads(request.data.decode())
                elif request.form:  # (accept form data that contains JSON-formatted data)
                    jsonval = json.loads(next(iter(request.form.to_dict())))
        if jsonval is not None:
            request._cached_json = (jsonval, jsonval)  # pylint:disable=protected-access
        return request

    @classmethod
    def preprocess_args(cls, request, reqargs, strict):  # noqa:C901
        """
        Performs any necessary preprocessing of arguments for type conversions, etc. prior to argument parsing.

        :param request: Flask request object
        :type  request: flask.request
        :param reqargs: Collection of argument definitions for Flask request
        :type  reqargs: Iterable
        :param strict:  "Validate model contents."
        :type  strict:  bool
        """
        argdefs = {arg.name: arg for arg in reqargs}
        # noinspection PyPropertyAccess
        request.args = request.args.to_dict()  # (make specified request arguments dictionary mutable)
        before = False

        for argname, argdef in argdefs.items():
            argval = request.args.get(argname, NotImplemented)
            argtype = getattr(argdef, 'type', None)
            model_arg = is_model(argtype)
            location = (argdef.location,) if isinstance(argdef.location, str) else argdef.location
            body_arg = any(loc in ('json', 'form') for loc in location)
            if model_arg:
                # Special case: model/aggregate param from request body -- only works for one param --
                # relocate to value params (Flask-RESTX deficiency) for this request
                if body_arg and not before:
                    if request.is_json:
                        argval = request.json.copy()
                        request.json.clear()
                    else:
                        argval = request.form or request.data
                    before = True
                if argval is not NotImplemented:
                    request.args[argname] = argval
                argdef.location = 'values'  # (caution: changes location persistently; must reinstate after parsing)

            if argval is NotImplemented:
                if 'json' in location and request.is_json:
                    argval = request.json.get(argname, NotImplemented)
                elif 'form' in location and request.form:
                    argval = request.form.get(argname, NotImplemented)

            if argval is not NotImplemented:
                # Consider "none" (text) as vacuous value for query param if value can be vacuous.
                if getattr(argdef, 'nullable', False) and argval in ('None', 'none') and request.args.get(argname):
                    # noinspection PyTypeChecker
                    request.args[argname] = None

                # Validate model contents when applicable.
                elif argtype is dict or model_arg:
                    request.args[argname] = argval = str_to_dict(argval)
                    if strict and isinstance(argtype, Model):
                        cls.validate_model_payload(argtype, argval)

    @classmethod
    def postprocess_args(cls, request, reqargs, argvals):  # noqa:C901
        """
        Performs any necessary postprocessing of arguments after parsing.

        :param request: Flask request object
        :type  request: flask.request
        :param reqargs: Collection of argument definitions for Flask request
        :type  reqargs: Iterable
        :param argvals: Parsed argument values
        :type  argvals: ParseResult

        :return: Adjusted parsed argument values
        :rtype:  ParseResult
        """
        argdefs = {arg.name: arg for arg in reqargs}
        for argname, argdef in argdefs.items():
            argtype = getattr(argdef, 'type', None)
            if is_model(argtype):
                argval = argvals.get(argname)
                if argval:
                    options = getattr(argtype, '_options', {})
                    skip_none = options.get('skip_none', False)
                    discard_missing = not options.get('store_missing', True)
                    reqval = request.args.get(argname, {})
                    for key in list(argval.keys()):
                        if ((skip_none or getattr(argdef.type.get(key), 'skip_none', False)) and argval[key] is None or
                                discard_missing and key not in reqval):
                            argval.pop(key)
                    argvals[argname] = type(argtype.name, (OmniDict,), {})(**argval)

        return argvals

    @staticmethod
    def validate_model_payload(model, model_dict):
        """ Validate that request body payload conforms to model definition. """
        try:
            model.validate(model_dict)  # (validate model values/types)
        except HTTPException as _exc:
            exc = _exc
            model_fields = {f for f, d in model.items() if type(d).__name__ in vars(fields)}
            extraneous = {f: "item not in model" for f in set(model_dict) - model_fields}
            if extraneous:
                if _exc:
                    getattr(_exc, 'data', {}).get('errors', {}).update(extraneous)
                else:
                    exc = werkzeug.exceptions.BadRequest()
                    exc.data = dict(message="Input payload validation failed", errors=extraneous)
            raise exc from _exc

    @classmethod
    def request_parser(cls, api, func=None, docfuncs=None, method=None, route_params=None, location=None):  # noqa:C901
        """
        Enhanced wrapper for a Flask-RESTX `RequestParser`: generates a request parser from the parameters and
        returns value definitions and commentary/annotations for a request-specific Python handler function.

        :param api:          Global Flask-RESTX API within which to define request parser (which may reference models)
        :type  api:          flask_restx.Api
        :param func:         Specific controller handler function for HTTP request, to generate a request parser for
                             (None => create a generic request parser; caller must specify all parameters/return value)
        :type  func:         Union(Callable, None)
        :param docfuncs:     Function or ([classname]->function) mapping from which to extract documentation
                             and parameter/return info (None => `func`; classname None => base class)
        :type  docfuncs:     Union(Callable, dict, None)
        :param method:       Expected HTTP method type for request (e.g., 'GET', 'POST', etc.)
        :type  method:       Union(str, None)
        :param route_params: Dictionary providing description(s) for any path parameter(s) embedded within `route`
        :type  route_params: Union(dict, None)
        :param location:     Flask-RESTX specification for where to harvest request parameters:
                              * str => location applied to all parameters
                              * Iterable => location(s) applied to all parameters
                              * dict => keyed by parameter, location applied to each; parameter absent => default
                             (None => default)
        :type  location:     Union(str, dict, Iterable, None)

        :return: Flask-RESTX parser for an HTTP request -- additional attributes defined:
                  * func: specific handler (controller) function for request
                  * method: HTTP method type for request
                  * params: Model for request parameters, if defined (None => parameters defined individually)
                  * result: `ResponseDesc` tuple describing the successful response from the handler function,
                            suitable for use with `api.response()` (None => N/A or undefined)
        :rtype:  flask_restx.RequestParser
        """
        # Extract synopsis/notes and from (any of) the handler function(s).
        docfunc = docfuncs or func
        if not docfunc:
            params, result, method = {}, {}, (method or DefaultHTTPMethod).upper()
        else:
            if callable(docfunc):
                docfuncs = {None: docfunc}

            # Extract parameter/result commentary and/or annotations from all handler functions, combining and
            # differentiating by class in the case of an inheritance lineage.
            def _tag_param(_clsname, _param):
                _match = re.fullmatch(PythonFuncDoc.PARAM_TAG_PATT, _param.get('help', ''))
                if _match:
                    _tag, _text = _match.groups()
                    _param['help'] = f"[{_tag}, {_clsname}] {_text[1:-1]}" if _tag else f"[{_clsname}] {_text}"
                return _param

            params, result, _method = PythonFuncDoc.extract_annotations(docfuncs.pop(None) or docfunc)
            method = (method or _method or DefaultHTTPMethod).upper()

            clsparams = OrderedDict({None: params})
            allkeys = set(params.keys())
            commonparams = None
            for clsname, svcfunc in docfuncs.items():
                if not clsname:
                    continue
                _params, _result, _ = PythonFuncDoc.extract_annotations(svcfunc)
                if not result:
                    result = _result  # @@@ TODO: Merge disparate result types among all (sub)classes
                clsparams[clsname] = _params = OrderedDict((k, _params[k]) for k in _params if k not in allkeys)
                commonparams = (_params if commonparams is None else
                                OrderedDict((k, v) for k, v in commonparams.items() if k in _params))
            params.update(commonparams or {})
            allkeys = set(params.keys())
            for clsname, _params in clsparams.items():
                if clsname:
                    # noinspection PyTypeChecker
                    params.update(OrderedDict((k, _tag_param(clsname, v))
                                              for k, v in _params.items() if k not in allkeys))

        # Create a vanilla Flask-RESTX request parser.
        parser = reqparse.RequestParser()

        # Add parser for each request parameter, in order.
        model = None
        headers = {}
        for name, param_def in params.items():
            if name in (route_params or {}):  # (ignore parameters specified by route)
                continue

            default_loc = (RequestLocationOther, RequestLocationGet)[method.upper() == 'GET']
            loc = param_def['location'] = (location.get(name, default_loc) if isinstance(location, dict) else
                                           location or default_loc)
            if loc == 'files':
                param_type = 'File'
            else:
                param_type = param_def.get('type', None)
                model = SwaggerModel.get(api, param_type)
                if model:
                    param_type = param_def['type'] = model
                    if len(params) > 1:
                        model = None
                    param_def['location'] = 'form' if 'form' in loc else 'json'

            if param_type == 'Password':
                param_def['location'] = 'form'
                param_def['type'] = Password
            elif param_type == 'header':
                headers[name] = {'in': 'header', 'description': re.sub(r' +', ' ', param_def.get('help', name))}
                continue
            elif param_type == 'File' or param_type.__class__.__name__ == 'FileStorage':
                param_def['location'] = 'files'
                param_type = param_def['type'] = FileStorage
            elif param_type and not is_model(param_type):
                param_type = param_def['type'] = TypingJig.typespec_to_param_converter(api, param_type, param_def)

            if not param_type:
                raise SwaggerAPIError(f"Invalid/missing parameter type specification for '{func.__qualname__}.{name}'")

            parser.add_argument(name, **param_def)

        # Supplement parser with contextual information about request handling.
        parser.func = func
        parser.method = method
        parser.model = model
        parser.header_params = headers
        # noinspection PyArgumentList
        parser.result = (ResponseDesc(HTTPStatus.OK if result else HTTPStatus.NO_CONTENT,
                                      (result or {}).get('help', "Success"),
                                      (result or {}).get('type', ""))
                         if result is not None else result)
        return parser

    @staticmethod
    def canonical_sdk_funcname(resource_name, method):
        """
        Constructs a canonical SDK function name.

        :param resource_name: Name for resource
        :type  resource_name: str
        :param method:        HTTP method (e.g., GET, POST, etc.)
        :type  method:        str

        :return: SDK function name
        :rtype:  str

        .. note::
         * Conforms to the Flask-RESTX method prototype called to provide an endpoint ID.
         * This method overrides the default naming conventions for SDK functions.
         * This method only affects SDK function naming; any rules-based endpoint naming
           overrides should affect the `route` parameter to `define_class()`.
        """
        return '_'.join((method, camel_to_dash(resource_name)))

    @staticmethod
    def construct_sdk_funcname(resource_name, method):
        """
        Uses rules to synthesize a terse, meaningful SDK function name from an HTTP method and resource name.
`
        (see :method:`canonical_sdk_funcname()` for details; use that function for a simple name translation)
        """
        method_redundancies = dict(get=['is', 'query', 'extract'], post=['set'])
        verb_redundancies = dict(get=['set', 'retrieve', 'collect'])
        replacements = dict(post='do')

        parts = camel_to_dash(resource_name).split('_')
        if parts[0] in method_redundancies.get(method, []) + [method]:
            prefix = []
        elif parts[0] in verb_redundancies.get(method, []):
            parts.pop(0)
            prefix = [method]
        else:
            prefix = [replacements.get(method, method)]

        return '_'.join(prefix + parts)

    @staticmethod
    def handle_request_exception(result):
        """ Handles an HTTP exception type returned from a request handler. """
        if isinstance(result, HTTPException):
            status = HTTPStatus_from_code(result.code)
            result = getattr(result, 'data', {}).get('message', getattr(result, 'description', str(result)))
        else:
            status = HTTPStatus.INTERNAL_SERVER_ERROR
        result = dict(message=str(result).strip())
        return result, status

    @staticmethod
    def sanitize_for_json(obj, as_json=False):
        """
        "Sanitizes" an object/value, converting it into a form suitable for conversion to JSON.

        :param obj:     Object/value to be encoded as JSON, possibly containing non-serializable items
        :type  obj:     object
        :param as_json: "Return JSONification of object." (otherwise, JSONifiable representation of object)
        :type  as_json: bool

        :return: JSONifiable object (or JSONification of object if `as_json`)
        :rtype:  Union(dict, str)

        .. note::
         * Sanitizes nested subdictionaries and lists, if specified or present as items within `obj`.
         * (Sub)objects containing a `__dict__` element are treated as dicts if direct serialization of them fails.
        """
        class _JSONEncoder(json.JSONEncoder):
            def default(self, item):  # pylint:disable=arguments-renamed
                try:
                    encoding = super().default(item)
                except TypeError:
                    if hasattr(item, '__encoder__'):
                        encoding = item.__encoder__(item)
                    else:
                        if hasattr(item, '__dict__'):
                            item = vars(item)
                        if isinstance(item, dict):
                            encoding = _encode(item)
                        elif isinstance(item, (list, tuple)):
                            encoding = [_encode(e) for e in item]
                        else:
                            encoding = str(item)
                return encoding

        def _encode(_obj, _load=True):
            _json = json.dumps(dictify(_obj), cls=_JSONEncoder)
            return json.loads(_json) if _load else _json

        return _encode(obj, _load=not as_json)


class SwaggerWrapper(flask_restx.swagger.Swagger):
    """ Overrides Flask-RESTX Swagger wrapper class, to permit custom hooks for Swagger spec processing. """
    NUMERICAL_STATUS_CODES = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @staticmethod
    def numerical_status_code(code):
        """ Represents HTTP status code as its numerical value. """
        if isinstance(code, str):
            with suppress(Exception):
                code = getattr(HTTPStatus, code.split('HTTPStatus.', maxsplit=1)[-1].replace(' ', '_'))
        return int(code)

    def as_dict(self):
        """ Postprocesses dictionary representation of Swagger specification. """
        self._registered_models = self.api.models  # (always include all models)
        try:  # pylint:disable=too-many-nested-blocks
            swagger_spec = super().as_dict()
            exclusions = []

            # Sweep through all defined resource endpoints.
            for path, resource in swagger_spec['paths'].items():
                # Omit any "internal" endpoints (with underscore-prefixed path name component).
                if '/_' in path:
                    exclusions.append(path)

                # Convert Flask-RESTX-misrepresented parameters of model type (data passed in body).
                for resource_def in resource.values():
                    if not isinstance(resource_def, dict):
                        continue
                    for param_def in resource_def.get('parameters', {}):
                        if not param_def.get('in') in ('body', 'formData'):  # (only body-passed parameters need fixing)
                            continue
                        schema = param_def.get('schema', {})
                        if schema.get('type') != 'object':  # (faulty schema: generic object instead of a model ref)
                            continue
                        for param_name, type_def in schema.get('properties', {}).items():
                            model_name = type_def.get('type')
                            if model_name in self._registered_models:
                                param_def['schema'] = {'$ref': f'#/definitions/{model_name}'}
                                param_def['name'] = param_name  # (also correct goofy parameter renaming to 'payload')
                            break  # (single properties definition)

            # Exclude endpoints for all resources with "private" names.
            for path in exclusions:
                del swagger_spec['paths'][path]

        except (Exception, BaseException) as exc:
            # noinspection PyTypeChecker
            locus = ''.join(traceback.format_tb(sys.exc_info()[-1]))
            self.api.log.error(f"ERROR: Failure to represent Swagger spec: {exc}\n{locus}")
            raise

        return swagger_spec

    def responses_for(self, doc, method):
        """ Converts all HTTP response status codes to numeric form, as expected by Swagger 2.0 specification. """
        # noinspection PyUnresolvedReferences
        if self.__class__.SWAGGER_NUMERIC_STATUS_CODES:
            for d in doc, doc[method]:
                responses = d.get('responses', {})
                for code, response in list(responses.items()):
                    responses[self.numerical_status_code(code)] = response
                    responses.pop(code)
        return super().responses_for(doc, method)


# pylint:disable=attribute-defined-outside-init
class SwaggerRequestHandler(WSGIRequestHandler):
    """ Overrides for official Flask/Werkzeug Request handler. """
    @staticmethod
    def _redact_path(path):
        """ Internal utility: Redacts sensitive query params from a path. """
        redacted = r'\w*password\w*|\w*token\w*'
        return re.sub(fr'({redacted})=[^ &]+', r'\1=...', path)

    @classmethod
    def redact_line(cls, line):
        """ Internal utility: Redacts sensitive query params from line containing a path. """
        with suppress(Exception):
            line = line.decode()
        with suppress(Exception):
            method, _path, *proto = line.split()
            line = ' '.join([method, cls._redact_path(_path)] + proto)
        return line.rstrip()

    # noinspection PyAttributeOutsideInit
    def log_request(self, code='-', size='-'):
        """ Override: Performs sensitive data redaction from query params when logging request params. """
        path = getattr(self, 'path', None)
        with suppress(Exception):
            if path:
                self.path = self._redact_path(path)
            else:
                self.requestline = self.redact_line(self.requestline)
        super().log_request(code=code, size=size)
        if path:
            self.path = path

    @classmethod
    def log_request_info(cls, request_info, prefix="Request: ", loglevel='info'):
        """ Logs request information, with redaction. """
        # pylint:disable=protected-access
        # noinspection PyProtectedMember
        getattr(werkzeug._internal._logger, loglevel)(f"{prefix}{cls.redact_line(request_info)}")

    def parse_request(self):
        """ Override: Logs request info just prior to start of request processing. """
        with suppress(Exception):
            self.log_request_info(self.raw_requestline)
        return super().parse_request()
