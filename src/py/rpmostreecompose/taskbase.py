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

class TaskBase(object):
    ATTRS = [ 'outputdir', 'workdir', 'rpmostree_cache_dir', 'pkgdatadir', 'ostree_repo',
              'os_name', 'os_pretty_name',
              'tree_name', 'tree_file', 'arch', 'release', 'ref',
              'yum_baseurl', 'lorax_additional_repos', 'local_overrides', 'http_proxy'
            ]

    def __init__(self, configfile, name=None, kickstart=None, release=None,
                 tdl=None):
        self._repo = None
        self._name = name
        self._tdl = tdl
        self._kickstart = kickstart
        assert release is not None
        defaults = { 'workdir': None,
                     'pkgdatadir':  os.environ['OSTBUILD_DATADIR'],
                     'yum_baseurl': None,
                     'local_overrides': None
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

        return

    @property
    def repo(self):
        if not os.path.exists(self.ostree_repo):
            #  Remove the cache, if the repo. is gone ... or rpm-ostree is very
            # confused.
            shutil.rmtree(self.rpmostree_cache_dir)
            os.makedirs(self.ostree_repo)
            subprocess.check_call(['ostree', 'init',
                                   "--repo="+self.ostree_repo])
        if self._repo is None:
            self._repo = OSTree.Repo(path=Gio.File.new_for_path(self.ostree_repo))
            self._repo.open(None)
        return self._repo

    def show_config(self):
        print "\n".join([ "%s=%s" % (x, str(getattr(self, x))) for x in self.ATTRS ])

    def cleanup(self):
        if self.workdir_is_tmp:
            shutil.rmtree(self.workdir)
