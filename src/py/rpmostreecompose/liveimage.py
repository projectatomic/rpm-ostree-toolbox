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

import argparse
import os
import shutil

from .taskbase import TaskBase
from .utils import fail_msg, run_sync
from .imagefactory import AbstractImageFactoryTask
from .imagefactory import ImgFacBuilder
from .installer import InstallerTask
import json


class CreateLiveTask(AbstractImageFactoryTask):
    def __init__(self, args, cmd, profile):
        AbstractImageFactoryTask.__init__(self, args, cmd, profile)
        self._args = args
        self._cmd = cmd
        self._profile = profile
        self._tdl = getattr(self, 'tdl')

    def createLiveDisk(self):
        self.checkoz("raw")
        imgfacbuild = ImgFacBuilder()
        ksfile = self._args.kickstart
        ksdata = self.formatKS(ksfile)
        parameters = {"install_script": ksdata,
                       "generate_icicle": False,
                       "oz_overrides": json.dumps(self.ozoverrides)
                      }
        print "Starting build"

        if self._args.diskimage:
            self._inputdiskpath = self._args.diskimage
            print "Using existing disk image: {0}".format(self._args.diskimage)
        else:
            image = imgfacbuild.build(template=open(self._tdl).read(), parameters=parameters)
            self._inputdiskpath = image.data
            print "Created input disk: {0}".format(image.data)

        self.lmcContainer(self._inputdiskpath)

    def lmcContainer(self, diskimage):
        inst = InstallerTask(self._args, self._cmd, self._profile)
        docker_os = getattr(self, 'docker_os_name')
        docker_image_name = '{0}/rpmostree-toolbox-lmc'.format(getattr(self, 'docker_os_name'))
        if not ('docker-create' in self.args.skip_subtask):
            # There is currently a bug for loop devices in containers,
            # so we make at least one device to be sure.
            # https://groups.google.com/forum/#!msg/docker-user/JmHko2nstWQ/5iuzVf67vfEJ
            lmc_shell = """#!/bin/sh\n
for x in $(seq 0 6); do
  path=/dev/loop${x}
  if ! test -b ${path}; then mknod -m660 ${path} b 7 ${x}; fi
done

/sbin/livemedia-creator --make-ostree-live --disk-image=/out/lmc_input_disk --resultdir=/out/images --keep-image --live-rootfs-keep-size
"""
            # Instead of the --disk-image being the real name, using
            # lmc_input_disk so we don't have to pass docker env vars

            # If the above loop issue is ever fixed, just make the
            # lmc command the CMD in the Dockerfile below

            inst.dumpTempMeta(os.path.join(self.workdir, "lmc_shell.sh"), lmc_shell)

            # If a yum_baseurl is defined, add it to the yum repos
            # in the container

            yb_url = getattr(self, 'yum_baseurl') if self._args.yum_baseurl is None else self._args.yum_baseurl
            if yb_url is "":
                yb_url = None

            yb_docker = ""
            if yb_url is not None:
                yb_repo = "[yum_baseurl-repo]\nname=yum_baseurl\nbaseurl={0}\nenabled=1\ngpgcheck=0\n".format(yb_url)
                yb_docker = 'ADD yb_baseurl.repo /etc/yum/repos.d/'
                inst.dumpTempMeta(os.path.join(self.workdir, "yb_baseurl.repo"), yb_repo)

            docker_subs = {'DOCKER_OS': docker_os,
                           'YB_REPO': yb_docker
                           }

            docker_file = """
FROM @DOCKER_OS@
@YB_REPO@
RUN mkdir /out
RUN yum -y update
RUN yum -y swap fakesystemd systemd
RUN yum -y install lorax
RUN yum -y clean all
ADD lmc_shell.sh /root/
RUN chmod u+x /root/lmc_shell.sh
CMD ["/bin/sh", "/root/lmc_shell.sh"]
            """

            for subname, subval in docker_subs.iteritems():
                docker_file = docker_file.replace('@%s@' % (subname, ), subval)

            tmp_docker_file = inst.dumpTempMeta(os.path.join(self.workdir, "Dockerfile"), docker_file)

            # Docker build
            db_cmd = ['docker', 'build', '-t', docker_image_name, os.path.dirname(tmp_docker_file)]
            run_sync(db_cmd)

        # Docker run
        lmc_outputdir = os.path.abspath(os.path.join(self._args.outputdir, "lmc/"))
        cp_cmd = ['cp', '-v', '--sparse=auto', diskimage, os.path.join(lmc_outputdir, "lmc_input_disk")]

        run_sync(cp_cmd)

        dr_cmd = ['docker', 'run', '--workdir', '/out', '-it', '--net=host',
                  '--privileged=true', '-v', '{0}:{1}'.format(lmc_outputdir, '/out'),
                  docker_image_name]
        run_sync(dr_cmd)

        finaldir = os.path.join(lmc_outputdir, "images")

        # Make readable for users
        os.chmod(finaldir, 0755)

        print "Your images can be found at {0}".format(finaldir)


# End liveimage

def main(cmd):
    parser = argparse.ArgumentParser(description='Create live images', parents=[TaskBase.baseargs()])
    parser.add_argument('--overwrite', action='store_true', help='If true, replace any existing output')
    parser.add_argument('-o', '--outputdir', type=str, required=True, help='Path to image output directory')
    parser.add_argument('-p', '--profile', type=str, default='DEFAULT', help='Profile to compose (references a stanza in the config file)')
    parser.add_argument('-k', '--kickstart', type=str, required=False, default=None, help='Path to kickstart')
    parser.add_argument('--tdl', type=str, required=False, help='TDL file')
    parser.add_argument('--name', type=str, required=False, help='Image name')
    parser.add_argument('--diskimage', type=str, required=False, help='Path to and including existing RAW disk image')
    parser.add_argument('--skip-subtask', action='append', help='Skip a subtask (currently: docker-create)', default=[])
    parser.add_argument('-b', '--yum_baseurl', type=str, required=False, help='Full URL for the yum repository')

    args = parser.parse_args()
    lmc_outputdir = os.path.join(args.outputdir, "lmc")
    if os.path.exists(lmc_outputdir):
        if not args.overwrite:
            fail_msg("The output directory {0} already exists.".format(lmc_outputdir))
        else:
            shutil.rmtree(lmc_outputdir)
            os.mkdir(lmc_outputdir, 0755)
    else:
        os.mkdir(lmc_outputdir, 0755)

    composer = CreateLiveTask(args, cmd, profile=args.profile)
    try:
        composer.createLiveDisk()

    finally:
        composer.cleanup()
