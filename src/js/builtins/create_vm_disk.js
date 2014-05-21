// -*- indent-tabs-mode: nil; tab-width: 2; -*-
// Copyright (C) 2013 Colin Walters <walters@verbum.org>
//
// This library is free software; you can redistribute it and/or
// modify it under the terms of the GNU Lesser General Public
// License as published by the Free Software Foundation; either
// version 2 of the License, or (at your option) any later version.
//
// This library is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
// Lesser General Public License for more details.
//
// You should have received a copy of the GNU Lesser General Public
// License along with this library; if not, write to the
// Free Software Foundation, Inc., 59 Temple Place - Suite 330,
// Boston, MA 02111-1307, USA.

const GLib = imports.gi.GLib;
const Gio = imports.gi.Gio;
const Lang = imports.lang;
const Format = imports.format;

const GSystem = imports.gi.GSystem;
const OSTree = imports.gi.OSTree;

const Builtin = imports.builtin;
const ArgParse = imports.argparse;
const ProcUtil = imports.procutil;
const LibQA = imports.libqa;
const GuestFish = imports.guestfish;

const CreateVmDisk = new Lang.Class({
    Name: 'CreateVmDisk',
    Extends: Builtin.Builtin,

    DESCRIPTION: "Generate a qcow2 disk image",

    _init: function() {
        this.parent();
        this.parser.addArgument('repo');
        this.parser.addArgument('osname');
        this.parser.addArgument('ref');
        this.parser.addArgument('diskpath');
    },

    execute: function(args, loop, cancellable) {
        let repoPath = Gio.File.new_for_path(args.repo);
        let repo = new OSTree.Repo({ path: repoPath });
        let [,rev] = repo.resolve_rev(args.ref, false);
        let path = Gio.File.new_for_path(args.diskpath);
        if (path.query_exists(null))
            throw new Error("" + path.get_path() + " exists");
        let tmppath = path.get_parent().get_child(path.get_basename() + '.tmp');
        GSystem.shutil_rm_rf(tmppath, cancellable);
        LibQA.createDisk(tmppath, cancellable);
        let mntdir = Gio.File.new_for_path('mnt');
        GSystem.file_ensure_directory(mntdir, true, cancellable);
        let gfmnt = new GuestFish.GuestMount(tmppath, { partitionOpts: LibQA.DEFAULT_GF_PARTITION_OPTS,
                                                            readWrite: true });
        gfmnt.mount(mntdir, cancellable);
        try {
            let osname = args['osname'];
            LibQA.pullDeploy(mntdir, repoPath, osname, args.ref, rev, null,
                             cancellable, { addKernelArgs: [] });
            print("Doing initial labeling");
            ProcUtil.runSync(['ostree', 'admin', '--sysroot=' + mntdir.get_path(),
                              'instutil', 'selinux-ensure-labeled',
		                          mntdir.get_path(),
		                          ""],
		                         cancellable,
		                         { logInitiation: true });
        } finally {
            gfmnt.umount(cancellable);
        }
        GSystem.file_rename(tmppath, path, cancellable);
        print("Created: " + path.get_path());
    }
});
