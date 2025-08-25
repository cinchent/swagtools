#! /usr/bin/env bash
THISDIR="$(cd "$(dirname "${BASH_SOURCE:-$0}")" && pwd -P)"
package_version="0.16.0"
swagger-python-codegen -i "${THISDIR}/swagger.json" -o ext \
                       -D packageName=sdk projectName=bats_api packageVersion="${package_version}" \
                       --api-package bats --generate docs tests git travis --fix http
