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

from .taskbase import TaskBase
from .utils import fail_msg, run_sync, TrivialHTTP, log
from .imagefactory import AbstractImageFactoryTask
from .imagefactory import ImgFacBuilder
from imgfac.BuildDispatcher import BuildDispatcher
from imgfac.PersistentImageManager import PersistentImageManager
from xml.etree import ElementTree as ET
from .imagefactory import getDefaultIP

from gi.repository import GLib  # pylint: disable=no-name-in-module

class InstallerTask(TaskBase):
    container_id = ""

    def __init__(self, *args, **kwargs):
        TaskBase.__init__(self, *args, **kwargs)
        self.tdl = None

    def getrepos(self, flatjson):
        fj = open(flatjson)
        fjparams = json.load(fj)
        repos = ""
        repoids = []
        for repo in fjparams['repos']:
            repofile = os.path.join(getattr(self, 'configdir'), repo + ".repo")
            repos = repos + open(repofile).read()
            repos = repos + "enabled=1"
            repos = repos + "\n"
            repoids.append(repo)
        if self.lorax_additional_repos:
            for i,repourl in enumerate(self.lorax_additional_repos.split(',')):
                repos += "[lorax-repo-{0}]\nbaseurl={1}\nenabled=1\ngpgcheck=0\n".format(i, repourl)
                repoids.append('lorax-repo-{0}'.format(i))
        return repoids,repos

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
        log("Wrote {0}".format(fullpathname))
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

    def _buildDockerImage(self, docker_image_name):
        repoids, repos = self.getrepos(self.jsonfilename)
        log("Using lorax.repo:\n" + repos)
        self.dumpTempMeta(os.path.join(self.workdir, "lorax.repo"), repos)

        packages = ['lorax', 'rpm-ostree', 'ostree']

        docker_image_basename = docker_image_name + '-base'

        docker_builder_argv = ['rpm-ostree-toolbox', 'docker-image',
                               '--minimize=docs',
                               '--minimize=langs',
                               '--reposdir', self.workdir,
                               '--name', docker_image_basename]
        for r in repoids:
            docker_builder_argv.append('--enablerepo=' + r)

        docker_builder_argv.extend(packages)
                               
        run_sync(docker_builder_argv)

        lorax_repos = []
        if self.lorax_additional_repos:
            if getattr(self, 'yum_baseurl') not in self.lorax_additional_repos:
                self.lorax_additional_repos += ", {0}".format(getattr(self, 'yum_baseurl'))
            for repourl in self.lorax_additional_repos.split(','):
                lorax_repos.extend(['-s', repourl.strip()])
        else:
            lorax_repos.extend(['-s', getattr(self, 'yum_baseurl')])

        os_v = getattr(self, 'release')
        lorax_cmd = ['lorax', '--nomacboot', '--add-template=/root/lorax.tmpl', '-e', 'fakesystemd', '-e', 'systemd-container',
                     '-p', self.os_pretty_name, '-v', os_v, '-r', os_v]
        http_proxy = os.environ.get('http_proxy')
        if http_proxy:
            lorax_cmd.extend(['--proxy', http_proxy])
        if bool(getattr(self, 'is_final')):
            lorax_cmd.append('--isfinal')
        lorax_cmd.extend(lorax_repos)
        excludes = getattr(self, 'lorax_exclude_packages')
        if excludes is not None:
            for exclude in excludes.split(','):
                if exclude == '': continue
                lorax_cmd.extend(['-e', exclude.strip()])
        includes = getattr(self, 'lorax_include_packages')
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
sed -e "s,@OSTREE_PORT@,${{OSTREE_PORT}}," -e "s,@OSTREE_PATH@,${{OSTREE_PATH}}," -e "s,@OSTREE_HOST@,${{OSTREE_HOST}},"  < /root/lorax.tmpl.in > /root/lorax.tmpl
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

    def createContainer(self, installer_outputdir, post=None):
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
        else:
            httpd_port = self.httpd_port
            httpd_url = self.httpd_host
        substitutions = {'OSTREE_REF':  self.ref,
                         'OSTREE_OSNAME':  self.os_name,
                         'OS_PRETTY': self.os_pretty_name,
                         'OS_VER': self.release
                         }

        # Test connectivity to trivial-httpd before we do the full run
        # I'm seeing some issues where it fails sometimes, and this will help
        # speed up debugging.
        run_sync(['curl', 'http://' + httpd_url + ':' + httpd_port])

        for subname, subval in substitutions.iteritems():
            lorax_tmpl = lorax_tmpl.replace('@%s@' % (subname, ), subval)

        self.dumpTempMeta(os.path.join(self.workdir, "lorax.tmpl"), lorax_tmpl)

        os_pretty_name = os_pretty_name = '"{0}"'.format(getattr(self, 'os_pretty_name'))
        docker_image_name = '{0}/rpmostree-toolbox-lorax'.format(getattr(self, 'docker_os_name'))
        if not ('docker-lorax' in self.args.skip_subtask):
            self._buildDockerImage(docker_image_name)
        else:
            log("Skipping subtask docker-lorax")

        installer_outputdir = os.path.abspath(installer_outputdir)
        # Docker run
        dr_cidfile = os.path.join(self.workdir, "containerid")

        dr_cmd = ['docker', 'run', '-e', 'OSTREE_PORT={0}'.format(httpd_port),
                  '-e', 'OSTREE_HOST={0}'.format(httpd_url),
                  '-e', 'OSTREE_PATH={0}'.format(self.httpd_path),
                  '--workdir', '/out', '-it', '--net=host', '--privileged=true',
                  '-v', '{0}:{1}'.format(installer_outputdir, '/out'),
                  docker_image_name]

        child_env = dict(os.environ)
        if 'http_proxy' in child_env:
            del child_env['http_proxy']
        run_sync(dr_cmd, env=child_env)

        if not self.ostree_repo_is_remote:
            trivhttp.stop()

        # We injected data into boot.iso, so it's now installer.iso
        lorax_output = installer_outputdir + '/lorax'
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

    def create(self, installer_outputdir, args, cmd, profile, post=None):
        imgfunc = AbstractImageFactoryTask(args, cmd, profile)
        n_repos, repos = self.getrepos(self.jsonfilename)
        util_xml = self.template_xml(repos, os.path.join(self.pkgdatadir, 'lorax-indirection-repo.tmpl'))
        lorax_repos = []
        if self.lorax_additional_repos:
            if getattr(self, 'yum_baseurl') not in self.lorax_additional_repos:
                self.lorax_additional_repos += ", {0}".format(getattr(self, 'yum_baseurl'))
            for repourl in self.lorax_additional_repos.split(','):
                lorax_repos.extend(['-s', repourl.strip()])
        else:
            lorax_repos.extend(['-s', getattr(self, 'yum_baseurl')])

        port_file_path = self.workdir + '/repo-port'

        if not self.ostree_repo_is_remote: 
            # Start trivial-httpd
            trivhttp = TrivialHTTP()
            trivhttp.start(self.ostree_repo)
            httpd_port = str(trivhttp.http_port)
            log("trivial httpd port=%s, pid=%s" % (httpd_port, trivhttp.http_pid))
        else:
            httpd_port = str(self.httpd_port)
        substitutions = {'OSTREE_PORT': httpd_port,
                         'OSTREE_REF':  self.ref,
                         'OSTREE_OSNAME':  self.os_name,
                         'LORAX_REPOS': " ".join(lorax_repos),
                         'OS_PRETTY': self.os_pretty_name,
                         'OS_VER': self.release
                         }
        if '@OSTREE_HOSTIP@' in util_xml:
            if not self.ostree_repo_is_remote:
                host_ip = getDefaultIP()
            else:
                host_ip = self.httpd_host
            substitutions['OSTREE_HOSTIP'] = host_ip

        if '@OSTREE_PATH' in util_xml:
            substitutions['OSTREE_PATH'] = self.httpd_path

        for subname, subval in substitutions.iteritems():
            util_xml = util_xml.replace('@%s@' % (subname, ), subval)

        # Dump util_xml to workdir for logging
        self.dumpTempMeta(os.path.join(self.workdir, "lorax.xml"), util_xml)
        global verbosemode
        imgfacbuild = ImgFacBuilder(verbosemode=verbosemode)
        imgfacbuild.verbosemode = verbosemode
        imgfunc.checkoz("qcow2")
        util_ks = self.createUtilKS(self.tdl)

        # Building of utility image
        parameters = {"install_script": util_ks,
                      "generate_icicle": False,
                      "oz_overrides": json.dumps(imgfunc.ozoverrides)
                      }
        if self.util_uuid is None:
            log("Starting Utility image build")
            util_image = imgfacbuild.build(template=open(self.util_tdl).read(), parameters=parameters)
            log("Created Utility Image: {0}".format(util_image.data))

        else:
            pim = PersistentImageManager.default_manager()
            util_image = pim.image_with_id(self.util_uuid)
            log("Re-using Utility Image: {0}".format(util_image.identifier))

        # Now lorax
        bd = BuildDispatcher()
        lorax_parameters = {"results_location": "/lorout/output.tar",
                            "utility_image": util_image.identifier,
                            "utility_customizations": util_xml,
                            "oz_overrides": json.dumps(imgfunc.ozoverrides)
                            }
        log("Building the lorax image")
        loraxiso_builder = bd.builder_for_target_image("indirection", image_id=util_image.identifier, template=None, parameters=lorax_parameters)
        loraxiso_image = loraxiso_builder.target_image
        thread = loraxiso_builder.target_thread
        thread.join()

        # Extract the tarball of built images
        log("Extracting images to {0}/images".format(installer_outputdir))
        t = tarfile.open(loraxiso_image.data)
        t.extractall(path=installer_outputdir)
        if not self.ostree_repo_is_remote:
            trivhttp.stop()

# End Composer


def main(cmd):
    parser = argparse.ArgumentParser(description='Create an installer image',
                                     parents=[TaskBase.baseargs()])
    parser.add_argument('-b', '--yum_baseurl', type=str, required=False, help='Full URL for the yum repository')
    parser.add_argument('-p', '--profile', type=str, default='DEFAULT', help='Profile to compose (references a stanza in the config file)')
    parser.add_argument('--util_uuid', required=False, default=None, type=str, help='The UUID of an existing utility image')
    parser.add_argument('--util_tdl', required=False, default=None, type=str, help='The TDL for the utility image')
    parser.add_argument('-v', '--verbose', action='store_true', help='verbose output')
    parser.add_argument('--skip-subtask', action='append', help='Skip a subtask (currently: docker-lorax)', default=[])
    parser.add_argument('--virtnetwork', default=None, type=str, required=False, help='Optional name of libvirt network')
    parser.add_argument('--virt', action='store_true', help='Use libvirt')
    parser.add_argument('--post', type=str, help='Run this %%post script in interactive installs')
    parser.add_argument('-o', '--outputdir', type=str, required=True, help='Path to image output directory')
    parser.add_argument('--overwrite', action='store_true', help='If true, replace any existing output')
    args = parser.parse_args()
    composer = InstallerTask(args, cmd, profile=args.profile)
    composer.show_config()
    global verbosemode
    verbosemode = args.verbose

    installer_outputdir = args.outputdir
    # Check if the lorax outputdir already exists
    lorax_outputdir = os.path.join(installer_outputdir, "lorax")
    if os.path.exists(lorax_outputdir):
        if not args.overwrite:
            fail_msg("The directory {0} already exists.  It must be removed or renamed so that lorax can be run".format(lorax_outputdir))
        else:
            shutil.rmtree(lorax_outputdir)
    elif not os.path.isdir(installer_outputdir):
        fail_msg("The output directory {0} does not exist".format(installer_outputdir))
        
    if args.virt:
        composer.create(installer_outputdir, args, cmd, profile=args.profile, post=args.post)
    else:
        composer.createContainer(installer_outputdir, post=args.post)

    composer.cleanup()
