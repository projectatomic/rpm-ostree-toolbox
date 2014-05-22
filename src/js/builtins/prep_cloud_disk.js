// -*- indent-tabs-mode: nil; tab-width: 2; -*-
// Copyright (C) 2014 Colin Walters <walters@verbum.org>
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

const PrepCloudDisk = new Lang.Class({
    Name: 'PrepCloudDisk',
    Extends: Builtin.Builtin,

    DESCRIPTION: "Prepare a disk image for OpenStack/EC2",

    _init: function() {
        this.parent();
        this.parser.addArgument('diskpath');
    },

    execute: function(args, loop, cancellable) {
        let tmpdir = Gio.File.new_for_path(GLib.dir_make_tmp('rpmostreetoolbox.XXXXXX'));
        let mntdir = tmpdir.get_child('mnt');
        GSystem.file_ensure_directory(mntdir, true, cancellable);
        let gfmnt = new GuestFish.GuestMount(Gio.File.new_for_path(args.diskpath),
                                             { partitionOpts: LibQA.DEFAULT_GF_PARTITION_OPTS,
                                               readWrite: true });
        gfmnt.mount(mntdir, cancellable);
        try {
            let sysroot = OSTree.Sysroot.new(mntdir);
            sysroot.load(null);
            let deployments = sysroot.get_deployments();
            let deployment = deployments[0];
            let deployDir = sysroot.get_deployment_directory(deployment);

            let agentSvcName = 'min-cloud-agent.service';

            let serviceRelpath = 'usr/lib/systemd/system/' + agentSvcName;
            let multiUserWantsPath = 'etc/systemd/system/multi-user.target.wants/' + agentSvcName;
            deployDir.resolve_relative_path(multiUserWantsPath).make_symbolic_link('/' + serviceRelpath, cancellable);
        } finally {
            gfmnt.umount(cancellable);
        }
    }
});
