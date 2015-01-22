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
from imgfac.BuildDispatcher import BuildDispatcher
from imgfac.PersistentImageManager import PersistentImageManager
import json



class CreateLiveTask(AbstractImageFactoryTask):
    def __init__(self, args, cmd, profile):
        AbstractImageFactoryTask.__init__(self, args, cmd, profile)
        self._args = args
        self._cmd = cmd
        self._profile = profile
        print "++++++++++++++++++++++"
        print args
        print cmd
        print profile
        print "++++++++++++++++++++++"
        print vars(self)
        
    def createLiveDisk(self):
        for i in vars(TaskBase):
            print i
        print vars(TaskBase)
        print self.__dict__
        #print getattr(self, 'ref')
        #self.show_config()
        
        #AbstractImageFactoryTask.__init__(imageoutputdir, name, ksfile, tdl)
        #TaskBase.__init__(args, cmd, profile)
        print self._args.outputdir
        self.checkoz("raw")

        #imgfunc = AbstractImageFactoryTask()
        #imgfunc = ImageFunctions()
        #imgfunc.checkoz("raw")
        #imgfacbuild = ImgFacBuilder()
        #imgfactask = ImageFactoryTask()
        #if not self.ostree_repo_is_remote: 
        print "************"
        ksfile = self._args.kickstart
        ksdata = self.formatKS(ksfile)
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
    #composer = CreateLiveTask()
    #taskbase = TaskBase(args, cmd, profile=args.profile)
    #composer.show_config()
    #print getattr(taskbase, 'name')
    try:
        composer.createLiveDisk()
        #composer.createLiveDisk(imageoutputdir=args.outputdir,
        #                name=getattr(taskbase, 'name'),
        #                ksfile=getattr(taskbase, 'kickstart'),
        #                tdl=getattr(taskbase, 'tdl'),
        #                taskbase=taskbase
        #                )

    finally:
        #composer.cleanup()
        print "do some cleanup?"
