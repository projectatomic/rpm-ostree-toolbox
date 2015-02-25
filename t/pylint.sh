#!/bin/sh

set -e
set -x

exec pylint -E $srcdir/src/py/rpmostreecompose/*.py
