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
from .utils import fail_msg

class TaskBase(object):
    ATTRS = [ 'outputdir', 'workdir', 'rpmostree_cache_dir', 'pkgdatadir', 'ostree_repo',
              'os_name', 'os_pretty_name',
              'tree_name', 'tree_file', 'arch', 'release', 'ref',
              'yum_baseurl', 'lorax_additional_repos', 'local_overrides', 'http_proxy',
              'selinux', 'output_repodata_dir',
            ]

    def __init__(self, configfile, release=None):
        self._repo = None

        assert release is not None
        defaults = { 'workdir': None,
                     'pkgdatadir':  os.environ['OSTBUILD_DATADIR'],
                     'yum_baseurl': None,
                     'output_repodata_dir': None,
                     'local_overrides': None,
                     'selinux': True
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

        if self.tree_file is None:
            fail_msg("No tree file was provided")

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

        self.buildjson()

        return
    
    def flattenjsoninclude(self, params):
        """ This function merges a dict that represents a tree file
        with a json includefile. It's not rescursive now but could be
        made to be.
        """
        includefile = (os.path.dirname(self.tree_file)) + "/" + params['include']
        params.pop('include', None)
        if not os.path.isfile(includefile):
            fail_msg(("Your tree file includes another file %s that could not be found") % includefile)
        else:
            jsoninclude = open(includefile)
            incparams = json.load(jsoninclude)
            for key in incparams:
                # If its a str,bool,or list and doesn't exist, add it
                if (key not in params) and (key != "comment"):
                    params[key] = incparams[key]
                # If its a list and already exists, merge them 
                if key in params and type(incparams[key]) == list:
                    merged = list(set(params[key] + incparams[key]))
                    params[key] = merged
        return params

    def buildjson(self):
        """ This function merges content from the config.ini and
        the json treefile and then outputs a merged, temporary
        json file in tempdir 
        """

        json_in = open(self.tree_file)
        params = json.load(json_in)
        if 'ref' not in 'params':
            params['ref']  = self.ref
        if 'selinux' not in 'params':
            params['selinux'] = self.selinux
        if 'osname' not in 'params':
            params['osname'] = self.os_name
        if 'include' in params:
            params = self.flattenjsoninclude(params)

        # Need to flatten repos
        if 'repos' in params:
            self._copyrepos(params['repos'])
        self.jsonfilename = os.path.join(self.workdir, os.path.basename(self.tree_file))
        self.jsonfile = open(self.jsonfilename, 'w')
        json.dump(params, self.jsonfile, indent=4)
        self.jsonfile.close()

    def _copyrepos(self, repos):
        """
        This function takes a list of repository names, iterates
        through them and copies them to tempdir
        """

        treefile_base = os.path.dirname(self.tree_file)
        for repo in repos:
            repo_filename = repo + '.repo'
            repo_path = os.path.join(treefile_base, repo_filename) 
            if not os.path.exists(repo_path):
                fail_msg("Unable to find %s as declared in the json input file(s)" % repo_path)
            try:
                shutil.copyfile(repo_path, os.path.join(self.workdir, repo_filename))
            except:
                fail_msg("Unable to copy {0} to tempdir".format(repo_filename))

    @property
    def repo(self):
        if not os.path.exists(self.ostree_repo):
            #  Remove the cache, if the repo. is gone ... or rpm-ostree is very
            # confused.
            if os.path.exists(self.rpmostree_cache_dir):
                shutil.rmtree(self.rpmostree_cache_dir)
            os.makedirs(self.ostree_repo)
            subprocess.check_call(['ostree', 'init',
                                   "--repo="+self.ostree_repo, '--mode=archive-z2'])
        if self._repo is None:
            self._repo = OSTree.Repo(path=Gio.File.new_for_path(self.ostree_repo))
            self._repo.open(None)
        return self._repo

    def show_config(self):
        print "\n".join([ "%s=%s" % (x, str(getattr(self, x))) for x in self.ATTRS ])

    def cleanup(self):
        if self.workdir_is_tmp:
            shutil.rmtree(self.workdir)
