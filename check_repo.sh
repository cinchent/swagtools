#!/usr/bin/env bash
# Canonical code-checking requirements for this repo.

THISDIR=$(cd "$(dirname "${BASH_SOURCE:-$0}")" && pwd -P)
PROJECT_DIR=${PROJECT_DIR:-${THISDIR}}
PACKAGE_DIR=${PACKAGE_DIR:-${THISDIR}/swagtools}
export PYTHONPATH=${PROJECT_DIR}

do_flake=$(echo "$@" | grep -q '\-\-skip.flake' && echo "false" || echo "true")
do_lint=$(echo "$@" | grep -q '\-\-skip.lint' && echo "false" || echo "true")
do_tests=$(echo "$@" | grep -q '\-\-skip.tests' && echo "false" || echo "true")

if ${do_flake}; then
    echo "==================== Flaking..."
    # shellcheck disable=SC2086
    flake8 --config=${PROJECT_DIR}/tox.ini --extend-exclude=swagtools_skeleton_client/skeleton_client/ext/ ${PROJECT_DIR} || \
      exit $?
fi

if ${do_lint}; then
    echo "==================== Linting..."
    # shellcheck disable=SC2046,SC2086
    pylint --rcfile=${PROJECT_DIR}/.pylintrc $(find ${PROJECT_DIR} -name '*.py' | grep -Ev '(/ext/.*)') || \
      exit $?
fi

if ${do_tests}; then
    echo "==================== Testing..."
    # py.test ${PYTEST_OPTIONS} ${PYTEST_MODULES}
fi
