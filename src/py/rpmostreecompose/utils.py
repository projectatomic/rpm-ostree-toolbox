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
import posixpath
import urllib
from SimpleHTTPServer import SimpleHTTPRequestHandler
import SocketServer
import threading
import os
import signal
import ctypes
import urllib2

def fail_msg(msg):
    if False:
        raise Exception(msg)
    print >>sys.stderr, msg
    sys.exit(1)

def run_sync(args, **kwargs):
    """Wraps subprocess.check_call(), logging the command line too."""
    log("Running: %s" % (subprocess.list2cmdline(args), ))
    subprocess.check_call(args, **kwargs)

def log(msg):
    "Print to standard output and flush it"
    sys.stdout.write(msg)
    sys.stdout.write('\n')
    sys.stdout.flush()

class ThreadedTCPServer(SocketServer.ThreadingMixIn, SocketServer.TCPServer):
    pass

class RequestHandler(SimpleHTTPRequestHandler):
    def translate_path(self, path):
        # Copy of python's, but using server._cwd instead of os.getcwd()
        # abandon query parameters
        path = path.split('?',1)[0]
        path = path.split('#',1)[0]
        # Don't forget explicit trailing slash when normalizing. Issue17324
        trailing_slash = path.rstrip().endswith('/')
        path = posixpath.normpath(urllib.unquote(path))
        words = path.split('/')
        words = filter(None, words)
        path = self.server._cwd  # HACKED HERE
        for word in words:
            if os.path.dirname(word) or word in (os.curdir, os.pardir):
                # Ignore components that are not a simple file/directory name
                continue
            path = os.path.join(path, word)
        if trailing_slash:
            path += '/'
        return path

class TemporaryWebserver(object):
    """ This class is used to control a temporary webserver which is used
    by the installer and imagefactory rpm-ostree-toolbox subcommands to get
    content from the from the host to the builds
    """

    def start(self, repopath):
        self.httpd = SocketServer.ThreadingTCPServer(("", 0), RequestHandler)
        self.httpd._cwd = repopath
        server_thread = threading.Thread(target=self.httpd.serve_forever)
        server_thread.daemon = True
        server_thread.start()
        return self.httpd.server_address[1]

    def stop(self):
        del self.httpd
