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

    def create_disks(self):
        [res,rev] = self.repo.resolve_rev(self.ref, False)
        [res,commit] = self.repo.load_variant(OSTree.ObjectType.COMMIT, rev)

        commitdate = GLib.DateTime.new_from_unix_utc(OSTree.commit_get_timestamp(commit)).format("%c")
        print commitdate
        # XXX - Define this somewhere?
        imageoutputdir=os.path.join(self.outputdir, 'images')

        imagedir = os.path.join(imageoutputdir, rev[:8])
        if not os.path.exists(imagedir):
            os.makedirs(imagedir)

        imagestmpdir = os.path.join(self.workdir, 'images')
        os.mkdir(imagestmpdir)

        generated = []

        imgtargetinstaller=os.path.join(imagestmpdir, 'install', '%s-installer.iso' % self.os_name)
        self.create_installer_image(self.workdir, imgtargetinstaller)
        generated.append(imgtargetinstaller)

        for f in generated:
            destpath = os.path.join(imagedir, os.path.basename(f))
            print "Created: " + destpath
            shutil.move(f, destpath)

    def create_installer_image(self, tmpdir, target):
        lorax_opts = []
        if self.local_overrides:
            lorax_opts.extend([ '-s', self.local_overrides ])
        if self.lorax_additional_repos:
            for repourl in self.lorax_additional_repos.split(','):
                lorax_opts.extend(['-s', repourl.strip()])
        http_proxy = os.environ.get('http_proxy')
        if http_proxy:
            lorax_opts.extend([ '--proxy', http_proxy ])

        lorax_workdir = os.path.join(tmpdir, 'lorax')
        os.makedirs(lorax_workdir)
        run_sync([self.cmd_lorax, '--nomacboot',
                  '--add-template=%s/lorax-embed-repo.tmpl' % self.pkgdatadir,
                  '--add-template-var=ostree_osname=%s' % self.os_name,
                  '--add-template-var=ostree_repo=%s' % self.ostree_repo,
                  '--add-template-var=ostree_ref=%s' % self.ref,
                  '-p', self.os_pretty_name, '-v', self.release,
                  '-r', self.release, '-s', self.yum_baseurl,
                  ] + lorax_opts + ['output'],
                 cwd=lorax_workdir)
        os.makedirs(os.path.dirname(target))
        # Right now we only take the boot.iso (which is really
        # installer.iso since we used a template to inject data)
        os.rename(lorax_workdir + '/output/images/boot.iso', target)

    def cleanup(self):
        if self.workdir_is_tmp:
            shutil.rmtree(self.workdir)

## End Composer

def main():
    parser = argparse.ArgumentParser(description='Create an installer image')
    parser.add_argument('-c', '--config', type=str, required=True, help='Path to config file')
    parser.add_argument('-r', '--release', type=str, default='rawhide', help='Release to compose (references a config file section)')
    parser.add_argument('-v', '--verbose', action='store_true', help='verbose output')
    args = parser.parse_args()

    composer = Composer(args.config, args.release)
    composer.show_config()

    origrev = None
    _,newrev = composer.repo.resolve_rev(composer.ref, True)

    composer.create_disks()

    composer.cleanup()
