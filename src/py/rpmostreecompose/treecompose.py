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

from .utils import run_sync, fail_msg

def print_header(tasks):
    print "=" * 78
    print tasks
    print "=" * 78

class Composer(object):
    ATTRS = [ 'outputdir', 'workdir', 'pkgdatadir', 'ostree_repo',
              'rpmostree_cache_dir', 'os_name', 'os_pretty_name',
              'tree_name', 'tree_file', 'arch', 'release', 'ref',
              'yum_baseurl', 'lorax_additional_repos', 'local_overrides', 'http_proxy',
              'cmd_ostree', 'cmd_rpm_ostree', 'cmd_lorax', 
            ]

    def __init__(self, configfile, release):
        self._repo = None
        defaults = { 'workdir': None,
                     'pkgdatadir':  os.environ['OSTBUILD_DATADIR'],
                     'rpmostree_cache_dir': os.path.join(os.getcwd(), release, 'cache'),
                     'yum_baseurl': None,
                     'local_overrides': None,
                     'cmd_ostree'     : 'ostree',
                     'cmd_rpm_ostree' : 'rpm-ostree',
                     'cmd_lorax'      : 'lorax',
                   }

        if not os.path.exists(configfile):
            fail_msg("No config file: " + configfile)

        settings = iniparse.ConfigParser()
        settings.read(configfile)
        for attr in self.ATTRS:
            try:
                val = settings.get(release, attr)
            except (iniparse.NoOptionError, iniparse.NoSectionError), e:
                try:
                    val = settings.get('DEFAULT', attr)
                except iniparse.NoOptionError, e:
                    val = defaults.get(attr)
            setattr(self, attr, val)

        if not self.yum_baseurl:
            if self.release in [ '21', 'rawhide' ]:
                self.yum_baseurl = 'http://download.fedoraproject.org/pub/fedora/linux/development/%s/%s/os/' % (self.release, self.arch)
            else:
                self.yum_baseurl = 'http://download.fedoraproject.org/pub/fedora/linux/releases/%s/%s/os/' % (self.release, self.arch)

        if self.http_proxy:
            os.environ['http_proxy'] = self.http_proxy

        self.workdir_is_tmp = False
        if self.workdir is None:
            self.workdir = tempfile.mkdtemp('.tmp', 'atomic-treecompose')
            self.workdir_is_tmp = True

        for cmd in (self.cmd_ostree, self.cmd_rpm_ostree, self.cmd_lorax):
            if os.path.isfile(cmd):
                continue
            if distutils.spawn.find_executable(cmd):
                continue
            fail_msg("Command not found: " + cmd)

        return

    @property
    def repo(self):
        if not os.path.exists(self.ostree_repo):
            #  Remove the cache, if the repo. is gone ... or rpm-ostree is very
            # confused.
            shutil.rmtree(self.rpmostree_cache_dir)
            os.makedirs(self.ostree_repo)
            subprocess.check_call([self.cmd_ostree, 'init',
                                   "--repo="+self.ostree_repo])
        if self._repo is None:
            self._repo = OSTree.Repo(path=Gio.File.new_for_path(self.ostree_repo))
            self._repo.open(None)
        return self._repo

    def show_config(self):
        print "\n".join([ "%s=%s" % (x, str(getattr(self, x))) for x in self.ATTRS ])

    def compose_tree(self):
        # XXX: rpm-ostree should be handling this, I think
        if not os.path.exists(self.rpmostree_cache_dir):
            os.makedirs(self.rpmostree_cache_dir)
        _,origrev = self.repo.resolve_rev(self.ref, True)
        print_header("Performing Task: tree (ostree compose)")
        if not self.tree_file:
            self.tree_file = '%s/%s-%s.json' % (self.pkgdatadir, self.os_name,
                                                self.tree_name)
        subprocess.check_call([self.cmd_rpm_ostree, 'compose', 'tree',
                               '--repo=' + self.ostree_repo,
                               '--cachedir=' + self.rpmostree_cache_dir,
                               self.tree_file])
        _,newrev = self.repo.resolve_rev(self.ref, True)
        return (origrev, newrev)

    def cleanup(self):
        if self.workdir_is_tmp:
            shutil.rmtree(self.workdir)

## End Composer

def main():
    parser = argparse.ArgumentParser(description='Compose OSTree trees and build images.')
    parser.add_argument('-c', '--config', type=str, required=True, help='Path to config file')
    parser.add_argument('-r', '--release', type=str, default='rawhide', help='Release to compose (references a config file section)')
    parser.add_argument('-v', '--verbose', action='store_true', help='verbose output')
    args = parser.parse_args()

    composer = Composer(args.config, args.release)
    composer.show_config()

    origrev, newrev = composer.compose_tree()

    if origrev != newrev:
        print "%s => %s" % (composer.ref, newrev)
    else:
        print "%s is unchanged at %s" % (composer.ref, origrev)

    composer.cleanup()
