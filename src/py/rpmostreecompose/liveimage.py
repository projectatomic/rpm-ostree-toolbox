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

from .taskbase import ImageTaskBase
from .utils import fail_msg, run_sync, log
from .imagefactory import AbstractImageFactoryTask
from .imagefactory import ImgFacBuilder
from .installer import InstallerTask
import json


class CreateLiveTask(AbstractImageFactoryTask):
    def __init__(self, args, cmd, profile=None):
        AbstractImageFactoryTask.__init__(self, args, cmd, profile=profile)
        self._args = args
        self._cmd = cmd
        self._profile = profile

    def impl_create(self):
        log("Starting build")

        self._ensure_httpd()

        if self._args.diskimage:
            self._inputdiskpath = self._args.diskimage
            log("Using existing disk image: {0}".format(self._args.diskimage))
        else:
            self.checkoz("raw")
            imgfacbuild = ImgFacBuilder()
            ksfile = self._args.kickstart
            ksdata = self.formatKS(ksfile)
            parameters = {"install_script": ksdata,
                        "generate_icicle": False,
                        "oz_overrides": json.dumps(self.ozoverrides)
                        }
            image = imgfacbuild.build(template=open(self.tdl).read(), parameters=parameters)
            self._inputdiskpath = image.data
            log("Created input disk: {0}".format(image.data))

        self.lmcContainer(self._inputdiskpath)

        self._destroy_httpd()

    def lmcContainer(self, diskimage):
        inst = InstallerTask(self._args, self._cmd, profile=self._profile)
        docker_os = self.docker_os_name
        docker_image_name = '{0}/rpmostree-toolbox-lmc'.format(docker_os)

        # If a yum_baseurl is defined, add it to the yum repos
        # in the container

        yb_url = self.yum_baseurl if self._args.yum_baseurl is None else self._args.yum_baseurl
        if yb_url is "":
            yb_url = None

        yb_docker = ""
        if yb_url is not None:
            yb_repo = "[yum_baseurl-repo]\nname=yum_baseurl\nbaseurl={0}\nenabled=1\ngpgcheck=0\n".format(yb_url)
            inst.dumpTempMeta(os.path.join(self.workdir, "yb_baseurl.repo"), yb_repo)

        packages = ['lorax', 'rpm-ostree', 'ostree']
        docker_image_basename = docker_image_name + '-base'
        docker_builder_argv = ['rpm-ostree-toolbox', 'docker-image',
                               '--minimize=docs',
                               '--minimize=langs',
                               '--reposdir', self.workdir,
                               '--enablerepo=yum_baseurl-repo',
                               '--name', docker_image_basename]

        docker_builder_argv.extend(packages)
                               
        run_sync(docker_builder_argv)

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

            docker_subs = {'DOCKER_OS': docker_image_basename,
                           }

            docker_file = """
FROM @DOCKER_OS@
RUN mkdir /out
ADD lmc_shell.sh /root/
RUN chmod u+x /root/lmc_shell.sh
CMD ["/bin/sh", "/root/lmc_shell.sh"]
            """

            for subname, subval in docker_subs.iteritems():
                docker_file = docker_file.replace('@%s@' % (subname, ), subval)

            tmp_docker_file = inst.dumpTempMeta(os.path.join(self.workdir, "Dockerfile"), docker_file)

            # Docker build
            child_env = dict(os.environ)
            if 'http_proxy' in child_env:
                del child_env['http_proxy']
            db_cmd = ['docker', 'build', '-t', docker_image_name, os.path.dirname(tmp_docker_file)]
            run_sync(db_cmd, env=child_env)

        # FIXME; why are we copying the input disk?
        run_sync(['cp', '-v', '--sparse=auto', diskimage, self.image_workdir + "/lmc_input_disk"])

        try:
            dr_cmd = ['docker', 'run', '--rm', '--workdir', '/out', '-it', '--net=host',
                      '--privileged=true', '-v', '{0}:{1}'.format(self.image_workdir, '/out'),
                      docker_image_name]
            child_env = dict(os.environ)
            if 'http_proxy' in child_env:
                del child_env['http_proxy']
            run_sync(dr_cmd, env=child_env)
        finally:
            # Remove temporary image
            os.unlink(self.image_workdir + "/lmc_input_disk")

        os.rename(self.image_workdir + '/images', self.image_content_outputdir)
        os.mkdir(self.image_log_outputdir)
        for fname in os.listdir(self.image_workdir):
            if not fname.endswith('.log'):
                continue
            shutil.move(self.image_workdir + '/' + fname, self.image_log_outputdir)

        # Make readable for users
        os.chmod(self.image_content_outputdir, 0755)


# End liveimage

def main(cmd):
    parser = argparse.ArgumentParser(description='Create live images', parents=ImageTaskBase.all_baseargs())
    parser.add_argument('-p', '--profile', type=str, default='DEFAULT', help='Profile to compose (references a stanza in the config file)')
    parser.add_argument('-k', '--kickstart', type=str, required=False, default=None, help='Path to kickstart')
    parser.add_argument('--tdl', type=str, required=False, help='TDL file')
    parser.add_argument('--name', type=str, required=False, help='Image name')
    parser.add_argument('--diskimage', type=str, required=False, help='Path to and including existing RAW disk image')
    parser.add_argument('--skip-subtask', action='append', help='Skip a subtask (currently: docker-create)', default=[])
    parser.add_argument('-b', '--yum_baseurl', type=str, required=False, help='Full URL for the yum repository')

    args = parser.parse_args()
    composer = CreateLiveTask(args, cmd, profile=args.profile)
    try:
        composer.create()
    finally:
        composer.cleanup()
