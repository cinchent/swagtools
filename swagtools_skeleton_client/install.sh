#!/usr/bin/env bash
# Python auto-installer for this repo.
# (see pyutils.setup.setup()() for envirosyms)
THISDIR=$(cd "$(dirname "${BASH_SOURCE:-$0}")" && pwd -P)
export EXT_PACKAGES_AUTH=${EXT_PACKAGES_AUTH:-https}
export EXT_PACKAGES_OVERWRITE=${EXT_PACKAGES_OVERWRITE:-false}
export EXT_PACKAGES_REINSTALL=${EXT_PACKAGES_REINSTALL:-true}
${EXT_PACKAGES_REINSTALL} && python3 "${THISDIR}/setup.py" egg_info
PIP_QUIET="$(python3 -m pip --version | grep -q "pip 21" || echo "--root-user-action=ignore")"
EXT_PACKAGES_REINSTALL=false python3 -m pip --no-cache-dir --disable-pip-version-check \
    install ${PIP_QUIET} -e "${THISDIR}"
