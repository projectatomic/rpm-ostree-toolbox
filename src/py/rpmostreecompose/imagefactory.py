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
from gi.repository import Gio, OSTree, GLib  # pylint: disable=no-name-in-module
import ConfigParser
import libvirt
import xml.etree.ElementTree as ET


from imgfac.PersistentImageManager import PersistentImageManager

# For ImageFactory builds
from imgfac.BuildDispatcher import BuildDispatcher
from imgfac.PluginManager import PluginManager
from imgfac.ApplicationConfiguration import ApplicationConfiguration
import logging

from .taskbase import TaskBase

from .utils import run_sync, fail_msg, TrivialHTTP, log


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
        config['rhevm_image_format'] = 'qcow2'
        ApplicationConfiguration(configuration=config)
        plugin_mgr = PluginManager('/etc/imagefactory/plugins.d')
        plugin_mgr.load()

        self.fhandler = logging.StreamHandler(sys.stdout)
        self.tlog = logging.getLogger()
        self.tlog.setLevel(logging.DEBUG)
        self.tlog.addHandler(self.fhandler)
        verbosemode = kwargs.get('verbosemode', False)

        if verbosemode:
            ch = logging.StreamHandler(sys.stdout)
            ch.setLevel(logging.DEBUG)
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            ch.setFormatter(formatter)
            self.tlog.addHandler(ch)

        pass

    def build(self, template=None, parameters=None):
        bd = BuildDispatcher()
        builder = bd.builder_for_base_image(template=template,
                                            parameters=parameters)
        image = builder.base_image
        thread = builder.base_thread

        thread.join()

        if image.status != "COMPLETE":
            fail_msg("Failed image status: " + image.status)
        return image

    def buildimagetype(self, imagetype, baseid, imgopts={}):
        """
        This method compliments the builder method by taking its
        uuid and outputputting various image formats
        """

        # This dict maps the imagetype to an imageformat
        imageformats = {'kvm':'kvm', 'rhevm': 'rhevm', 'vsphere':'vsphere', 
                        'vagrant-libvirt':'rhevm', 'vagrant-virtualbox': 'vsphere'
                        }

        log("Working on a {0} for {1}".format(imagetype, baseid))
        vagrant = True if imagetype in ['vagrant-virtualbox', 'vagrant-libvirt'] else False
        bd = BuildDispatcher()
        imagebuilder = bd.builder_for_target_image(imageformats[imagetype], image_id=baseid, template=None, parameters=imgopts)
        target_image = imagebuilder.target_image
        thread = imagebuilder.target_thread
        thread.join()
        if target_image.status != "COMPLETE":
            fail_msg("Failed image status: " + target_image.status)

        # Now doing the OVA

        log("Creating OVA for {0}".format(imagetype))

        bdi = BuildDispatcher()
        if imagetype == 'vagrant-virtualbox' :
            imgopts['vsphere_ova_format'] = 'vagrant-virtualbox'
        if imagetype == 'vagrant-libvirt':
            imgopts['rhevm_ova_format'] = 'vagrant-libvirt'

        ovabuilder = bdi.builder_for_target_image("ova", image_id=target_image.identifier, template=None, parameters=imgopts)
        target_ova = ovabuilder.target_image
        ovathread = ovabuilder.target_thread
        ovathread.join()
        if target_ova.status != "COMPLETE":
            fail_msg("Failed image status: " + target_ova.status)
        return target_ova

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

class AbstractImageFactoryTask(TaskBase):
    def __init__(self, *args, **kwargs):
        TaskBase.__init__(self, *args, **kwargs)
        self.ozoverrides = {}

    def addozoverride(self, cfgsec, key, value):
        """
        Method that takes oz config section and adds a key
        and value to prepare an json formatted oz override
        value
        """
        if cfgsec not in self.ozoverrides.keys():
            self.ozoverrides[cfgsec] = {}
        self.ozoverrides[cfgsec][key] = value

    def checkoz(self, defimagetype):
        """
        Method which checks the oz.cfg for certain variables to alert
        user to potential errors caused by the cfg itself. It also
        returns the default image type.
        """
        cfg = ConfigParser.SafeConfigParser()
        cfg.read('/etc/oz/oz.cfg')

        # Set default image to always be KVM
        self.addozoverride('libvirt', 'image_type', defimagetype)

        if cfg.has_option("libvirt","memory"):
            if int(cfg.get("libvirt","memory")) < 2048:
                log("Your current oz configuration specifies a memory amount of less than 2048 which can lead to possible image creation failures. Overriding temporarily to 2048")
                self.addozoverride('libvirt', 'memory', 2048)

        else:
            # We need at least 2GB of memory for imagefactory
            self.addozoverride('libvirt', 'memory', 2048)

        # Two cpus is prefered for producer/consumer ops
        self.addozoverride('libvirt', 'cpus', '2')

        log("Oz overrides: {0}".format(self.ozoverrides))

    def formatKS(self, ksfile):
        ksfile = os.path.abspath(ksfile)
        ks_basename = os.path.basename(ksfile)
        # FIXME - eventually stop hardcoding this via some mapping
        if ks_basename.find('fedora') >= 0:
            kickstart_version = self.release.upper()
        else:
            kickstart_version = 'RHEL7'

        dockerfile = """CMD ["ksflatten", "--version", "{0}", "-c", "/in/{1}", "-o", "/out/{1}"]""".format(kickstart_version, ks_basename)
        contextdir = os.path.join(self.workdir, 'tmp-kickstart')
        if os.path.isdir(contextdir): shutil.rmtree(contextdir)
        os.mkdir(contextdir)
        ksworker_name = self.buildDockerWorker('kickstart', ['pykickstart'], dockerfile, contextdir)

        cmd = ['docker', 'run', '--workdir', '/out', '-it', '--net=none',
               '-v', '{0}:{1}:ro'.format(os.path.dirname(ksfile), '/in'),
               '-v', '{0}:{1}'.format(contextdir, '/out'),
               ksworker_name]
        child_env = dict(os.environ)
        if 'http_proxy' in child_env:
            del child_env['http_proxy']
        run_sync(cmd, env=child_env)

        flattened_ks = self.workdir + '/' + ks_basename
        os.rename(contextdir + '/' + ks_basename, flattened_ks)

        # TODO: Pull kickstart from separate git repo
        ksdata = open(flattened_ks).read()
        substitutions = { 'OSTREE_REF':  self.ref,
                          'OSTREE_OSNAME':  self.os_name}

        if '@OSTREE_PORT@' in ksdata:
             substitutions['OSTREE_PORT'] = self.httpd_port

        if '@OSTREE_HOST_IP@' in ksdata:
            if not self.ostree_repo_is_remote:
                host_ip = getDefaultIP(hostnet=self.virtnetwork)
            else:
                host_ip = self.httpd_host
            substitutions['OSTREE_HOST_IP'] = host_ip

        if '@OSTREE_PATH@' in ksdata:
            substitutions['OSTREE_PATH'] = self.httpd_path

        if '@OSTREE_LOCATION@' in ksdata:
            if not self.ostree_repo_is_remote:
                ostree_location = "file:///install/ostree"
            else:
                ostree_location = "http://{0}:{1}:{2}".format(self.httpd_host, self.httpd_port, self.httpd_path)
            substitutions['OSTREE_LOCATION'] = ostree_location

        for subname, subval in substitutions.iteritems():
            ksdata = ksdata.replace('@%s@' % (subname, ), subval)
        return ksdata


class ImageFactoryTask(AbstractImageFactoryTask):
    def __init__(self, args, cmd, profile):
        AbstractImageFactoryTask.__init__(self, args, cmd, profile)

    def create(self, imageoutputdir, name, ksfile, vkickstart, tdl, imageouttypes):
        #AbstractImageFactoryTask.__init__(self)
        self._name = name
        self._tdl = tdl
        self._kickstart = ksfile
        self._imageoutputdir = imageoutputdir
        self.vksfile = None
        self.vagrant = False
        if len(self.returnCommon(imageouttypes, ['vagrant-libvirt', 'vagrant-virtualbox'])) > 0:
            self.vagrant = True
            self.vksfile = vkickstart if vkickstart is not None else os.path.join(os.path.dirname(ksfile),os.path.basename(ksfile).replace(".ks","-vagrant.ks"))
            if not os.path.isfile(self.vksfile):
                fail_msg("Unable to find the kickstart file {0} required to build vagrant images.  Consider passing --vkickstart to override.".format(self.vksfile))
        
        os.mkdir(imageoutputdir)

        # FIXME : future version control related
        # [res, rev] = self.repo.resolve_rev(self.ref, False)
        # [res, commit] = self.repo.load_variant(OSTree.ObjectType.COMMIT, rev)

        # commitdate = GLib.DateTime.new_from_unix_utc(OSTree.commit_get_timestamp(commit)).format("%c")
        # print commitdate

        port_file_path = self.workdir + '/repo-port'

        if not self.ostree_repo_is_remote: 
            # Start trivial-httpd
            trivhttp = TrivialHTTP()
            trivhttp.start(self.ostree_repo)
            self.httpd_port = str(trivhttp.http_port)
            log("trivial httpd port=%s, pid=%s" % (self.httpd_port, trivhttp.http_pid))
        else:
            httpd_port = self.ostree_port

        self.checkoz("qcow2")
        # The conditional handles the building of the images listed below
        if len(self.returnCommon(imageouttypes, ['rhevm', 'vsphere', 'kvm', 'raw', 'hyperv'])) > 0:
            ksdata = self.formatKS(ksfile)
            parameters =  { "install_script": ksdata,
                            "generate_icicle": False,
                            "oz_overrides": json.dumps(self.ozoverrides)
                          }
            log("Starting build")
            image = self.builder.build(template=open(self._tdl).read(), parameters=parameters)

            # For debug, you can comment out the above and enable the code below
            # to skip the initial image creation.  Just point myuuid at the proper
            # image uuid

            # self.builder.download()
            # myuuid = "fd301dce-fba3-421d-a2e8-182cf2cefaf8"
            # pim = PersistentImageManager.default_manager()
            # image = pim.image_with_id(myuuid)

            # Copy the qcow2 file to the outputdir
            outputname = os.path.join(imageoutputdir, '%s.qcow2' % (self.os_nr))
            shutil.copyfile(image.data, outputname)
            log("Created: {0}".format(outputname))

            if 'raw' in imageouttypes:
                log("Processing image from qcow2 to raw")
                outputname = os.path.join(imageoutputdir, '%s.raw' % (self.os_nr))

                qemucmd = ['qemu-img', 'convert', '-f', 'qcow2', '-O', 'raw', image.data, outputname]
                run_sync(qemucmd)
                imageouttypes.pop(imageouttypes.index("raw"))
                log("Created: {0}".format(outputname))

            if 'hyperv' in imageouttypes:
                outputname = os.path.join(imageoutputdir, '%s-hyperv.vhd' % (self.os_nr))
                # We can only create a gen1 hyperv image with no ova right now
                qemucmd = ['qemu-img', 'convert', '-f', 'qcow2', '-O', 'vpc', image.data, outputname]
                run_sync(qemucmd)
                imageouttypes.pop(imageouttypes.index("hyperv"))
                log("Created: {0}".format(outputname))

            for imagetype in self.returnCommon(imageouttypes, ['rhevm','vsphere']):
                self.generateOVA(imagetype, "ova", image)

        # This conditional handles the vagrant images
        if self.vagrant:
            # vagrant images need a new base image with changes in the KS
            ksdata = self.formatKS(self.vksfile)
            parameters =  { "install_script": ksdata,
                            "generate_icicle": False,
                            "oz_overrides": json.dumps(self.ozoverrides)
                           }
            vimage = self.builder.build(template=open(self._tdl).read(), parameters=parameters)

            for imagetype in self.returnCommon(imageouttypes, ['vagrant-libvirt','vagrant-virtualbox']):
                self.generateOVA(imagetype, "box", vimage)

        if not self.ostree_repo_is_remote: 
            trivhttp.stop()


    @property
    def builder(self):
        # TODO: option to switch to koji builder
        if True:
            global verbosemode
            return ImgFacBuilder(workdir=self.workdir, verbosemode=verbosemode)
        else:
            return KojiBuilder()


    def generateOVA(self, imagetype, fileext, image):
        log("Creating {0} image".format(imagetype))
        # Imgfac will ensure proper qemu type is used
        target_image = self.builder.buildimagetype(imagetype, image.identifier)
        infile = target_image.data
        outfile = os.path.join(self._imageoutputdir, '%s-%s.%s' % (self._name, imagetype, fileext))
        shutil.copyfile(infile, outfile)
        log("Created: {0}".format(outfile))


    def returnCommon(self, list1, list2):
        return list(set(list1).intersection(list2))


## End Composer

def getDefaultIP(hostnet=None):
    """
    This method determines returns the IP of the atomic host, which
    is used by the kickstart file to find the atomic repository. It can
    accept a virt network name to help determine the IP.  Else, it will
    count the number of networks and if only one use that.  Else it
    will look for one named default.
    """
    conn=libvirt.open()

    numnets = int(conn.numOfNetworks())

    if numnets < 1:
        fail_msg("No libvirt networks appear to be defined.  Ensure you have a network defined and re-run.")
        exit(1)

    netlist = conn.listNetworks()

    if hostnet is not None:
        netname = hostnet
    elif conn.numOfNetworks() == 1:
        netname = netlist[0]
    elif "default" in netlist:
        netname = "default"
    else:
        fail_msg("Unable to determine your libvirt network automatically.  Please re-run with --virtnetwork switch and the name of the network you want to use (from virsh net-list)")

    interface = conn.networkLookupByName(netname)
    root = ET.fromstring(interface.XMLDesc())
    ip = root.find("ip").get('address')
    return ip



def parseimagetypes(imagetypes):
    default_image_types = ["kvm", "raw", "vsphere", "rhevm", "vagrant-virtualbox", "vagrant-libvirt", "hyperv"]
    if imagetypes == None:
        return default_image_types

    # Check that input types are valid
    for i in imagetypes:
        if i not in default_image_types:
            log("{0} is not a valid image type.  The valid types are {1}".format(i, default_image_types))
            exit(1) 

    return imagetypes


def main(cmd):
    parser = argparse.ArgumentParser(description='Use ImageFactory to create a disk image',
                                     parents=[TaskBase.baseargs()])
    parser.add_argument('-i', '--images', help='Output image formats in list format', action='append')
    parser.add_argument('--name', type=str, required=False, help='Image name')
    parser.add_argument('--tdl', type=str, required=False, help='TDL file')
    parser.add_argument('--virtnetwork', default=None, type=str, required=False, help='Optional name of libvirt network')
    parser.add_argument('-o', '--outputdir', type=str, required=True, help='Path to image output directory')
    parser.add_argument('--overwrite', action='store_true', help='If true, replace any existing output')
    parser.add_argument('-k', '--kickstart', type=str, required=False, default=None, help='Path to kickstart') 
    parser.add_argument('--vkickstart', type=str, required=False, help='Path to vagrant kickstart') 
    parser.add_argument('-p', '--profile', type=str, default='DEFAULT', help='Profile to compose (references a stanza in the config file)')
    parser.add_argument('-v', '--verbose', action='store_true', help='verbose output')
    args = parser.parse_args()
     
    imagetypes = parseimagetypes(args.images)

    if os.path.exists(args.outputdir):
        if not args.overwrite:
            fail_msg("The output directory {0} already exists.".format(args.outputdir))
        else:
            shutil.rmtree(args.outputdir)

    composer = ImageFactoryTask(args, cmd, profile=args.profile)

    composer.show_config()
    global verbosemode
    verbosemode = args.verbose
    try:
        composer.create(imageoutputdir=args.outputdir,
                        name=composer.name,
                        ksfile=composer.kickstart,
                        vkickstart=args.vkickstart,
                        tdl=composer.tdl,
                        imageouttypes=imagetypes
                        )
    finally:
        composer.cleanup()
