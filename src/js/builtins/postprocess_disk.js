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
const JsonUtil = imports.jsonutil;
const LibQA = imports.libqa;
const GuestFish = imports.guestfish;

const PostprocessDisk = new Lang.Class({
    Name: 'PostprocessDisk',
    Extends: Builtin.Builtin,

    DESCRIPTION: "Perform a series of postprocessing steps on the deployment in a disk image",

    _init: function() {
        this.parent();
        this.parser.addArgument('diskpath');
        this.parser.addArgument('postscript');
    },

    _ensureLink: function(path, dest, cancellable) {
        if (path.query_file_type(Gio.FileQueryInfoFlags.NOFOLLOW_SYMLINKS, null) != Gio.FileType.UNKNOWN)
            return;
        path.make_symbolic_link(dest, cancellable);
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

                print("systemctlenable(" + unit + ")");
                this._ensureLink(linkSrc, usrLibSystemdPath + unit, null);
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

                print("systemctlmask(" + unit + ")");
                this._ensureLink(linkSrc, '/dev/null', null);
            }
        },

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
            let usrSbinPath = dir.resolve_relative_path('usr/sbin/' + script);
            contents = GSystem.file_load_contents_utf8(this._datadir.resolve_relative_path(script), null);
            usrSbinPath.replace_contents(contents, null, false, 0, null);
            GSystem.file_chmod(usrSbinPath, 493, null);

            let usrLibSystemdSystemPath = dir.resolve_relative_path('usr/lib/systemd/system/' + unit);
            contents = GSystem.file_load_contents_utf8(this._datadir.resolve_relative_path(unit), null);
            usrLibSystemdSystemPath.replace_contents(contents, null, false, 0, null);

            print("injectservice(" + data.unit + "," + data.script + ")");
        },

        // Add a kernel argument
        appendkernelargs: function(data, dir, params) {
            let bootconfig = params.deployment.get_bootconfig();
            let optString = bootconfig.get("options");
            let opts = optString.split(/ /g);
            opts.push.apply(opts, data.args);
            let argv = ['ostree', 'admin',
                        '--sysroot=' + params.mntdir.get_path(),
                        'instutil', 'set-kargs'];
            argv.push.apply(argv, opts);
            ProcUtil.runSync(argv, null, { logInitiation: true });
        }
    },

    execute: function(args, loop, cancellable) {
        let postscriptPath = Gio.File.new_for_path(args.postscript)

        this._datadir = postscriptPath.get_parent();

        let postscript = JsonUtil.loadJson(postscriptPath, cancellable);
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
                let name = cmd.name

                if (!name)
                    throw new Error("Command index " + i + " missing 'name'");
                
                let impl = this._commands[name];
                if (!impl)
                    throw new Error("No such command '" + cmd + "'");

                let params = {'deployment': deployment,
                              'mntdir':  mntdir};
                impl.bind(this)(cmd, deployDir, params);
            }

            ProcUtil.runSync(['ostree', 'admin', '--sysroot=' + mntdir.get_path(), 'instutil', 'selinux-ensure-labeled'], cancellable, { logInitiation: true });
        } finally {
            gfmnt.umount(cancellable);
        }
    }
});
