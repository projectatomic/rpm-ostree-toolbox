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
import os
import signal
import ctypes

def fail_msg(msg):
    if False:
        raise Exception(msg)
    print >>sys.stderr, msg
    sys.exit(1)

def run_sync(args, **kwargs):
    """Wraps subprocess.check_call(), logging the command line too."""
    print "Running: %s" % (subprocess.list2cmdline(args), )
    subprocess.check_call(args, **kwargs)


class TrivialHTTP():
    """ This class is used to control ostree's trivial-httpd which is used
    by the installer and imagefactory rpm-ostree-toolbox subcommands to get
    content from the from the host to the builds
    """

    def __init__(self):
        self.f = None
        self.libc = ctypes.CDLL('libc.so.6')
        self.PR_SET_PDEATHSIG = 1
        self.SIGINT = signal.SIGINT
        self.SIGTERM = signal.SIGTERM

    def set_death_signal(self, signal):
        self.libc.prctl(self.PR_SET_PDEATHSIG, signal)
    
    def set_death_signal_int(self):
        self.set_death_signal(self.SIGINT)

    # trivial-httpd does not close its output pipe so we use
    # monitor to deal with it.  If ostree is fixed, this can
    # likely be removed

    def monitor(self):
        lines = iter(self.f.stdout.readline, "")

        for line in lines:
            if int(line) > 0:
                self.http_port = int(line)
                break

    def start(self, repopath):
        self.f = subprocess.Popen(['ostree', 'trivial-httpd', '--autoexit', '-p', "-"],
                                  cwd=repopath, stdout=subprocess.PIPE, preexec_fn=self.set_death_signal_int)
        self.http_pid = self.f.pid
        while True:
            if self.f is not None:
                break
        self.monitor()

    def stop(self):
        os.kill(self.http_pid, signal.SIGQUIT)
