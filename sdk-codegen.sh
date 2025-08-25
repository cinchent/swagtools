#!/usr/bin/env bash
# Generates the Python 3 SDK for a Swagger-compatible Web Service RESTful API.
#
# Copyright © 2019-2025  CINCH Enterprises, Ltd and Rod Pullmann.  All rights reserved.
#
# Maintenance Notes:
#  * OpenAPI open-source version of swagger-codegen is available via:
#      $ ver=<version>  # (e.g., 3.0.42)
#      $ wget https://repo1.maven.org/maven2/io/swagger/codegen/v3/swagger-codegen-cli/$ver/swagger-codegen-cli-$ver.jar
#  * To use open-source generator, install into /opt, then add this script somewhere in the PATH (e.g., /usr/local/bin):
#      #!/usr/bin/env bash
#      version=<version>
#      java -jar /opt/swagger-codegen/swagger-codegen-cli-${version}.jar $@

THISDIR="$(cd "$(dirname "${BASH_SOURCE:-$0}")" && pwd -P)"

python=python3
export PYTHONPATH=${THISDIR}:${PYTHONPATH}

echo "Resolving configuration for SDK code generation..."

function get_defaults() {
cat << EOF | ${python} -
from contextlib import suppress
from configparser import ConfigParser
from cinch_pyutils.pip import get_package_dir
with suppress(Exception):
    config = ConfigParser()
    _ = config.read('.gitmodules')
    section = {k: v for k, v in list(config.values())[-1].items()}
    client_repo = section.get('path')
    if client_repo != 'swagger-python-codegen':
        print("DEFAULT_CLIENT_DIR={}".format(get_package_dir(client_repo)))
        print("DEFAULT_CLIENT_URL={}".format(section.get('url')))
EOF
}
defs="$(get_defaults)"
# shellcheck disable=SC2086
eval ${defs}

API_TITLE="${SWAGGER_API_TITLE:-API SDK}"
API_PACKAGE="${SWAGGER_API_PACKAGE:-swagtools}"
CLIENT_DIR="${SWAGGER_CLIENT_DIR:-${DEFAULT_CLIENT_DIR:-${THISDIR}/swagtools_skeleton_client/skeleton_client}}"
CLIENT_URL="${SWAGGER_CLIENT_URL:-${DEFAULT_CLIENT_URL}}"
SDK_BASE_DIR="${SWAGGER_SDK_BASE_DIR:-ext}"
SDK_PACKAGE="${SWAGGER_SDK_PACKAGE:-sdk}"
SDK_SUBPACKAGE="${SWAGGER_SDK_SUBPACKAGE:-skeleton}"

# Parses command-line arguments -- evaluate result to define envirosyms.
function parse_args() {
cat << EOF | ${python} - "$@"
from argparse import ArgumentParser
parser = ArgumentParser(description="""\
(Re)builds Python SDK from RESTful API definition.
""")
import sys
parser.add_argument('--swagger_spec', '--swagger-spec', "-s", type=str, default='',
                    help="Existing Swagger specification file to use (empty => run API to generate)")
parser.add_argument('--api_title', '--api-title', type=str, nargs='+', default="${API_TITLE}",
                    help="Title for API (default: %(default)s)")
parser.add_argument('--api_base_dir', '--api-base-dir', type=str, default="${THISDIR}",
                    help="Base directory where API resides (default: %(default)s)")
parser.add_argument('--api_package', '--api-package', type=str, default="${API_PACKAGE}",
                    help="Package that contains API for which to generate SDK (default: %(default)s)")
parser.add_argument('--api_project', '--api-project', type=str, default="${API_PROJECT}",
                    help="Project name for API (default: derive from API_PACKAGE)")
parser.add_argument('--client_dir', '--client-dir', type=str, default="${CLIENT_DIR}",
                    help="Base directory for API Client (default: %(default)s)")
parser.add_argument('--client_url', '--client-url', type=str, default="${CLIENT_URL}",
                    help="URL for API client repo (default: %(default)s)")
parser.add_argument('--sdk_base_dir', '--sdk-base-dir', type=str, default="${SDK_BASE_DIR}",
                    help="Base directory where to generate SDK,"
                         " relative to CLIENT_DIR unless absolute path (default: %(default)s)")
parser.add_argument('--sdk_package', '--sdk-package', type=str, default="${SDK_PACKAGE}",
                    help="Name for SDK package (default: %(default)s)")
parser.add_argument('--sdk_subpackage', '--sdk-subpackage', type=str, default="${SDK_SUBPACKAGE}",
                    help="Name for SDK subpackage (default: %(default)s)")
parser.add_argument('--verbose', dest='verbose', action='store_true', default=False,
                    help="Display details of code generation")
parser.add_argument('-D', dest='extra_settings', nargs='+', default=[],
                    help="Extra settings appended to generator command line")
params, passthru = parser.parse_known_args()
for arg, val in vars(params).items():
    print('{}="{}"'.format(arg.upper(), str(val).lower() if isinstance(val, bool) else
                                        ' '.join(val) if isinstance(val, (list, tuple)) else val.replace('None', '')))
print('SERVER_OPTS="{}"'.format(' '.join(passthru)))
EOF
}
# shellcheck disable=SC2068
defs="$(parse_args $@)"
echo "${defs}" | grep -q 'usage:' && echo "${defs}" && exit 0
# shellcheck disable=SC2086
eval ${defs}

VERBOSE="$(${VERBOSE} && echo "--verbose" || echo)"
[[ -n "${EXTRA_SETTINGS}" ]] && EXTRA_SETTINGS="-D ${EXTRA_SETTINGS}"
API_BASE_DIR="${API_BASE_DIR/#~/${HOME}}"
API_PROJECT="${API_PROJECT:-${API_PACKAGE}_api}"
cd "${API_BASE_DIR}" || exit 1
API_VERSION="$(${python} -c "import ${API_PACKAGE}; print(${API_PACKAGE}.__version__)")"
SDK_BASE_DIR="$(${python} -c "from pathlib import Path; d=Path('${SDK_BASE_DIR/#~/${HOME}}'); \
                              print(d if d.is_absolute() else Path('${CLIENT_DIR/#~/${HOME}}', d))")"
# REST_LIBRARY=${REST_LIBRARY:-urllib3}
REST_LIBRARY=${REST_LIBRARY:-requests}

# MULTIPROCESSING="multiprocessing"
MULTIPROCESSING="concurrent_futures"

# ----------
swagger_spec_supplied="${SWAGGER_SPEC}"
SWAGGER_SPEC=${swagger_spec_supplied:-${API_BASE_DIR}/swagger.json}
SWAGGER_CODEGEN="$(which swagger-codegen)"
# SWAGGER_CODEGEN="java -classpath ${HOME}/swagger-codegen/swagger-codegen-jar io/swagger/codegen/v3/cli/SwaggerCodegen"
CODEGEN_VER="$("${SWAGGER_CODEGEN}" version 2>/dev/null)"
CODEGEN_LOC="$(
  java() { echo "$2"; }
  export -f java
  ${SWAGGER_CODEGEN} 2>/dev/null
)"

# shellcheck disable=SC2155
export SWAGGER_PYTHON_CODEGEN="$(which swagger-python-codegen)"
if [[ -n "${SWAGGER_PYTHON_CODEGEN}" ]]; then
    export SWAGGER_CODEGEN_VERSION="${CODEGEN_VER}"
    export SWAGGER_CODEGEN_TEMPLATE_DEFAULT="${CODEGEN_LOC}"
    SWAGGER_CODEGEN="${SWAGGER_PYTHON_CODEGEN}"
fi

# ----------
# Launch API Server in a special mode to generate the Swagger specification file (unless spec is already provided).
if [[ -z "${swagger_spec_supplied}" ]]; then
    rm -f "${SWAGGER_SPEC}"
    SERVICE_CONFIG="service_config.local"
    [[ -n "$(find . -name "${SERVICE_CONFIG}"'*')" ]] && SERVICE_CONFIG="--env ${SERVICE_CONFIG}" || SERVICE_CONFIG=
    # shellcheck disable=SC2086
    ${python} ${API_PACKAGE}/app.py ${SERVICE_CONFIG} ${SERVER_OPTS} --swagger ${SWAGGER_SPEC}
fi
if [[ ! -f "${SWAGGER_SPEC}" ]]; then
    echo "ERROR: No Swagger specification file '${SWAGGER_SPEC}' -- cannot generate SDK" && exit 1
fi

# Generate the SDK from the Swagger specification file.
rm -rf "${SDK_BASE_DIR}"
# shellcheck disable=SC2086
${SWAGGER_CODEGEN} generate --lang python --import-mappings BigDecimal=float \
                            --fix module_comment http_response thread_pool \
                            -D projectName="${API_PROJECT}" packageName="${SDK_PACKAGE}" \
                               packageVersion="${API_VERSION}" packageUrl="${CLIENT_URL}" \
                               library="${REST_LIBRARY}" multiprocessingLibrary="${MULTIPROCESSING}" \
                            --api-package "${SDK_SUBPACKAGE}" -i "${SWAGGER_SPEC}" -o "${SDK_BASE_DIR}" \
                            ${VERBOSE} ${EXTRA_SETTINGS}
cd "${SDK_BASE_DIR}" || exit 1

# shellcheck disable=SC2038
find . -name "__pycache__" | xargs rm -rf

echo "SUCCESS"
