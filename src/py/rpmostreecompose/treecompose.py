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

def _rev2version(repo, rev):
    _,oldrev = repo.resolve_rev(rev, True)
    if oldrev is None:
        return None

    _,commit = repo.load_variant(OSTree.ObjectType.COMMIT, oldrev)

    metadata = commit.get_child_value(0)
    version = metadata.lookup_value("version", None)
    if version is not None:
        version = version.get_string()
    return version

class Treecompose(TaskBase):
    def compose_tree(self):
        # XXX: rpm-ostree should be handling this, I think
        _,origrev = self.repo.resolve_rev(self.ref, True)
        if not self.tree_file:
            self.tree_file = '%s/%s-%s.json' % (self.pkgdatadir, self.os_name,
                                                self.tree_name)
        rpmostreecmd = ['rpm-ostree', 'compose', 'tree', '--repo=' + self.ostree_repo]

        loaded_version = _rev2version(self.repo, self.ref)

        # Load the old version from the tree...
        if self.tree_version and self.tree_version.startswith('skip-or-'):
            if not loaded_version:
                self.tree_version = None
            else:
                self.tree_version = self.tree_version[len('skip-or-'):]
        elif loaded_version and not self.tree_version:
            print >>sys.stderr, " WARNING: No version specified, but have old version in tree."

        try:
            lv = [int(x) for x in loaded_version.split('.', 3)]
        except:
            print >>sys.stderr, " WARNING: Old version is invalid (not 4 numbers)."
            loaded_version = None

        if self.tree_version:

            # Version looks like <releasever>.<minor>.<refresh>.<cve>
            # So if we are on 1.2.4.8 then:
            # --version=minor   == 1.3.0.0
            # --version=refresh == 1.2.5.0
            # --version=cve     == 1.2.4.9
            if not loaded_version and self.tree_version in ('cve', 'minor',
                                                            'refresh'):
                fail_msg("No previous version to get new version from")
            if loaded_version and self.tree_version == 'cve':
                lv = [int(x) for x in loaded_version.split('.')]
                lv[3] += 1
                self.tree_version = "%u.%u.%u.%u" % tuple(lv)
            if loaded_version and self.tree_version == 'refresh':
                lv = [int(x) for x in loaded_version.split('.')]
                lv[2] += 1
                lv[3] = 0
                self.tree_version = "%u.%u.%u.%u" % tuple(lv)
            if loaded_version and self.tree_version == 'minor':
                lv = [int(x) for x in loaded_version.split('.')]
                lv[1] += 1
                lv[2] = 0
                lv[3] = 0
                self.tree_version = "%u.%u.%u.%u" % tuple(lv)

            tv = self.tree_version.split('.')
            if len(tv) != 4:
                fail_msg("Version not in correct format (4 numbers). Eg. version=1.2.3.4")

            if loaded_version:
                lv = [int(x) for x in loaded_version.split('.')]

                if int(tv[0]) < lv[0]:
                    fail_msg("<releasever> of version is getting older.")
                if int(tv[1]) < lv[1]:
                    fail_msg("<minor> of version is getting older.")
                if int(tv[2]) < lv[2]:
                    fail_msg("<refresh> of version is getting older.")
                if int(tv[3]) < lv[3]:
                    fail_msg("<cve> of version is getting older.")
            print "** Building Version:", self.tree_version
            rpmostreecmd.append('--add-metadata-string=version=' + self.tree_version)

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
    parser.add_argument('-c', '--config', type=str, default='config.ini', help='Path to config file')
    parser.add_argument('-r', '--release', type=str, default='rawhide', help='Release to compose (references a config file section)')
    parser.add_argument('-V', '--version', type=str, default='skip-or-refresh', help='Version to mark compose')
    parser.add_argument('-v', '--verbose', action='store_true', help='verbose output')
    args = parser.parse_args()

    composer = Treecompose(args.config, release=args.release)
    composer.tree_version = args.version
    composer.show_config()

    origrev, newrev = composer.compose_tree()

    if origrev != newrev:
        print "%s => %s" % (composer.ref, newrev)
    else:
        print "%s is unchanged at %s" % (composer.ref, origrev)

    composer.cleanup()
