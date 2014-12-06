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
import argparse
import subprocess
import oz.TDL
import oz.GuestFactory
import tarfile

from .taskbase import TaskBase
from .utils import fail_msg, run_sync
from .imagefactory import ImageFunctions
from .imagefactory import ImgFacBuilder
from imgfac.BuildDispatcher import BuildDispatcher
from imgfac.PersistentImageManager import PersistentImageManager
from xml.etree import ElementTree as ET
from .imagefactory import getDefaultIP


class InstallerTask(TaskBase):
    container_id = ""

    def getrepos(self, flatjson):
        fj = open(flatjson)
        fjparams = json.load(fj)
        repos = ""
        for repo in fjparams['repos']:
            repofile = os.path.join(getattr(self, 'configdir'), repo + ".repo")
            repos = repos + open(repofile).read()
            repos = repos + "enabled=1"
            repos = repos + "\n"
        return repos

    def template_xml(self, repos, tmplfilename):
        tree = ET.parse(tmplfilename)
        root = tree.getroot()
        files = root.find('files')
        yumrepos = ET.SubElement(files, "file", {'name': '/etc/yum.repos.d/atomic.repo'})
        yumrepos.text = repos
        return ET.tostring(root)

    def dumpTempMeta(self, fullpathname, tmpstr):
        with open(fullpathname, 'w') as f:
            f.write(tmpstr)
        print "Wrote {0}".format(fullpathname)
        return fullpathname

    def createUtilKS(self, tdl):
        util_post = """
%post
# For cloud images, 'eth0' _is_ the predictable device name, since
# we don't want to be tied to specific virtual (!) hardware
rm -f /etc/udev/rules.d/70*
ln -s /dev/null /etc/udev/rules.d/80-net-setup-link.rules

# simple eth0 config, again not hard-coded to the build hardware
cat > /etc/sysconfig/network-scripts/ifcfg-eth0 << EOF
DEVICE="eth0"
BOOTPROTO="dhcp"
ONBOOT="yes"
TYPE="Ethernet"
PERSISTENT_DHCLIENT="yes"
EOF
%end
"""
        util_tdl = oz.TDL.TDL(open(tdl).read())
        oz_class = oz.GuestFactory.guest_factory(util_tdl, None, None)
        util_ksname = oz_class.get_auto_path()
        util_ks = open(util_ksname).read()
        util_ks = util_ks + util_post
        util_ksfilename = os.path.join(self.workdir, os.path.basename(util_ksname.replace(".auto", ".ks")))

        # Write out to tmp file in workdir
        self.dumpTempMeta(util_ksfilename, util_ks)

        return util_ks

    def returnDockerFile(self):
        docker_subs = {'DOCKER_OS': getattr(self, 'docker_os_name')}
        docker_file = """
FROM @DOCKER_OS@
ADD lorax.repo /etc/yum.repos.d/
ADD lorax.tmpl /root/
ADD lorax.sh /root/
RUN chmod u+x /root/lorax.sh
RUN yum -y update && yum -y clean all
RUN yum -y swap fakesystemd systemd && yum -y clean all
RUN yum -y install ostree lorax && yum -y clean all
CMD ["/bin/sh", "/root/lorax.sh"]
        """

        for subname, subval in docker_subs.iteritems():
            docker_file = docker_file.replace('@%s@' % (subname, ), subval)

        return docker_file, getattr(self, 'docker_os_name')

    def createContainer(self, outputdir, post=None):
        imgfunc = ImageFunctions()
        repos = self.getrepos(self.jsonfilename)
        self.dumpTempMeta(os.path.join(self.workdir, "lorax.repo"), repos)
        lorax_tmpl = open(os.path.join(self.pkgdatadir, 'lorax-http-repo.tmpl')).read()
        lorax_repos = []
        if self.lorax_additional_repos:
            if getattr(self, 'yum_baseurl') not in self.lorax_additional_repos:
                self.lorax_additional_repos += ", {0}".format(getattr(self, 'yum_baseurl'))
            for repourl in self.lorax_additional_repos.split(','):
                lorax_repos.extend(['-s', repourl.strip()])
        else:
            lorax_repos.append('-s {0}'.format(getattr(self, 'yum_baseurl')))
        port_file_path = self.workdir + '/repo-port'
        subprocess.check_call(['ostree',
                               'trivial-httpd', '--autoexit', '--daemonize',
                               '--port-file', port_file_path],
                              cwd=self.ostree_repo)

        httpd_port = open(port_file_path).read().strip()
        substitutions = {'OSTREE_PORT': httpd_port,
                         'OSTREE_REF':  self.ref,
                         'OSTREE_OSNAME':  self.os_name,
                         'LORAX_REPOS': " ".join(lorax_repos),
                         'OS_PRETTY': self.os_pretty_name,
                         'OS_VER': self.release
                         }
        if '@OSTREE_HOSTIP@' in lorax_tmpl:
            host_ip = "localhost"
            substitutions['OSTREE_HOSTIP'] = host_ip

        for subname, subval in substitutions.iteritems():
            print subname
            lorax_tmpl = lorax_tmpl.replace('@%s@' % (subname, ), subval)

        self.dumpTempMeta(os.path.join(self.workdir, "lorax.tmpl"), lorax_tmpl)

        os_v = getattr(self, 'release')
        os_pretty_name = os_pretty_name = '"{0}"'.format(getattr(self, 'os_pretty_name'))

        docker_file, docker_os = self.returnDockerFile()

        lorax_cmd = ['lorax', '--nomacboot', '--add-template=/root/lorax.tmpl', '-e', 'fakesystemd', '-e', 'systemd-container', '-p', os_pretty_name, '-v', os_v, '-r', os_v, " ".join(lorax_repos), '/out']
        http_proxy = os.environ.get('http_proxy')
        if http_proxy:
            lorax_cmd.extend(['--proxy', http_proxy])

        # There is currently a bug for loop devices in containers,
        # so we make at least one device to be sure.
        # https://groups.google.com/forum/#!msg/docker-user/JmHko2nstWQ/5iuzVf67vfEJ

        lorax_shell = """#!/bin/sh\n
mknod -m660 /dev/loop0 b 7 0
exec 
        lorax_shell = "mknod -m660 /dev/loop0 b 7 0 \n"
        lorax_shell = lorax_shell + " ".join(lorax_cmd)
        self.dumpTempMeta(os.path.join(self.workdir, "lorax.sh"), lorax_shell)

        tmp_docker_file = self.dumpTempMeta(os.path.join(self.workdir, "Dockerfile"), docker_file)

        # Docker build
        db_cmd = ['docker', 'build', '-t', docker_os, os.path.dirname(tmp_docker_file)]
        run_sync(db_cmd)

        # Docker run
        dr_cidfile = os.path.join(self.workdir, "containerid")
        dr_cmd = ['docker', 'run', '-it', '--net=host', '--privileged=true', '--cidfile="' + dr_cidfile + '"', docker_os]
        run_sync(dr_cmd)
        cid = open(dr_cidfile).read().strip()

        # Copy the files images out
        dcp_cmd = ['docker', 'cp', cid + ":/out/images", outputdir]
        print "Copied images to " + outputdir
        run_sync(dcp_cmd)

        # Cop lorax logs to tempspace
        dock_logs = ['lorax.log', 'program.log', 'yum.log']
        for log in dock_logs:
            dcp_cmd = ['docker', 'cp', cid + ":/" + log, os.path.join(self.workdir)]
            print "Copying {0} to {1}".format(log, os.path.join(self.workdir))
            run_sync(dcp_cmd)

        # Copy the log to the tmp
        # Marshalling issues, doesnt work yet
        # dlog_cmd = ['docker', 'logs', cid]
        # docker_log = json.JSONEncoder(subprocess.check_output(dlog_cmd))
        # self.dumpTempMeta(os.path.join(self.workdir, "docker.log"), docker_log)

    def create(self, outputdir, post=None):
        imgfunc = ImageFunctions()
        repos = self.getrepos(self.jsonfilename)
        util_xml = self.template_xml(repos, os.path.join(self.pkgdatadir, 'lorax-indirection-repo.tmpl'))
        lorax_repos = []
        if self.lorax_additional_repos:
            if getattr(self, 'yum_baseurl') not in self.lorax_additional_repos:
                self.lorax_additional_repos += ", {0}".format(getattr(self, 'yum_baseurl'))
            for repourl in self.lorax_additional_repos.split(','):
                lorax_repos.extend(['-s', repourl.strip()])
        else:
            lorax_repos.append('-s {0}'.format(getattr(self, 'yum_baseurl')))

        port_file_path = self.workdir + '/repo-port'
        subprocess.check_call(['ostree',
                               'trivial-httpd', '--autoexit', '--daemonize',
                               '--port-file', port_file_path],
                              cwd=self.ostree_repo)

        httpd_port = open(port_file_path).read().strip()
        print "trivial httpd port=%s" % (httpd_port, )
        substitutions = {'OSTREE_PORT': httpd_port,
                         'OSTREE_REF':  self.ref,
                         'OSTREE_OSNAME':  self.os_name,
                         'LORAX_REPOS': " ".join(lorax_repos),
                         'OS_PRETTY': self.os_pretty_name,
                         'OS_VER': self.release
                         }
        if '@OSTREE_HOSTIP@' in util_xml:
            host_ip = getDefaultIP()
            substitutions['OSTREE_HOSTIP'] = host_ip

        print type(util_xml)
        for subname, subval in substitutions.iteritems():
            util_xml = util_xml.replace('@%s@' % (subname, ), subval)

        # Dump util_xml to workdir for logging
        self.dumpTempMeta(os.path.join(self.workdir, "lorax.xml"), util_xml)
        global verbosemode
        imgfacbuild = ImgFacBuilder(verbosemode=verbosemode)
        imgfacbuild.verbosemode = verbosemode
        imgfunc.checkoz()
        util_ks = self.createUtilKS(self.tdl)

        # Building of utility image
        parameters = {"install_script": util_ks,
                      "generate_icicle": False,
                      "oz_overrides": json.dumps(imgfunc.ozoverrides)
                      }
        print "Starting build"
        if self.util_uuid is None:
            util_image = imgfacbuild.build(template=open(self.util_tdl).read(), parameters=parameters)
            print "Created Utility Image: {0}".format(util_image.data)

        else:
            pim = PersistentImageManager.default_manager()
            util_image = pim.image_with_id(self.util_uuid)
            print "Re-using Utility Image: {0}".format(util_image.identifier)

        # Now lorax
        bd = BuildDispatcher()
        lorax_parameters = {"results_location": "/lorout/output.tar",
                            "utility_image": util_image.identifier,
                            "utility_customizations": util_xml,
                            "oz_overrides": json.dumps(imgfunc.ozoverrides)
                            }
        print "Building the lorax image"
        loraxiso_builder = bd.builder_for_target_image("indirection", image_id=util_image.identifier, template=None, parameters=lorax_parameters)
        loraxiso_image = loraxiso_builder.target_image
        thread = loraxiso_builder.target_thread
        thread.join()

        # Extract the tarball of built images
        print "Extracting images to {0}/images".format(outputdir)
        t = tarfile.open(loraxiso_image.data)
        t.extractall(path=outputdir)

# End Composer


def main(cmd):
    parser = argparse.ArgumentParser(description='Create an installer image',
                                     parents=[TaskBase.baseargs()])
    parser.add_argument('-b', '--yum_baseurl', type=str, required=False, help='Full URL for the yum repository')
    parser.add_argument('-p', '--profile', type=str, default='DEFAULT', help='Profile to compose (references a stanza in the config file)')
    parser.add_argument('--util_uuid', required=False, default=None, type=str, help='The UUID of an existing utility image')
    parser.add_argument('--util_tdl', required=False, default=None, type=str, help='The TDL for the utility image')
    parser.add_argument('-v', '--verbose', action='store_true', help='verbose output')
    parser.add_argument('--virt', action='store_true', help='Use libvirt')
    parser.add_argument('--post', type=str, help='Run this %%post script in interactive installs')
    parser.add_argument('-o', '--outputdir', type=str, required=False, help='Path to image output directory')
    args = parser.parse_args()
    composer = InstallerTask(args, cmd, profile=args.profile)
    composer.show_config()
    global verbosemode
    verbosemode = args.verbose
    if args.virt:
        composer.create(outputdir=getattr(composer, 'outputdir'), post=args.post)
    else:
        composer.createContainer(outputdir=getattr(composer, 'outputdir'), post=args.post)

    composer.cleanup()
