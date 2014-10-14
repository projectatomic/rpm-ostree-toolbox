#!/usr/bin/env python
# Copyright (C) 2014 Colin Walters <walters@verbum.org>, Andy Grimm <agrimm@redhat.com>
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
import sys
import tempfile
import argparse
import shutil
import subprocess
import distutils.spawn
from gi.repository import Gio, OSTree, GLib
import iniparse

from .taskbase import TaskBase
from .utils import run_sync, fail_msg

class Treecompose(TaskBase):
    def compose_tree(self):
        # XXX: rpm-ostree should be handling this, I think
        _,origrev = self.repo.resolve_rev(self.ref, True)
        if not self.tree_file:
            self.tree_file = '%s/%s-%s.json' % (self.pkgdatadir, self.os_name,
                                                self.tree_name)
        rpmostreecmd = ['rpm-ostree', 'compose', 'tree', '--repo=' + self.ostree_repo]

        rpmostreecachedir = self.rpmostree_cache_dir
        if rpmostreecachedir is not None:
            cachecmd = '--cachedir=' + rpmostreecachedir
            rpmostreecmd.append(cachecmd)
            if not os.path.exists(rpmostreecachedir):
                os.makedirs(rpmostreecachedir)
        rpmostreecmd.append(self.jsonfilename)

        subprocess.check_call(rpmostreecmd)
        _,newrev = self.repo.resolve_rev(self.ref, True)
        return (origrev, newrev)

## End Composer

def main():
    parser = argparse.ArgumentParser(description='Compose OSTree tree')
    parser.add_argument('-c', '--config', type=str, required=True, help='Path to config file')
    parser.add_argument('-r', '--release', type=str, default='rawhide', help='Release to compose (references a config file section)')
    parser.add_argument('-v', '--verbose', action='store_true', help='verbose output')
    args = parser.parse_args()

    composer = Treecompose(args.config, release=args.release)
    composer.show_config()

    origrev, newrev = composer.compose_tree()

    if origrev != newrev:
        print "%s => %s" % (composer.ref, newrev)
    else:
        print "%s is unchanged at %s" % (composer.ref, origrev)

    composer.cleanup()
