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

# For ImageFactory builds
from imgfac.BuildDispatcher import BuildDispatcher
from imgfac.PluginManager import PluginManager
from imgfac.ApplicationConfiguration import ApplicationConfiguration
import logging

from .utils import run_sync, fail_msg

class ImgBuilder(object):
    '''
    Abstract class from which specific builder inherit.
    This is mostly because we want to allow for direct calls to imagefactory,
    but also calls to koji.  In one case, we need to generate a TDL; in the
    other, we provide the parameters and let the system construct it.
    '''

    def __init__(self, *args, **kwargs):
        pass

    def build(self):
        '''
        Trigger a build.  Return something useful like a build id, status, etc.
        '''
        raise NotImplementedError

    def download(self, dest):
        '''
        Copy/download artifacts to a destination
        '''
        raise NotImplementedError

class ImgFacBuilder(ImgBuilder):
    def __init__(self, *args, **kwargs):
        config = json.loads(open('/etc/imagefactory/imagefactory.conf').read())
        config['plugins'] = '/etc/imagefactory/plugins.d'
        config['timeout'] = 3600
        ApplicationConfiguration(configuration=config)
        plugin_mgr = PluginManager('/etc/imagefactory/plugins.d')
        plugin_mgr.load()

        logfile = os.path.join(kwargs['workdir'], 'imgfac.log')

        self.fhandler = logging.FileHandler(logfile)
        self.tlog = logging.getLogger()
        self.tlog.setLevel(logging.DEBUG)
        self.tlog.addHandler(self.fhandler)

        pass

    def build(self, template=None, parameters=None):
        bd = BuildDispatcher()
        builder = bd.builder_for_base_image(template=template,
                                            parameters=parameters)
        print json.dumps(builder.app_config)
        image = builder.base_image
        thread = builder.base_thread
        for key in image.metadata():
            print "%s %s" % (key, getattr(image, key, None))

        thread.join()

        if image.status != "COMPLETE":
            fail_msg("Failed image status: " + image.status)
        return image.data

    def download(self):
        pass

class KojiBuilder(ImgBuilder):
    def __init__(self, **kwargs):
        # sort of
        # server = kwargs.pop('server')
        # self.session = koji.ClientSession(server, kwargs)
        pass

    def build(self):
        # TODO: populate buildinfo
        # self.session.createImageBuild(buildinfo)
        pass

    def download(self):
        pass


class Composer(object):
    ATTRS = [ 'outputdir', 'workdir', 'pkgdatadir', 'ostree_repo',
              'rpmostree_cache_dir', 'os_name', 'os_pretty_name',
              'tree_name', 'tree_file', 'arch', 'release', 'ref',
              'yum_baseurl', 'lorax_additional_repos', 'local_overrides', 'http_proxy'
            ]

    def __init__(self, configfile, name=None, kickstart=None, release=None,
                 tdl=None):
        self._repo = None
        self._name = name
        self._tdl = tdl
        self._kickstart = kickstart
        defaults = { 'workdir': None,
                     'pkgdatadir':  os.environ['OSTBUILD_DATADIR'],
                     'rpmostree_cache_dir': os.path.join(os.getcwd(), release, 'cache'),
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

        imgtargetcloud=os.path.join(imagestmpdir, self._name, '%s.qcow2' % self.os_name)
        self.create_cloud_image(self.workdir, imgtargetcloud, self._kickstart)
        generated.append(imgtargetcloud)

        for f in generated:
            destpath = os.path.join(imagedir, os.path.basename(f))
            print "Created: " + destpath
            shutil.move(f, destpath)

    def create_cloud_image(self, tmpdir, target, ksfile):
        targetdir = os.path.dirname(target)
        if not os.path.exists(targetdir):
            os.makedirs(targetdir)

        port_file_path = tmpdir + '/repo-port'
        subprocess.check_call(['ostree',
                               'trivial-httpd', '--autoexit', '--daemonize',
                               '--port-file', port_file_path],
                              cwd=self.ostree_repo + '/..')

        httpd_port = open(port_file_path).read().strip()
        print "trivial httpd port=%s" % (httpd_port, )

        # TODO: Pull kickstart from separate git repo
        kickstart = open(ksfile).read()
        kickstart = kickstart.replace('@OSTREE_PORT@', httpd_port)

        parameters =  { "install_script": kickstart, 
                        "generate_icicle": False,
                      }

        image_path = self.builder.build(template=open(self._tdl).read(),
                                        parameters=parameters)
        shutil.copyfile(image_path, target)
        print "Created: " + target

    @property
    def builder(self):
        # TODO: option to switch to koji builder
        if True:
            return ImgFacBuilder(workdir=self.workdir)
        else:
            return KojiBuilder()

    def cleanup(self):
        if self.workdir_is_tmp:
            shutil.rmtree(self.workdir)

## End Composer

def main():
    parser = argparse.ArgumentParser(description='Use ImageFactory to create a disk image')
    parser.add_argument('-c', '--config', type=str, required=True, help='Path to config file')
    parser.add_argument('--name', type=str, required=True, help='Image name') 
    parser.add_argument('--tdl', type=str, required=True, help='TDL file') 
    parser.add_argument('-k', '--kickstart', type=str, required=True, help='Path to kickstart') 
    parser.add_argument('-r', '--release', type=str, default='rawhide', help='Release to compose (references a config file section)')
    parser.add_argument('-v', '--verbose', action='store_true', help='verbose output')
    args = parser.parse_args()

    composer = Composer(args.config, name=args.name,
                        kickstart=args.kickstart,
                        tdl=args.tdl,
                        release=args.release)
    composer.show_config()

    composer.create_disks()

    composer.cleanup()
