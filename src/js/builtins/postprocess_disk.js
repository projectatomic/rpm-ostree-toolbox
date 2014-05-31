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

const PostProcessDisk = new Lang.Class({
    Name: 'PostprocessDisk',
    Extends: Builtin.Builtin,

    DESCRIPTION: "Perform a series of postprocessing steps on the deployment in a disk image",

    _init: function() {
        this.parent();
        this.parser.addArgument('diskpath');
        this.parser.addArgument('postscript');
    },

    _commands: {
        // Enable a systemd unit for multi-user.target (not default.target)
        systemctlenable: function(data, dir) {
            let units = data.units;
            if (!units)
                throw new Error("No 'units' specified for systemctlenable");
            let usrLibSystemdPath = '/usr/lib/systemd/system/';
            let multiUserWantsDir = dir.resolve_relative_path('etc/systemd/system/multi-user.target.wants');
            for (let i = 0; i < units.length; i++) {
                let unit = units[i];
                let linkSrc = multiUserWantsDir.get_child(unit);

                linkSrc.make_symbolic_link(usrLibSystemdPath + unit);
            }
        },

        // Mask a systemd unit
        systemctlmask: function(data, dir) {
            let units = data.units;
            if (!units)
                throw new Error("No 'units' specified for systemctlmask");
            let etcSystemdSystemPath = dir.resolve_relative_path('etc/systemd/system');
            for (let i = 0; i < units.length; i++) {
                let unit = units[i];
                let linkSrc = etcSystemdSystemPath.get_child(unit);

                linkSrc.make_symbolic_link('/dev/null');
            }
        }

        // Copy in a script from the host system to run in the target.
        // This is your best bet for performing more complex
        // provisioning inside the guest; you should set up your unit
        // so it's done once at boot.
        injectservice: function(data, dir) {
            let unit = data.unit;
            if (!unit)
                throw new Error("No 'unit' specified for injectservice");
            let script = data.script;
            if (!script)
                throw new Error("No 'script' specified for injectservice");

            let contents;
            let usrLibSystemdPath = dir.resolve_relative_path('usr/lib/systemd/system/' + unit);
            contents = GSystem.file_load_contents_utf8(this._datadir.resolve_relative_path(script), null);
            usrLibSystemdPath.replace_contents(contents, null, FALSE, 0, null);

            let etcSystemdSystemPath = dir.resolve_relative_path('etc/systemd/system/' + unit);
            contents = GSystem.file_load_contents_utf8(this._datadir.resolve_relative_path(unit), null);
            etcSystemdSystemPath.replace_contents(contents, null, FALSE, 0, null);
        }
    },

    execute: function(args, loop, cancellable) {
        let postscriptPath = Gio.File.new_for_path(args.postscript)

        this._datadir = postscriptPath.get_parent();

        let postscript = JsonUtil.loadJson(this._postscriptPath, cancellable);
        let commands = postscript.commands;
        if (!commands)
            throw new Error("No 'commands' found in postscript");

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

            for (let i = 0; i < commands.length; i++) {
                let cmd = commands[i];
                
                let impl = this._commands[cmd];
                if (!impl)
                    throw new Error("No such command '" + cmd "'");

                impl(cmd, deployDir);
            }

            ProcUtil.runSync(['ostree', 'admin', '--sysroot=' + mntdir.get_path(), 'instutil', 'selinux-ensure-labeled'], cancellable, { logInitiation: true });
        } finally {
            gfmnt.umount(cancellable);
        }
    }
});
