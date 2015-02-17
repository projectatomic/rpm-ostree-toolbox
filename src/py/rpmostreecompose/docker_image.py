#!/usr/bin/env python
# Copyright (C) 2015 Colin Walters <walters@verbum.org>
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2 of the License, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the
# Free Software Foundation, Inc., 59 Temple Place - Suite 330,
# Boston, MA 02111-1307, USA.

import json
import os
import shutil
import errno
import tempfile
import argparse
import subprocess
import oz.TDL
import oz.GuestFactory
import tarfile
import shutil

from .utils import fail_msg, run_sync, TrivialHTTP, log

from gi.repository import GLib

def clean_dir_contents(path):
    if not os.path.isdir(path):
        return
    for name in os.listdir(path):
        subpath = path + '/' + name
        if os.path.isfile(subpath):
            os.unlink(subpath)
        else:
            shutil.rmtree(subpath)

def ensure_unlinked(path):
    try:
        os.unlink(path)
    except OSError, e:
        if e.errno != errno.ENOENT:
            raise

def main(cmd):
    parser = argparse.ArgumentParser(description='Create a docker image')
    parser.add_argument('--reposdir', required=True, default=None, type=str, help='Path to directory with yum .repo files')
    parser.add_argument('--enablerepo', required=True, default=[], action='append', help='Enable a repository')
    parser.add_argument('--minimize', action='append', default=[], help='Control minimization; known types: docs, langs"')
    parser.add_argument('--releasever', action='store', default=None, help='Set "$releasever" URL variable')
    parser.add_argument('--tmpdir', action='store', help='Path to temporary directory')
    parser.add_argument('--name', required=True, action='store', help='Name for docker image')
    parser.add_argument('packages', nargs='+', help='Package name')
    args = parser.parse_args()

    instroot = tempfile.mkdtemp(prefix='toolbox-docker', dir=args.tmpdir)

    try:
        yum_argv = ['yum', '-y', '--disablerepo=*',
                    '--installroot=' + instroot,
                    '--setopt=reposdir=' + args.reposdir]
        for val in args.minimize:
            if val == 'docs':
                yum_argv.append('--setopt=tsflags=nodocs')
            elif val == 'langs':
                yum_argv.append('--setopt=override_install_langs=en')
            else:
                fail_msg("Unknown minimize flag: " + val)
        for val in args.enablerepo:
            yum_argv.append('--enablerepo=' + val)

        if args.releasever:
            yum_argv.append('--setopt=releasever=' + args.releasever)

        yum_argv.append('install')
        yum_argv.extend(args.packages)

        run_sync(yum_argv)

        ensure_unlinked(instroot + '/etc/machine-id')
        if 'langs' in args.minimize:
            ensure_unlinked(instroot + '/usr/lib/locale/locale-archive')

        varcache = instroot + '/var/cache'
        for name in ['/tmp', '/var/cache', '/run']:
            clean_dir_contents(instroot + name)

        tarproc = subprocess.Popen(['tar', '-C', instroot, '-c', '.'],
                                   stdout=subprocess.PIPE)
        # Blah, docker tries to use the http proxy for localhost...
        child_env = dict(os.environ)
        if 'http_proxy' in child_env:
            del child_env['http_proxy']
        run_sync(['docker', 'import', '-', args.name], stdin=tarproc.stdout,
                 env=child_env)
        tarproc.wait()
        if tarproc.returncode != 0:
            fail_msg("tar exited with code " + tarproc.returncode)

    finally:
        shutil.rmtree(instroot)

