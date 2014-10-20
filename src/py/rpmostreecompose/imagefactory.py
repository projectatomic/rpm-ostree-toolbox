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

from .taskbase import TaskBase

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

        print "ImgFacBuilder logging to: " + logfile
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


class ImageFactoryTask(TaskBase):
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
        if not os.path.exists(imagestmpdir):
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
                              cwd=self.ostree_repo)

        httpd_port = open(port_file_path).read().strip()
        print "trivial httpd port=%s" % (httpd_port, )

        ks_basename = os.path.basename(ksfile)
        flattened_ks = os.path.join(tmpdir, ks_basename)

        # FIXME - eventually stop hardcoding this via some mapping
        if ks_basename.find('fedora') >= 0:
            kickstart_version = 'F21'
        else:
            kickstart_version = 'RHEL7'
        run_sync(['ksflatten', '--version', kickstart_version,
                  '-c', ksfile, '-o', flattened_ks])

        # TODO: Pull kickstart from separate git repo
        ksdata = open(flattened_ks).read()
        substitutions = { 'OSTREE_PORT': httpd_port,
                          'OSTREE_REF':  self.ref,
                          'OSTREE_OSNAME':  self.os_name }
        for subname, subval in substitutions.iteritems():
            ksdata = ksdata.replace('@%s@' % (subname, ), subval)

        parameters =  { "install_script": ksdata, 
                        "generate_icicle": False,
                      }

        print "Starting build"
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

    composer = ImageFactoryTask(args.config, name=args.name,
                                kickstart=args.kickstart,
                                tdl=args.tdl,
                                release=args.release)
    composer.show_config()

    composer.create_disks()

    composer.cleanup()
