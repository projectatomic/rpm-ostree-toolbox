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
from .imagefactory import ImageFunctions
from .imagefactory import ImageFactoryTask
from .imagefactory import ImgFacBuilder
from imgfac.BuildDispatcher import BuildDispatcher
from imgfac.PersistentImageManager import PersistentImageManager
import json



class CreateLiveTask(TaskBase):
    def createLiveDisk(self, imageoutputdir, tdl, ksfile, name):
        self._imageoutputdir = imageoutputdir
        self._tdl = tdl
        self._ksfile = ksfile
        self._name = name
        self.ref = self.ref
        workdir = self.workdir
        imgfunc = ImageFunctions()
        imgfunc.checkoz("raw")
        imgfacbuild = ImgFacBuilder()
        #imgfactask = ImageFactoryTask()
        #if not self.ostree_repo_is_remote: 
        print "************"
        print self.ref
        print self.ostree_port
        print self.ostree_repo
        print self.ostree_repo_is_remote
        print self.ref
        print self.os_name


        ksdata = imgfunc.formatKS(ksfile)
        print ksdata

        exit(1)
        parameters = {"install_script": ksdata,
                       "generate_icicle": False,
                       "oz_overrides": json.dumps(imgfunc.ozoverrides)
                      }
        print "Starting build"
        image = imgfacbuild.build(template=open(self._tdl).read(), parameters=parameters)
        print "**********************************"
        print image.data
        print "**********************************"


# End liveimage

def main(cmd):
    parser = argparse.ArgumentParser(description='Create live images', parents=[TaskBase.baseargs()])
    parser.add_argument('--overwrite', action='store_true', help='If true, replace any existing output')
    parser.add_argument('-o', '--outputdir', type=str, required=True, help='Path to image output directory')
    parser.add_argument('-p', '--profile', type=str, default='DEFAULT', help='Profile to compose (references a stanza in the config file)')
    parser.add_argument('-k', '--kickstart', type=str, required=False, default=None, help='Path to kickstart') 
    parser.add_argument('--tdl', type=str, required=False, help='TDL file')
    parser.add_argument('--name', type=str, required=False, help='Image name')
    
    args = parser.parse_args()

    if os.path.exists(args.outputdir):
        if not args.overwrite:
            fail_msg("The output directory {0} already exists.".format(args.outputdir))
        else:
            shutil.rmtree(args.outputdir)

    composer = CreateLiveTask(args, cmd, profile=args.profile)
    composer.show_config()
    try:
        composer.createLiveDisk(imageoutputdir=args.outputdir,
                        name=getattr(composer, 'name'),
                        ksfile=getattr(composer, 'kickstart'),
                        tdl=getattr(composer, 'tdl'),
                        )

    finally:
        #composer.cleanup()
        print "do some cleanup?"
