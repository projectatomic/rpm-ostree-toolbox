#!/usr/bin/env python
# Copyright (C) 2014 Colin Walters <walters@verbum.org>
# Copyright (C) 2014 Andy Grimm <agrimm@redhat.com>
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

import sys
import subprocess

def fail_msg(msg):
    if False:
        raise Exception(msg)
    print >>sys.stderr, msg
    sys.exit(1)

def run_sync(args, **kwargs):
    """Wraps subprocess.check_call(), logging the command line too."""
    print "Running: %s" % (subprocess.list2cmdline(args), )
    subprocess.check_call(args, **kwargs)
