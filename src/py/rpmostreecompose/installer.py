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

class InstallerTask(TaskBase):
    def create(self, outputdir):
        [res,rev] = self.repo.resolve_rev(self.ref, False)
        [res,commit] = self.repo.load_variant(OSTree.ObjectType.COMMIT, rev)

        commitdate = GLib.DateTime.new_from_unix_utc(OSTree.commit_get_timestamp(commit)).format("%c")
        print commitdate

        lorax_opts = []
        if self.local_overrides:
            lorax_opts.extend([ '-s', self.local_overrides ])
        if self.lorax_additional_repos:
            for repourl in self.lorax_additional_repos.split(','):
                lorax_opts.extend(['-s', repourl.strip()])
        http_proxy = os.environ.get('http_proxy')
        if http_proxy:
            lorax_opts.extend([ '--proxy', http_proxy ])

        lorax_workdir = os.path.join(self.workdir, 'lorax')
        os.makedirs(lorax_workdir)
        run_sync(['lorax', '--nomacboot',
                  '--add-template=%s/lorax-embed-repo.tmpl' % self.pkgdatadir,
                  '--add-template-var=ostree_osname=%s' % self.os_name,
                  '--add-template-var=ostree_repo=%s' % self.ostree_repo,
                  '--add-template-var=ostree_ref=%s' % self.ref,
                  '-p', self.os_pretty_name, '-v', self.release,
                  '-r', self.release, '-s', self.yum_baseurl,
                  ] + lorax_opts + ['output'],
                 cwd=lorax_workdir)
        # We injected data into boot.iso, so it's now installer.iso
        lorax_output = lorax_workdir + '/output'
        lorax_images = lorax_output + '/images'
        os.rename(lorax_images + '/boot.iso', lorax_images + '/installer.iso')

        for p in os.listdir(lorax_output):
            print "Generated: " + p
            shutil.move(os.path.join(lorax_output, p),
                        os.path.join(outputdir, p))

## End Composer

def main():
    parser = argparse.ArgumentParser(description='Create an installer image')
    parser.add_argument('-c', '--config', type=str, required=True, help='Path to config file')
    parser.add_argument('-r', '--release', type=str, default='rawhide', help='Release to compose (references a config file section)')
    parser.add_argument('-v', '--verbose', action='store_true', help='verbose output')
    parser.add_argument('-o', '--outputdir', type=str, required=True, help='Path to image output directory')
    args = parser.parse_args()

    composer = InstallerTask(args.config, release=args.release)
    composer.show_config()

    composer.create(args.outputdir)

    composer.cleanup()
