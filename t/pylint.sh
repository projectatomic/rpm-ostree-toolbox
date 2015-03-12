#!/bin/bash

set -e
set -x


if test -n "${PYLINT_FULL}"; then
    PYLINT_OPTIONS=
else
    PYLINT_OPTIONS=-E
fi

pylint -d line-too-long ${PYLINT_OPTIONS} $srcdir/src/pyrpmostree
pylint -d line-too-long ${PYLINT_OPTIONS} $srcdir/src/py/rpmostreecompose
