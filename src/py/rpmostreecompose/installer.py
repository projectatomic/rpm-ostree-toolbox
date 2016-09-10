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
import shutil
import argparse
import subprocess
import oz.TDL
import oz.GuestFactory
import tarfile
import shutil

from .taskbase import ImageTaskBase
from .utils import fail_msg, run_sync, TrivialHTTP, log
from .imagefactory import AbstractImageFactoryTask
from .imagefactory import ImgFacBuilder
from imgfac.BuildDispatcher import BuildDispatcher
from imgfac.PersistentImageManager import PersistentImageManager
from xml.etree import ElementTree as ET
from .imagefactory import getDefaultIP

from gi.repository import GLib  # pylint: disable=no-name-in-module

class InstallerTask(ImageTaskBase):
    container_id = ""

    def __init__(self, *args, **kwargs):
        ImageTaskBase.__init__(self, *args, **kwargs)
        self.tdl = None

    def dumpTempMeta(self, fullpathname, tmpstr):
        with open(fullpathname, 'w') as f:
            f.write(tmpstr)
        log("Wrote {0}".format(fullpathname))
        return fullpathname

    def _buildDockerImage(self, docker_image_name):
        docker_image_basename = self.buildDockerWorkerBaseImage('lorax', ['lorax', 'rpm-ostree', 'ostree'])

        lorax_repos = []
        # This is hacky since we need to support CentOS 7 lorax which only knows
        # -s/-m and not --repo
        if self.lorax_inherit_repos is not None:
            repoids,repos = self.getrepos(self.jsonfilename)
            baseurls = {}
            for repoid in repoids:
                with open('{}/{}.repo'.format(self.configdir, repoid)) as f:
                    baseurl = None
                    for line in f:
                        if line.startswith('baseurl='):
                            baseurl = line[len('baseurl='):].strip()
                            break
                    if baseurl is None:
                        fail_msg("Didn't find baseurl= in {}".format(repoid))
                    baseurls[repoid] = baseurl
            for repoid,baseurl in baseurls.iteritems():
                lorax_repos.extend(['-s', baseurl])

        if self.lorax_additional_repos:
            if self.yum_baseurl not in self.lorax_additional_repos:
                self.lorax_additional_repos += ", {0}".format(self.yum_baseurl)
            for repourl in self.lorax_additional_repos.split(','):
                lorax_repos.extend(['-s', repourl.strip()])
        else:
            lorax_repos.extend(['-s', self.yum_baseurl])

        os_v = self.release
        lorax_cmd = ['lorax', '--nomacboot', '--add-template=/root/lorax.tmpl',
                     '-p', self.os_pretty_name, '-v', os_v, '-r', os_v]
        if self.lorax_rootfs_size is not None:
            lorax_cmd.extend(['--rootfs-size', self.lorax_rootfs_size])
        isolabel = "{0}-{1}-{2}".format(self.os_pretty_name, os_v, self.arch)
        if len(isolabel) > 32:
            isolabel = isolabel[:32].strip()
            log("Using isolabel truncated to 32 chars: %s" % isolabel)
            lorax_cmd.extend(['--volid', isolabel])
        http_proxy = os.environ.get('http_proxy')
        if http_proxy:
            lorax_cmd.extend(['--proxy', http_proxy])
        if bool(self.is_final):
            lorax_cmd.append('--isfinal')
        lorax_cmd.extend(lorax_repos)
        excludes = self.lorax_exclude_packages
        if excludes is not None:
            for exclude in excludes.split(','):
                exclude = exclude.strip()
                if exclude == '': continue
                lorax_cmd.extend(['-e', exclude])
        includes = self.lorax_include_packages
        if includes is not None:
            for include in includes.split(','):
                if include == '': continue
                lorax_cmd.extend(['-i', include.strip()])
        lorax_cmd.append('/out/lorax')

        # There is currently a bug for loop devices in containers,
        # so we make at least one device to be sure.
        # https://groups.google.com/forum/#!msg/docker-user/JmHko2nstWQ/5iuzVf67vfEJ
        lorax_shell = """#!/bin/sh\n
for x in $(seq 0 6); do
  path=/dev/loop${{x}}
  if ! test -b ${{path}}; then mknod -m660 ${{path}} b 7 ${{x}}; fi
done
sed -e "s,@OSTREE_URL@,${{OSTREE_URL}},"  < /root/lorax.tmpl.in > /root/lorax.tmpl
echo Running: {0}
exec {0}
""".format(" ".join(map(GLib.shell_quote, lorax_cmd)))
        self.dumpTempMeta(os.path.join(self.workdir, "lorax.sh"), lorax_shell)

        docker_subs = {'DOCKER_OS': docker_image_basename}
        docker_file = """
FROM @DOCKER_OS@
ADD lorax.tmpl /root/lorax.tmpl.in
ADD lorax.sh /root/
RUN mkdir /out
RUN if rpm -q subscription-manager 1>/dev/null 2>&1; then yum -y remove subscription-manager; fi
RUN chmod u+x /root/lorax.sh
CMD ["/bin/sh", "/root/lorax.sh"]
        """

        for subname, subval in docker_subs.iteritems():
            docker_file = docker_file.replace('@%s@' % (subname, ), subval)

        tmp_docker_file = self.dumpTempMeta(os.path.join(self.workdir, "Dockerfile"), docker_file)

        # Docker build
        db_cmd = ['docker', 'build', '-t', docker_image_name, os.path.dirname(tmp_docker_file)]
        child_env = dict(os.environ)
        if 'http_proxy' in child_env:
            del child_env['http_proxy']
        run_sync(db_cmd, env=child_env)

    def impl_create(self, post=None):
        lorax_tmpl = open(os.path.join(self.pkgdatadir, 'lorax-http-repo.tmpl')).read()

        # Yeah, this is pretty awful.
        if post is not None:
            post_str = '%r' % ('%post --erroronfail\n' + open(post).read() + '\n%end\n', )
            lorax_tmpl += '\nappend usr/share/anaconda/interactive-defaults.ks %s\n' % (post_str, ) 

        port_file_path = self.workdir + '/repo-port'
        if not self.ostree_repo_is_remote:
            # Start trivial-httpd
            trivhttp = TrivialHTTP()
            trivhttp.start(self.ostree_repo)
            httpd_port = str(trivhttp.http_port)
            httpd_url = '127.0.0.1'
            log("trivial httpd serving %s on port=%s, pid=%s" % (self.ostree_repo, httpd_port, trivhttp.http_pid))
            ostree_url = "http://{0}:{1}".format(httpd_url, httpd_port)
        else:
            httpd_port = self.httpd_port
            httpd_url = self.httpd_host
            ostree_url = self.ostree_repo

        # Test connectivity to the the ostree repository.  Here we look for
        # for the repository's /config file.
        self._require_ostree_repo(ostree_url)

        substitutions = {'OSTREE_REF':  self.ref,
                         'OSTREE_OSNAME':  self.os_name,
                         'OSTREE_REMOTE':  self.ostree_remote,
                         'OS_PRETTY': self.os_pretty_name,
                         'OS_VER': self.release,
                         'OS_VER': self.release,
                         'OSTREE_URL': ostree_url
                         }

        for subname, subval in substitutions.iteritems():
            if subval is None:
                continue
            lorax_tmpl = lorax_tmpl.replace('@%s@' % (subname, ), subval)

        self.dumpTempMeta(os.path.join(self.workdir, "lorax.tmpl"), lorax_tmpl)

        os_pretty_name = os_pretty_name = '"{0}"'.format(self.os_pretty_name)
        parts = self.docker_os_name.split("/")
        docker_os = parts[0]
        for i in parts[1:]:
            docker_os += '/%s' % i.replace(".", "")
        docker_image_name = '{0}/rpmostree-toolbox-lorax'.format(docker_os)
        if not ('docker-lorax' in self.args.skip_subtask):
            self._buildDockerImage(docker_image_name)
        else:
            log("Skipping subtask docker-lorax")

        # Docker run
        dr_cidfile = os.path.join(self.workdir, "containerid")

        dr_cmd = ['docker', 'run', '--rm', '--workdir', '/out', '--net=host', '--privileged=true',
                  '-v', '{0}:{1}'.format(self.image_workdir, '/out'), docker_image_name]

        child_env = dict(os.environ)
        if 'http_proxy' in child_env:
            del child_env['http_proxy']
        run_sync(dr_cmd, env=child_env)

        if not self.ostree_repo_is_remote:
            trivhttp.stop()

        # We injected data into boot.iso, so it's now installer.iso
        lorax_output = self.image_workdir + '/lorax'
        lorax_images = lorax_output + '/images'
        os.rename(lorax_images + '/boot.iso', lorax_images + '/installer.iso')

        treeinfo = lorax_output + '/.treeinfo'
        treeinfo_tmp = treeinfo + '.tmp'
        with open(treeinfo) as treein:
            with open(treeinfo_tmp, 'w') as treeout:
                for line in treein:
                    if line.startswith('boot.iso'):
                        treeout.write(line.replace('boot.iso', 'installer.iso'))
                    else:
                        treeout.write(line)
        os.rename(treeinfo_tmp, treeinfo)

        os.rename(lorax_output, self.image_content_outputdir)
        os.mkdir(self.image_log_outputdir)
        for fname in os.listdir(self.image_workdir):
            if not fname.endswith('.log'):
                continue
            shutil.move(self.image_workdir + '/' + fname, self.image_log_outputdir)

# End Composer


def main(cmd):
    parser = argparse.ArgumentParser(description='Create an installer image',
                                     parents=ImageTaskBase.all_baseargs())
    parser.add_argument('-b', '--yum_baseurl', type=str, required=False, help='Full URL for the yum repository')
    parser.add_argument('-p', '--profile', type=str, default='DEFAULT', help='Profile to compose (references a stanza in the config file)')
    parser.add_argument('-v', '--verbose', action='store_true', help='verbose output')
    parser.add_argument('--skip-subtask', action='append', help='Skip a subtask (currently: docker-lorax)', default=[])
    parser.add_argument('--post', type=str, help='Run this %%post script in interactive installs')
    args = parser.parse_args()
    composer = InstallerTask(args, cmd, profile=args.profile)
    composer.show_config()
    global verbosemode
    verbosemode = args.verbose

    composer.create(post=args.post)

    composer.cleanup()
