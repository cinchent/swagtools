#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generates Python SDK code from a Swagger (a.k.a. OpenAPI) API specification using 'swagger-codegen' open-source
code templates.

Copyright © 2022-2025 CINCH Enterprises, Ltd. and Rod Pullmann.  All rights reserved.
"""
# pylint:disable=too-many-lines
import sys
import os
import re
import argparse
from pathlib import Path
from textwrap import (dedent, indent, wrap, fill)
from collections import namedtuple
from contextlib import suppress
from zipfile import ZipFile
from datetime import datetime
import shutil
import json
import http

try:
    # noinspection PyPackageRequirements
    import yaml
except ImportError:
    yaml = None
# noinspection PyPackageRequirements
import pystache

# noinspection PyUnresolvedReferences,PyPackageRequirements
from swagger_python_codegen import __version__

THISDIR = Path(__file__).resolve().parent

PRINT = print
PRINT_VERBOSE = print

GENERATOR_NAME = THISDIR.stem
GENERATOR_URL = f"https://github.com/cinchent/{GENERATOR_NAME}.git"

TEMPLATE_VERSION = os.getenv('SWAGGER_CODEGEN_VERSION', "3.0.35")
TEMPLATE_DEFAULT = os.getenv('SWAGGER_CODEGEN_TEMPLATE_DEFAULT',
                             f"/opt/swagger-codegen/swagger-codegen-cli-{TEMPLATE_VERSION}.jar")
TEMPLATE_OVERRIDE_DIR = THISDIR.joinpath('templates')
TEMPLATE_EXT = '.mustache'
TEMPLATE_PARTIALS = [
    'partial_header'
]
TemplateInfo = namedtuple('TemplateInfo', 'dest_fmt vars options')

MultiprocessingLibraries = dict(multiprocessing=True, concurrent_futures=False)  # (default marked True)

TEMPLATES = dict(  # (ordering is significant)
    model=TemplateInfo('{packageName}/{model_package}/', dict(hasMore=True), {}),
    __init__model=TemplateInfo('{packageName}/{model_package}/__init__.py', {}, {}),
    api=TemplateInfo('{packageName}/{api_package}/', dict(operations=True, hasMore=True), {}),
    __init__api=TemplateInfo('{packageName}/{api_package}/__init__.py', {}, {}),
    __init__package=TemplateInfo('{packageName}/__init__.py', {}, {}),
    api_client=TemplateInfo('{packageName}/api_client.py', {**dict(writeBinary=True),
                                                            **MultiprocessingLibraries}, {}),
    configuration=TemplateInfo('{packageName}/configuration.py', {}, {}),
    rest=TemplateInfo('{packageName}/rest.py', {}, {}),
    requirements=TemplateInfo('requirements.txt', {}, {}),
    setup=TemplateInfo('setup.py', {}, {}),
)
TEMPLATES_OPTIONAL = dict(  # (optional templates processed by '--generate' specification)
    docs={
        'api_doc': TemplateInfo('docs/', {}, {}),
        'model_doc': TemplateInfo('docs/', {}, {}),
        'README': TemplateInfo('README.md', dict(gitUserId="GIT_USER_ID",
                                                 gitRepoId="GIT_REPO_ID",
                                                 generatedDate=datetime.isoformat(datetime.now(), sep=' ',
                                                                                  timespec='seconds'),
                                                 generatorClass=Path(sys.argv[0]).stem,
                                                 appVersion='{packageVersion}',
                                                 infoUrl='{packageUrl}',
                                                 hasMore=True,
                                                 ), {}),
    },
    tests={
        '__init__test': TemplateInfo('test/__init__.py', {}, {}),
        'api_test': TemplateInfo('test/', {}, {}),
        'model_test': TemplateInfo('test/', {}, {}),
        'test-requirements': TemplateInfo('test-requirements.txt', {}, {}),
    },
    git={
        'gitignore': TemplateInfo('.gitignore', {}, {}),
        'git_push.sh': TemplateInfo('git_push.sh', dict(gitUserId="GIT_USER_ID",
                                                        gitRepoId="GIT_REPO_ID",
                                                        releaseNote="Minor update"), {}),
        'tox': TemplateInfo('tox.ini', {}, {}),
    },
    travis={
        'travis': TemplateInfo('.travis.yml', {}, {}),
    },
)
TEMPLATES_ASYNC = {  # (optional templates processed by '--async_library' option)
    'asyncio/rest': TemplateInfo('{packageName}/rest.py', dict(asyncio=True), {}),
    'tornado/rest': TemplateInfo('{packageName}/rest.py', dict(tornado=True), {}),
}


class TemplateReader:  # pylint:disable=too-few-public-methods
    """
    Custom template reader: provides a reader method to read a template file from a directory or JAR,
    optionally overriding a default template with a custom one.
    """
    TemplateSource = namedtuple('TemplateSource', 'location base_path jar')

    def __init__(self, location, alternate=None):  # pylint:disable=unused-argument
        """ Initializer: Constructs the template reader. """
        # Validate template sources for main and alternate locations.
        for (src, src_desc) in (('location', "Template location"), ('alternate', "Alternate template location")):
            src_path = locals().get(src)
            if not src_path:
                setattr(self, src, None)
                continue
            src_path = Path(src_path).expanduser()
            if not src_path.exists():
                raise FileNotFoundError(f"{src_desc} '{src_path}' is absent")
            setattr(self, src, src_path)

            if src_path.suffix == '.jar':
                base_path = Path('python')
                jar = ZipFile(str(src_path))  # pylint:disable=consider-using-with
            else:
                if not src_path.is_dir():
                    raise FileNotFoundError(f"If not a JAR file, {src_desc.lower()} '{src_path}' must be a directory")
                base_path = src_path
                jar = None
            setattr(self, src, self.TemplateSource(src_path, base_path, jar))

    def read(self, filename, **options):
        """ Reads template file content from a directory or JAR, subject to override. """
        # noinspection PyUnusedLocal
        content, read_ok = None, False
        # First look for template in alternate (override) location, then in default location.
        for src in options.get('sources', ('alternate', 'location')):
            with suppress(Exception):
                template_source = getattr(self, src)
                path = Path(str(template_source.base_path.joinpath(filename)) + TEMPLATE_EXT)  # (not .with_suffix())
                if template_source.jar:
                    content = template_source.jar.read(str(path)).decode()
                else:
                    content = path.read_text(encoding='utf-8')
                read_ok = True
                break
        if not read_ok:
            raise ValueError(f"Unable to read template '{filename}'")
        return content


class Generator:
    """ SDK code generator. """

    def __init__(self, settings, params):
        # Record and rationalize passed parameters and settings.
        self.settings = self.resolve_settings(settings)
        self.params = self.resolve_params(params)

        # Parse input Swagger specification.
        self.input_file = Path(params.input_spec).expanduser()
        if not self.input_file.is_file():
            raise FileNotFoundError(f"ERROR: input file '{self.input_file}' absent")
        raw_spec = self.input_file.read_text(encoding='utf-8')
        if yaml:
            self.swagger_spec = yaml.safe_load(raw_spec)
        else:
            try:
                self.swagger_spec = json.loads(raw_spec)
            except (Exception, BaseException) as exc:
                raise TypeError(f"Input file '{self.input_file}' exists, but you have no Python YAML support") from exc

        # Apply any specified fixes to Swagger specification.
        if 'http_response' in self.params.fix:
            self.swagger_spec = self.fix_response_http_codes(self.swagger_spec)

        # Parse the top-level API info from the Swagger spec.
        self.info = self.dict_translate(self.swagger_spec.get('info', {}),
                                        dict(title='appName', description='appDescription', email='infoEmail'))
        self.info.update(dict(generatorName=GENERATOR_NAME, generatorURL=GENERATOR_URL,
                              appName=self.info.get('appName', '').split('(')[0].rstrip()))

        # Fully resolve all template definitions and variables from settings and parameters.
        other_vars = dict(version='0.0.{}'.format(int(float(self.swagger_spec.get('swagger', 2)))),
                          basePath=self.swagger_spec.get('basePath', ''))
        async_library = self.settings.get('asyncLibrary')
        if async_library:
            TEMPLATES.pop('rest', None)
            template_name = f"{async_library}/rest"
            template_info = TEMPLATES_ASYNC.get(template_name)
            if template_info:
                TEMPLATES.update({template_name: template_info})
                other_vars.update(template_info.vars)
        else:
            library = self.settings.get('library')
            if library == GENERATOR_SETTINGS['library']['default']:
                # noinspection PyProtectedMember
                TEMPLATES['rest'] = TEMPLATES['rest']._replace(options=dict(sources=('location',)))

        multiprocessing_library = self.settings.get('multiprocessingLibrary')
        if multiprocessing_library:
            api_client_vars = TEMPLATES['api_client'].vars
            for k in api_client_vars:
                if k in MultiprocessingLibraries:
                    api_client_vars[k] = k == multiprocessing_library
            if sum(api_client_vars[k] for k in MultiprocessingLibraries) != 1:
                raise ValueError(f"Exactly one of {set(MultiprocessingLibraries)} must be specified"
                                 " for 'multiprocessingLibrary' option")

        self.common_vars = {**vars(self.params), **self.settings, **self.info, **other_vars}
        TEMPLATES.update({t: d for g in self.params.generate for t, d in TEMPLATES_OPTIONAL.get(g, {}).items()})
        self.template_dests = {k: v.dest_fmt.format(**self.common_vars) for k, v in TEMPLATES.items()}
        self.template_vars = {k: v.vars for k, v in TEMPLATES.items()}

        # Extract other top-level definitions for API:
        #  - Request MIME types
        consumes = self.swagger_spec.get('consumes', [])
        # noinspection PyTypeChecker
        self.common_vars.update(dict(hasConsumes=bool(consumes), consumes=[dict(mediaType=m) for m in consumes]))

        #  - Response MIME types
        produces = self.swagger_spec.get('produces', [])
        # noinspection PyTypeChecker
        self.common_vars.update(dict(hasProduces=bool(produces), produces=[dict(mediaType=m) for m in produces]))

        #  - Authentication methods in use among all resource groups
        self.auth_methods = self.swagger_spec.get('securityDefinitions', {})

        # Read all templates and partials.
        self.template_reader = TemplateReader(params.template_dir, alternate=TEMPLATE_OVERRIDE_DIR)
        partials = {template_file: self.template_reader.read(template_file) for template_file in TEMPLATE_PARTIALS}
        self.templates = {template_file: self.template_reader.read(template_file, **template_entry.options)
                          for template_file, template_entry in TEMPLATES.items()}

        # Resolve all settings and parameters passed in common to all renderers.
        package_name = self.settings.get('packageName', '')
        # noinspection PyTypeChecker
        self.common_vars.update(dict(apiPackage=f"{package_name}.{self.params.api_package}",
                                     modelPackage=f"{package_name}.{self.params.model_package}",
                                     httpUserAgent=self.params.http_user_agent))
        self.common_vars.update({'-first': self.once})

        # Create a Mustache renderer, specifying any partials.
        self.renderer = pystache.Renderer(partials=partials)
        self.template_firsts = {}

        # Resolve where output will be generated.
        self.output_base = Path(params.output).expanduser()

    @staticmethod
    def resolve_settings(settings):
        """ Performs any necessary runtime validation/resolution of generator settings. """
        return settings

    def resolve_params(self, params):
        """ Performs any necessary runtime validation/resolution for specified command-line options. """
        params.http_user_agent = params.http_user_agent.format(**self.settings)
        return params

    def resolve_vars(self, _vars, common_vars=None):
        """ Performs any symbolic substitutions from common variable definitions within specific template variables. """
        return {k: v.format(**(common_vars if common_vars is not None else self.common_vars))
                if isinstance(v, str) else (v or {}) for k, v in _vars.items()}

    @staticmethod
    def snake_to_camel(snake, capitalize=True):
        """ Utility function: Returns the camel-case identifier corresponding to a snake-case identifier. """
        camel = '_' if snake.startswith('_') else ''
        camel += ''.join(s.capitalize() if i or capitalize else s for i, s in enumerate(snake.lstrip('_').split('_')))
        return camel

    @staticmethod
    def camel_to_snake(camel):
        """ Utility function: Returns the snake-case identifier corresponding to a camel-case identifier. """
        return ''.join(f"_{s.lower()}" if i % 2 else s for i, s in enumerate(re.split(r'([A-Z]+)', camel))).lstrip('_')

    @staticmethod
    def str_to_identifier(string, lowercase=True):
        """ Utility function: Returns the identifier corresponding to a string value. """
        ident = string.replace('-', '_')
        return ident.lower() if lowercase else ident

    @staticmethod
    def dict_translate(_dict, translations):
        """ Utility function: translates keys within a dictionary. """
        for _from, _to in translations.items():
            if _from in _dict:
                _dict[_to] = _dict[_from]
                del _dict[_from]
        return _dict

    @staticmethod
    def assign_bounds(_dict, idx, count=None):
        """ Assign special Mustache "bounds" variables, depending on element position in a sequence. """
        if idx == 0:
            _dict['first'] = True
        if idx == (count or 0) - 1:
            _dict['last'] = True
        return _dict

    def define_security_vars(self, auth_methods):
        """ Defines all security-related vars for the specified list of applicable authorization methods. """
        auth_methods = {m: self.auth_methods[m] for m in auth_methods if m in self.auth_methods}
        method_list = []
        for i, method in enumerate(auth_methods):
            method_def = auth_methods.get(method, {})
            method_type = method_def.get('type')
            method_vars = self.assign_bounds(dict(name=method), i, len(auth_methods))
            if method_type == 'basic':
                method_vars.update(isBasic=True)
            elif method_type == 'oauth2':
                scopes = method_def.get('scopes', {})
                method_vars.update({**method_def, **dict(isOAuth=True, scopes=bool(scopes), scope=scopes)})
            elif method_type == 'apiKey':
                loc = method_def.get('in')
                method_vars.update(dict(isApiKey=True,
                                        isKeyInHeader=loc == 'header',
                                        isKeyInQuery=loc == 'query',
                                        keyParamName=method_def.get('name')))
            method_list.append(method_vars)
        return dict(hasAuthMethods=bool(method_list), authMethods=method_list)

    def convert_data_type(self, data_item):
        """
        Parses a typed data item descriptor and translates the Swagger data/model type contained there to a Python type,
        or constructs a composite type descriptor from a nested type definition there.
        """
        translations = {**dict(string='str', number='float', integer='int', boolean='bool'),
                        **self.params.import_mappings}

        def _parse_type(_typedef):
            """ Recursive parser for (possibly nested) type definitions: """
            _type = _typedef.get('$ref')
            if _type:
                _type = _type.split('/')[-1]
            else:
                _type = _typedef.get('schema')
                if _type:
                    _type = _parse_type(_type)
                else:
                    _type = _typedef.get('type')
                    if _type:
                        if _type == 'array':
                            _subtype = _parse_type(_typedef.get('items'))
                            _type = f"list[{_subtype}]"
                        else:
                            _type = translations.get(_type, _type)
            return _type

        return _parse_type(data_item or {}) or None

    @staticmethod
    def example_value_string(typedef, varname, default=NotImplemented):
        """ Creates an example value code element for a variable of a known type. """
        value = None
        if typedef == 'bool':
            value = default if default is not NotImplemented else False
            if isinstance(default, str):
                value = default.lower() == 'true'
            value = str(value)
        elif typedef == 'str' or not typedef:
            if default is NotImplemented:
                default = f"{varname}_example"
            value = f'''"{default}"'''
        elif typedef in ('int', 'float'):
            value = (f"{varname}_example" if default is NotImplemented else
                     int(default) if typedef == 'int' else float(default))
        elif typedef == 'dict':
            # noinspection PyTypeChecker
            value = f"dict(example_{varname}_item=...)" if default is NotImplemented else dict(default)
        elif typedef.startswith('list'):
            # noinspection PyTypeChecker
            value = f"[example_{varname}_item, ...]" if default is NotImplemented else list(default)
        return str(value)

    @staticmethod
    def multiline_description(attr_def, indentation=8):
        """ Formats a multiline description for a resource or attribute into an indented paragraph. """
        desc = attr_def.get('description', '')
        if '\n' in desc:
            ind = indentation * ' '
            desc = indent(desc + '\n', ind).strip()
        return desc

    def check_output_overwrite(self, dest_path):
        """ Safeguards against overwrite of output file or directory when overwrite is forbidden. """
        overwrite_ok = True
        if dest_path.exists():
            if self.params.skip_overwrite:
                PRINT(f"WARNING: output file '{dest_path}' exists, but --skip-overwrite specified;"
                      " refusing to overwrite")
                overwrite_ok = False
            if not dest_path.is_file():
                raise FileExistsError(f"ERROR: '{dest_path}' exists and is not a file; refusing to overwrite")
        return overwrite_ok

    @staticmethod
    def fix_response_http_codes(swagger_spec):
        """ Makes all HTTP response codes among endpoint definitions in the Swagger specification consistent."""
        def _fix(_out, _in):
            for key, val in _in.items():
                if key.startswith('HTTPStatus.'):
                    key = str(int(getattr(http.HTTPStatus, key.split('.', maxsplit=1)[-1])))
                _out[key] = _fix({}, val) if isinstance(val, dict) else val
            return _out

        return _fix({}, swagger_spec)

    @staticmethod
    def fix_module_initial_comments(rendered_text):
        """ Corrects ill-formed module initial comments with well-formed ones. """
        match = re.search(r'^#!', rendered_text, re.MULTILINE)
        if match:
            rendered_text = rendered_text[match.start():]
        return rendered_text

    def render(self, path, template, *context, **kwargs):
        """
        Wrapper for Pystache rendering method to automatically apply any generic post-rendering fixes specified.
        """
        output = self.renderer.render(template, *context, **kwargs)
        if 'module_comment' in self.params.fix and Path(path).suffix == '.py':
            output = self.fix_module_initial_comments(output)
        return output

    def once(self, hashable):
        """ Rendering lambda: Renders a Mustache Section Context at most once during the rendering of a template. """
        never = hashable not in self.template_firsts
        self.template_firsts.setdefault(hashable)
        return hashable if never else ''

    def generate(self):
        """ Generates the SDK. """
        # Ensure that output directories are cleared, unless overwrite is forbidden.
        if self.output_base.exists() and not self.params.skip_overwrite:
            shutil.rmtree(self.output_base, ignore_errors=True)

        for output_dir in ('', self.settings['packageName']):
            os.makedirs(self.output_base.joinpath(output_dir), exist_ok=True)

        # For each Mustache template in use...
        for template_name, template_dest in self.template_dests.items():
            template_dest_path = self.output_base.joinpath(template_dest)
            self.template_firsts = {}
            custom_renderer = getattr(self, f'render_{template_name}', None)

            # Simple file template: render content directly using simple renderer,
            template_vars = self.resolve_vars(self.template_vars[template_name])
            if not template_dest.endswith('/'):
                if not self.check_output_overwrite(template_dest_path):
                    continue
                template_vars = {**self.common_vars, **template_vars}
                if callable(custom_renderer):
                    custom_renderer(template_name, template_dest_path, template_vars)
                else:
                    output = self.render(template_dest_path, self.templates[template_name], template_vars)
                    os.makedirs(template_dest_path.parent, exist_ok=True)
                    template_dest_path.write_text(output, encoding='utf-8')
                PRINT(f"Generated '{template_name}' to '{template_dest}'")
                continue

            # Otherwise, rendering for multiple files in a directory: ensure directories are cleared,
            # unless overwrite is forbidden,
            if template_dest_path.exists():
                if not template_dest_path.is_dir():
                    raise FileExistsError(f"ERROR: '{template_dest}' exists, but is not a directory;"
                                          " refusing to overwrite")
            else:
                os.makedirs(template_dest_path, exist_ok=True)

            # Invoke custom renderer for each directory template.
            if not callable(custom_renderer):
                raise NotImplementedError(f"ERROR: {custom_renderer}() not implemented; cannot continue")
            custom_renderer(template_name, template_dest_path, template_vars)
            PRINT(f"Generated '{template_name}' to directory '{template_dest}'")

    def render_model(self, template_name, template_dest_path, template_vars):
        """ Renders the SDK models defined for the API. """
        PRINT_VERBOSE("--- Processing API models for code generation:")
        model_name = '<unknown>'
        try:
            # Process each model defined in the Swagger spec...
            all_models = {}
            models = self.swagger_spec.get('definitions', {})
            for model_name, model_def in models.items():
                PRINT_VERBOSE(f"Processing model '{model_name}'...")

                # Extract all attributes for model, and rationalize data types to Python.
                attrs = model_def.get('properties', {})
                class_name = f"{self.params.model_name_prefix}{model_name}{self.params.model_name_suffix}"
                model_module = self.camel_to_snake(class_name)
                required = model_def.get('required', [])

                # Record all applicable rendering variables for model.
                nattrs = len(attrs)
                model_vars = [{**self.dict_translate(attr_def, dict(default='defaultValue')),
                               **self.assign_bounds(dict(
                                   baseName=attr_name,
                                   name=self.str_to_identifier(attr_name, lowercase=False),
                                   datatype=self.convert_data_type(attr_def),
                                   required=attr_name in required,
                                   description=self.multiline_description(attr_def),
                               ), i, nattrs),
                               }
                              for i, (attr_name, attr_def) in enumerate(attrs.items())]
                all_models[model_name] = dict(classname=class_name, modulename=model_module, classFilename=model_module,
                                              vars=model_vars)

            # Denote that model definitions exist, unless they're vacuous.
            # noinspection PyTypeChecker
            self.common_vars['models'] = bool(all_models)

            # Render output modules for all models defined in API...
            template = self.templates[template_name]
            for model_name, model in all_models.items():
                PRINT_VERBOSE(f"Generating code for model '{model_name}'...")
                model_path = template_dest_path.joinpath(model['modulename']).with_suffix('.py')
                if not self.check_output_overwrite(model_path):
                    continue
                output = self.render(model_path, template, {**self.common_vars, **template_vars, **dict(model=model)})
                model_path.write_text(output, encoding='utf-8')
                PRINT_VERBOSE(f"Generated model '{model_name}' to '{template_dest_path}'")

            # Record model naming definitions globally, for use by other templates.
            # noinspection PyTypeChecker
            self.common_vars['model'] = list(all_models.values())

        except (Exception, BaseException) as exc:
            raise RuntimeError(f"ERROR: Failure rendering template '{template_name}'"
                               f" (model '{model_name}'): {exc}") from exc

    # pylint:disable=too-many-locals
    def render_api(self, template_name, template_dest_path, template_vars):  # noqa: C901
        """ Renders the SDK modules/classes/methods for the API. """
        PRINT_VERBOSE("--- Processing API resources for SDK code generation:")
        group_name = '<unknown>'
        try:  # pylint:disable=too-many-nested-blocks
            # Process each API resource group defined in the Swagger spec...
            apis = {}
            tags = self.swagger_spec.get('tags', [])
            for resource_group in tags:
                # Extract group-specific definitions.
                group_name = resource_group.get('name')
                if not group_name:
                    continue
                PRINT_VERBOSE(f"Processing resource group '{group_name}'...")
                module_name = f"{group_name.replace('/', '')}_api"
                class_name = self.snake_to_camel(module_name)
                apis[group_name] = group = dict(apiPackage=f"{self.settings['packageName']}.{self.params.api_package}",
                                                classVarName=module_name, classname=class_name)

                # Process each resource (and for all HTTP methods if multiple exist) in the resource group...
                resource_list = []
                for resource_path, resource_methods in self.swagger_spec.get('paths', {}).items():
                    for http_method, resource_def in resource_methods.items():
                        # Process resource definition only if it is a member of the resource currently being processed.
                        if not isinstance(resource_def, dict):
                            continue
                        resource_tags = resource_def.get('tags', [])
                        if group_name not in resource_tags:
                            continue
                        PRINT_VERBOSE(f"  Processing resource endpoint {http_method.upper()} {resource_path}...")
                        resource_vars = resource_def

                        # Extract security options for this resource, if any are in use.
                        resource_security = [next(iter(m)) for m in resource_def.get('security', [])]
                        if resource_security:
                            resource_vars.update(self.define_security_vars(resource_security))

                        # Extract all resource parameters and rationalize data types to Python.
                        all_params = [p.copy() for p in resource_methods.get('parameters', [])]
                        all_params.extend(resource_def.get('parameters', []))
                        nparams = len(all_params)
                        for i, param in enumerate(all_params):
                            name = param.get('name', '')
                            is_file = param.get('type') == 'file'
                            param.update(dict(baseName=name,
                                              paramName=self.str_to_identifier(name),
                                              dataType=self.convert_data_type(param),
                                              isFile=is_file, notFile=not is_file,
                                              description=param.get('description', ''),
                                              ))
                            self.assign_bounds(param, i, nparams)
                            all_params[i] = param

                        # Segregate parameters by source location within API requests.
                        resource_vars['allParams'] = all_params
                        for (var, indic) in (('pathParams', 'path'),
                                             ('queryParams', 'query'),
                                             ('headerParams', 'header'),
                                             ('formParams', 'formData'),
                                             ('bodyParam', 'body'),
                                             ):
                            resource_vars[var] = [d for d in all_params if d.get('in') == indic]

                        # Extract all MIME types recognized for this resource, provided body or form data is expected.
                        consumes = resource_def.get('consumes', [])
                        if consumes:
                            resource_vars.update(dict(hasConsumes=True, consumes=[dict(mediaType=m) for m in consumes]))
                        if not resource_vars['formParams'] and not resource_vars['bodyParam']:
                            resource_vars.update(dict(hasConsumes=False, consumes=[]))

                        # Extract return type for resource.
                        response_schema = {}
                        for response in resource_def.get('responses', {}).values():
                            response_schema = response.get('schema', {})
                            if response_schema:
                                break

                        # Record all applicable rendering variables for resource.
                        ind = 8 * ' '
                        resource_vars.update(
                            dict(path=resource_path,
                                 httpMethod=http_method.upper(),
                                 operationIdLowerCase=resource_vars.get('operationId', '').lower(),
                                 returnType=self.convert_data_type(response_schema),
                                 summary=indent('\n' + re.sub(r'  +', '\n', resource_vars.get('summary', '')).rstrip(),
                                                ind),
                                 notes=self.multiline_description(resource_vars),
                                 ))
                        self.assign_bounds(resource_vars, len(resource_list))
                        resource_list.append(resource_vars)

                nresources = len(resource_list)
                if nresources:
                    self.assign_bounds(resource_list[-1], nresources - 1, nresources)

                # Record all applicable rendering variables for resource group.
                group['operation'] = resource_list

            # Render API output modules for all resource groups defined in API...
            template = self.templates[template_name]
            for group_name, api_vars in apis.items():
                # Skip vacuous resource groups.
                api_module = api_vars.get('classVarName')
                if not api_module or not api_vars.get('operation'):
                    PRINT_VERBOSE(f"Ignoring vacuous API '{group_name}': no resources defined")
                    del apis[group_name]  # pylint:disable=unnecessary-dict-index-lookup
                    continue
                api_vars['operations'] = True

                # Render code for resource group.
                PRINT_VERBOSE(f"Generating code for API '{group_name}'...")
                api_path = template_dest_path.joinpath(api_module).with_suffix('.py')
                if not self.check_output_overwrite(api_path):
                    continue
                output = self.render(api_path, template, {**self.common_vars, **template_vars, **api_vars})
                os.makedirs(api_path.parent, exist_ok=True)
                api_path.write_text(output, encoding='utf-8')
                PRINT_VERBOSE(f"Generated API '{group_name}' to '{template_dest_path}'")

            # Supplement and adjust API resource definitions, for use by other templates.
            for i, group in enumerate(apis.values()):
                self.assign_bounds(group, i, len(apis))
                for oper in group.get('operation', []):
                    oper['summary'] = dedent(oper.get('summary', '')).strip().replace('\n', ' ').replace('  ', ' ')
                    for param in oper.get('allParams', []):
                        param_name = param.get('paramName', '')
                        default = param.get('default', NotImplemented)
                        description = re.sub(r'\n  +', ' ', param.get('description', ''))
                        example = self.example_value_string(param.get('dataType'), param_name, default)
                        param.update(description=description, example=example,
                                     defaultValue=None if default is NotImplemented else default)
            # noinspection PyTypeChecker
            self.common_vars['apiInfo'] = bool(apis)
            # noinspection PyTypeChecker
            self.common_vars['apis'] = list(apis.values())
            # noinspection PyTypeChecker
            self.common_vars.update(self.define_security_vars(self.auth_methods))

        except (Exception, BaseException) as exc:
            raise RuntimeError(f"ERROR: Failure rendering template '{template_name}'"
                               f" (resource group '{group_name}'): {exc}") from exc

    def render_api_client(self, template_name, template_dest_path, template_vars):
        """ Renders the API client module for the SDK. """
        content = self.render(template_dest_path, self.templates[template_name], template_vars)
        if 'thread_pool' in self.params.fix:
            if 'def pool' in content:  # (newer template, using property for pool member)
                setter = indent(dedent("""\
                                       @pool.setter
                                       def pool(self, _pool):
                                           self._pool = _pool
                                       """), 4 * ' ')
                content = re.sub(r'(return *self._pool.*\n)', f"\\1\n{setter}", content)
            else:  # (legacy, using attribute for pool member)
                content = re.sub(r'\n( +)self\.pool *= *ThreadPool',
                                 "from unittest.mock import Mock\n\\1self.\\2pool = Mock",
                                 content)
        os.makedirs(template_dest_path.parent, exist_ok=True)
        template_dest_path.write_text(content, encoding='utf-8')

    def render_model_doc(self, template_name, template_dest_path, template_vars):
        """ Renders the SDK documentation for each defined model in the API. """
        PRINT_VERBOSE("--- Processing API models for documentation generation:")
        model_name = '<unknown>'
        try:
            # Process all defined models...
            for model_vars in self.common_vars.get('model', []):
                model_name = model_vars.get('classFilename')
                model_classname = model_vars.get('classname')
                if not model_classname or not model_classname:
                    continue

                PRINT_VERBOSE(f"Generating documentation for model '{model_name}'...")
                docfile = template_dest_path.joinpath(model_classname).with_suffix('.md')
                if not self.check_output_overwrite(docfile):
                    continue
                output = self.render(docfile, self.templates[template_name],
                                     {**self.common_vars, **dict(model=[model_vars]), **template_vars})
                os.makedirs(docfile.parent, exist_ok=True)
                docfile.write_text(output, encoding='utf-8')
                PRINT_VERBOSE(f"Generated '{template_name}' to '{docfile}'")

        except (Exception, BaseException) as exc:
            raise RuntimeError(f"ERROR: Failure rendering template '{template_name}'"
                               f" (model '{model_name}'): {exc}") from exc

    def render_api_doc(self, template_name, template_dest_path, template_vars):
        """ Renders the SDK documentation for each resource group in the API. """
        PRINT_VERBOSE("--- Processing API resources for documentation generation:")
        group_name = '<unknown>'
        try:
            # Process all API resource groups...
            for group_vars in self.common_vars.get('apis', []):
                group_name = group_vars.get('classVarName')
                group_classname = group_vars.get('classname')
                if not group_classname or not group_classname:
                    continue

                PRINT_VERBOSE(f"Generating documentation for resource group API '{group_name}'...")
                docfile = template_dest_path.joinpath(group_classname).with_suffix('.md')
                if not self.check_output_overwrite(docfile):
                    continue
                output = self.render(docfile, self.templates[template_name],
                                     {**self.common_vars, **group_vars, **template_vars})
                os.makedirs(docfile.parent, exist_ok=True)
                docfile.write_text(output, encoding='utf-8')
                PRINT_VERBOSE(f"Generated '{template_name}' to '{docfile}'")

        except (Exception, BaseException) as exc:
            raise RuntimeError(f"ERROR: Failure rendering template '{template_name}'"
                               f" (resource group '{group_name}'): {exc}") from exc

    def render_model_test(self, template_name, template_dest_path, template_vars):
        """ Renders the unit test skeletons for each defined model in the API. """
        PRINT_VERBOSE("--- Processing API models for unit test skeleton generation:")
        model_name = '<unknown>'
        try:
            # Process all defined models...
            for model_vars in self.common_vars.get('model', []):
                model_name = model_vars.get('classFilename')
                model_classname = model_vars.get('classname')
                if not model_classname or not model_classname:
                    continue

                PRINT_VERBOSE(f"Generating unit test skeletons for model '{model_name}'...")
                testfile = template_dest_path.joinpath(f"test_{model_name}").with_suffix('.py')
                if not self.check_output_overwrite(testfile):
                    continue
                output = self.render(testfile, self.templates[template_name],
                                     {**self.common_vars, **dict(model=[model_vars]), **template_vars})
                os.makedirs(testfile.parent, exist_ok=True)
                testfile.write_text(output, encoding='utf-8')
                PRINT_VERBOSE(f"Generated '{template_name}' to '{testfile}'")

        except (Exception, BaseException) as exc:
            raise RuntimeError(f"ERROR: Failure rendering template '{template_name}'"
                               f" (model '{model_name}'): {exc}") from exc

    def render_api_test(self, template_name, template_dest_path, template_vars):
        """ Renders the unit test skeletons for each resource group in the API. """
        PRINT_VERBOSE("--- Processing API resources for unit test skeleton generation:")
        group_name = '<unknown>'
        try:
            # Process all API resource groups...
            for group_vars in self.common_vars.get('apis', []):
                group_name = group_vars.get('classVarName')
                group_classname = group_vars.get('classname')
                if not group_classname or not group_classname:
                    continue

                PRINT_VERBOSE(f"Generating unit test skeletons for resource group API '{group_name}'...")
                testfile = template_dest_path.joinpath(f"test_{group_name}").with_suffix('.py')
                if not self.check_output_overwrite(testfile):
                    continue
                output = self.render(testfile, self.templates[template_name],
                                     {**self.common_vars, **group_vars, **template_vars})
                os.makedirs(testfile.parent, exist_ok=True)
                testfile.write_text(output, encoding='utf-8')
                PRINT_VERBOSE(f"Generated '{template_name}' to '{testfile}'")

        except (Exception, BaseException) as exc:
            raise RuntimeError(f"ERROR: Failure rendering template '{template_name}'"
                               f" (resource group '{group_name}'): {exc}") from exc


# ------------------------------------------------
GENERATOR_SETTINGS = dict(  # (defined to be compatible with 'swagger-codegen')
    packageName=dict(
        type=str,
        help="Python package name (convention: snake_case)",
        default='sdk'),
    projectName=dict(
        type=str,
        help="Python project name in 'setup.py'",
        default='swagger_api'),
    packageVersion=dict(
        type=str,
        help="Python package version",
        default=__version__),
    packageUrl=dict(
        type=str,
        help="Python package URL",
        default=''),
    infoEmail=dict(
        type=str,
        help="Email contact for API support",
        default=''),
    sortParamsByRequiredFlag=dict(
        type=bool,
        help="Sort method arguments to place required parameters before optional parameters",
        default=True),
    hideGenerationTimestamp=dict(
        type=bool,
        help="Hides the generation timestamp when files are generated",
        default=True),
    library=dict(
        type=str,
        help="HTTP library template (sub-template) to use",
        default='urllib3'),
    asyncLibrary=dict(
        type=str,
        help="Asynchronous library to use (one of: {asyncio, tornado}; None => neither)",
        default=None),
    multiprocessingLibrary=dict(
        type=str,
        help=f"Multiprocessing library to use (one of: {set(MultiprocessingLibraries)})",
        default=([k for k, v in MultiprocessingLibraries.items() if v] + [''])[0]),
)

ParsedArgs = namedtuple('ParsedArgs', 'params unknown settings')


def parse_args():
    """ Parses command-line arguments. """
    class MultiRawFormatter(argparse.RawTextHelpFormatter,
                            argparse.RawDescriptionHelpFormatter):
        """ (allow specification of multiple argparse formatters) """

    col = max(len(n) for n in GENERATOR_SETTINGS)
    properties_table = '\n'.join((fill(f"{pk:{col}s} {pv['help']}", width=78, subsequent_indent=' ' * (col + 1)) +
                                  f"\n{'':{col + 1}s}(default: {pv['default']})"
                                  for pk, pv in GENERATOR_SETTINGS.items()))

    if '--version' in sys.argv or len(sys.argv) == 2 and sys.argv[1] == '-v':
        PRINT(__version__)
        sys.exit(0)

    desc, *epilog = __doc__.split('\n\n', maxsplit=1)
    epilog = epilog[0] if epilog else ''
    parser = argparse.ArgumentParser(description='\n'.join(wrap(desc, width=80)).strip(),
                                     fromfile_prefix_chars='@',
                                     epilog=f"\nGenerator Properties:\n{indent(properties_table, '  ')}\n\n"
                                            f"Version {__version__}\n{epilog}",
                                     formatter_class=MultiRawFormatter)
    # NOTE: arg definitions compatible with 'swagger-codegen' naming and syntax.
    parser.add_argument('--version',
                        help="""Show generator version""",
                        action='store_true')
    parser.add_argument('-v', '--verbose',
                        action='store_true',
                        help="""Verbose mode""")
    parser.add_argument('-o', '--output',
                        default='ext',
                        help="""Where to write the generated files; default: '%(default)s'""")
    parser.add_argument('-i', '--input-spec',
                        default='swagger.json',
                        help=dedent("""\
                            Location of the Swagger spec, as URL or file;
                            default: '%(default)s'"""))
    parser.add_argument('-t', '--template-dir',
                        default=TEMPLATE_DEFAULT,
                        help=dedent("""\
                            Folder or JAR file containing the template files;
                            default: '%(default)s'"""))
    parser.add_argument('-s', '--skip-overwrite',
                        action='store_true',
                        help=dedent("""\
                            Specifies if the existing files should be overwritten during
                            the generation"""))
    parser.add_argument('-D',
                        dest='settings', metavar='PROPERTY_SETTING', nargs='+', action='append', default=[],
                        help=dedent("""\
                            Sets specified generator properties, each %(metavar)s
                            in the format: name=value,...; see below for settings"""))
    parser.add_argument('--api-package',
                        default=GENERATOR_SETTINGS.get('projectName').get('default'),
                        help="""Package for generated API classes""")
    parser.add_argument('--model-package',
                        default='models',
                        help="""Package for generated models""")
    parser.add_argument('--model-name-prefix',
                        default='',
                        help=dedent("""\
                            Prefix that will be prepended to all model names;
                            default: no prefix"""))
    parser.add_argument('--model-name-suffix',
                        default='',
                        help=dedent("""\
                            Prefix that will be prepended to all model names;
                            default: no suffix"""))
    parser.add_argument('--import-mappings',
                        metavar='MAPPING', nargs='+', action='append', default=[],
                        help=dedent("""\
                            Specifies mapping between a given class and the import
                            that should be used for that class, each %(metavar)s
                            in the format: type=import,..."""))
    parser.add_argument('--http-user-agent',
                        default=f"Swagger-Python-Codegen-{__version__}" "/{packageVersion}",
                        help=dedent("""\
                            HTTP user agent;
                            default: '%(default)s'"""))
    parser.add_argument('--fix',
                        metavar='PROBLEM', nargs='+', action='append', default=[],
                        help=dedent("""\
                            Specifies which optional fixes to apply before or during
                            generation; PROBLEM may be any or all of:
                              module_comment => replaces ill-formed module initial
                                                comments with well-formed ones
                              http_response => makes HTTP response code specifications
                                               consistent within input OpenAPI spec
                              thread_pool => allows 'multiprocessing.ThreadPool'
                                             instance in SDK API client object to be
                                             modifiable (for client object copying)"""))
    parser.add_argument('--generate',
                        metavar='FEATURE', nargs='+', action='append', default=[],
                        help=dedent("""\
                            Specifies which optional SDK feature(s) to generate
                            in addition to the SDK API and models; FEATURE may be
                            any or all of:
                              docs => generate full SDK documentation
                              test => generate full SDK unit-test suite
                              git => git scripts and configuration
                              travis = Travis CI configuration"""))
    required_command = 'generate'
    parser.add_argument('command', metavar='COMMAND', nargs='?', default=required_command,
                        help=dedent("""\
                            Generator command; if specified, must be '%(default)s'
                            (for compatibility with `swagger-codegen-cli`)"""))

    params, unknown_args = parser.parse_known_args()

    if params.command != required_command:
        raise argparse.ArgumentTypeError(f"COMMAND must be '{required_command}' if specified")

    suppl_parser = argparse.ArgumentParser()
    suppl_parser.add_argument('-l', '--lang', default=None)
    ignored, unknown_args = suppl_parser.parse_known_args(unknown_args)
    if ignored.lang and ignored.lang.lower() != 'python':
        raise argparse.ArgumentTypeError(f"Language '{ignored.lang}' is not supported: only Python code generation")

    def _parse_multi_params(_param_name, _multi_params):
        """ Parses a group of key=val parameter specifications. """
        _param_set = {}
        for _def in _multi_params:
            if isinstance(_def, list):
                _param_set.update(_parse_multi_params(_param_name, _def))
            else:
                try:
                    _n, *_v = _def.split('=')
                    _param_set[_n] = _v[0] if _v else None
                except (Exception, BaseException) as exc:
                    _opt = f"{'-' * min(len(_param_name), 2)}{_param_name}"
                    raise argparse.ArgumentTypeError(f"Bad specification for {_opt}: {_def}") from exc
        return _param_set

    settings = {k: v.get('default') for k, v in GENERATOR_SETTINGS.items()}
    overrides = _parse_multi_params('D', params.settings)
    unknown = [k for k in overrides if k not in settings]
    if unknown:
        raise argparse.ArgumentTypeError(f"Bad specification for -D: unknown settings {unknown}")
    settings.update(overrides)

    params.import_mappings = _parse_multi_params('import-mappings', params.import_mappings)
    params.generate = _parse_multi_params('generate', params.generate)
    params.fix = _parse_multi_params('fix', params.fix)

    # noinspection PyArgumentList
    return ParsedArgs(params, unknown_args, settings)


# ======================================================================================================================
def main():
    """ Application main: generates SDK code from Swagger templates and a Swagger API specification. """
    global PRINT_VERBOSE  # pylint:disable=global-statement

    params, unsupported, settings = parse_args()
    if not params.verbose:
        PRINT_VERBOSE = lambda *_, **__: None  # noqa:E731
    if unsupported:
        PRINT_VERBOSE(f"WARNING: Unsupported command-line options specified: {' '.join(unsupported)}")

    generator = Generator(settings, params)
    generator.generate()


if __name__ == '__main__':
    main()
