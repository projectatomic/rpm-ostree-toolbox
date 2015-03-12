#!/usr/bin/env python
# Copyright (C) 2015 Colin Walters <walters@verbum.org>
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

import logging
import os
import json
import subprocess
import sys

from gi.repository import GLib, Gio, OSTree

class RpmOstreeComposeRepo(object):
    """Class with various utility functions for doing compose/rel-eng
    operations.
    """

    def __init__(self, repopath):
        self.repopath = repopath
        self.repo = OSTree.Repo.new(Gio.File.new_for_path(self.repopath))
        self.repo.open(None)

    def delete_commits_with_key(self, ref, key):
        """Delete any commits that have @key as a detached metadata string.
        This is useful before doing a staging commit to ensure one is
        not shipping intermediate history.
        """

        # Note we require at least one 
        [_,rev] = self.repo.resolve_rev(ref, True)
        if rev is None:
            logging.info("No previous commit")
            return

        commit = None
        iter_rev = rev
        while True:
            _,commit = self.repo.load_variant(OSTree.ObjectType.COMMIT, iter_rev)
            _,metadata = self.repo.read_commit_detached_metadata(iter_rev, None)
            if (metadata is not None and metadata.unpack().get(key)):
                iter_rev = OSTree.commit_get_parent(commit)
                if iter_rev is None:
                    logging.error("Found a staging commit but no parent?")
                # skip this commit
                continue   
            else:
                break

        if iter_rev != rev:
            # We have commits to delete
            
            logging.info("Resetting {0} to {1}".format(ref, iter_rev))
            self.repo.set_ref_immediate(None, ref, iter_rev, None)
            
            # Now do a prune
            _,nobjs,npruned,objsize = self.repo.prune(OSTree.RepoPruneFlags.REFS_ONLY, -1, None)
            if npruned == 0:
                print "No unreachable objects"
            else:
                fmtsize = GLib.format_size_full(objsize, 0)
                logging.info("Deleted {0} objects, {1} freed".format(npruned, fmtsize))
        else:
            logging.info("No staging commits to prune")

    def compose_process(self, treefile, version=None, stdout=None, stderr=None):
        """Currently a thin wrapper for subprocess."""
        treedata = json.load(open(treefile))
        argv = ['rpm-ostree', 'compose', '--repo=' + self.repopath, 'tree']
        if version is not None:
            argv.append('--add-metadata-string=version=' + version)
        argv.append(treefile)
        subprocess.check_call(argv, stdout=stdout, stderr=stderr)
        [_,rev] = self.repo.resolve_rev(treedata['ref'], True)
        return rev
