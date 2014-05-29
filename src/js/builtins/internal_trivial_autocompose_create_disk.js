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

const GSystem = imports.gi.GSystem;

const Builtin = imports.builtin;
const JsonUtil = imports.jsonutil;
const BuildUtil = imports.buildutil;
const ProcUtil = imports.procutil;
const VersionedDir = imports.versioneddir;

const InternalTrivialAutocomposeCreateDisk = new Lang.Class({
    Name: 'InternalTrivialAutocomposeCreateDisk',
    Extends: Builtin.Builtin,

    DESCRIPTION: "Create disk images",

    _init: function() {
	this.parent();

        this.parser.addArgument('repo', { action: 'store' });
        this.parser.addArgument('taskdir', { action: 'store' });
        this.parser.addArgument('osname', { action: 'store' });
        this.parser.addArgument('ref', { action: 'store' });
        this.parser.addArgument('rev', { action: 'store' });
        this.parser.addArgument('name', { action: 'store' });
    },

    execute: function(args, loop, cancellable) {
	let repoPath = Gio.File.new_for_path(args.repo);
	let taskdir = Gio.File.new_for_path(args.taskdir);
	let osname = args.osname;
	let ref = args.ref;
	let rev = args.rev;
	let name = args.name;
	let refUnix = name.replace('/', '_');

	print("Checking disk state for " + ref + " (" + name + ") => " + rev);

	let imagesTmpDir = taskdir.get_child('images');
	GSystem.file_ensure_directory(imagesTmpDir.get_parent(), true, cancellable);

	let imageName = refUnix + '.qcow2';
	let imageTarget = imagesTmpDir.get_child(imageName);
	let imageTargetCloud = imagesTmpDir.get_child('cloud').get_child(imageName);
	let imageTargetVagrantDir = imagesTmpDir.get_child('vagrant');
	let imageTargetVagrantQemu = imageTargetVagrantDir.resolve_relative_path('libvirt/' + refUnix + '.qcow2');

	if (imageTargetVagrantQemu.query_exists(null)) {
	    print("Already have disk " + imageTargetVagrantQemu.get_path());
	    return;
	} else {
	    // Base qcow2
	    GSystem.file_ensure_directory(imageTarget.get_parent(), true, cancellable);
	    let argv = ['rpm-ostree-toolbox', 'create-vm-disk'];
	    argv.push.apply(argv, [
		repoPath.get_path(),
		osname,
		ref,
		imageTarget.get_path()]);
	    ProcUtil.runSync(argv, cancellable, { logInitiation: true });

	    // Cloud disk
	    GSystem.file_ensure_directory(imageTargetCloud.get_parent(), true, cancellable);
	    imageTarget.copy(imageTargetCloud, 0, cancellable, null, null);
	    argv = ['rpm-ostree-toolbox', 'prep-cloud-disk'];
	    argv.push(imageTargetCloud.get_path());
	    ProcUtil.runSync(argv, cancellable, { logInitiation: true });
	    ProcUtil.runSync(['xz', imageTargetCloud.get_path()], cancellable, { logInitiation: true });

	    // Vagrant disk
	    GSystem.file_ensure_directory(imageTargetVagrantQemu.get_parent(), true, cancellable);
	    imageTarget.copy(imageTargetVagrantQemu, 0, cancellable, null, null);
	    argv = ['rpm-ostree-toolbox', 'prep-vagrant-disk'];
	    argv.push(imageTargetVagrantQemu.get_path());
	    ProcUtil.runSync(argv, cancellable, { logInitiation: true });
	    ProcUtil.runSync(['xz', imageTargetVagrantQemu.get_path()], cancellable, { logInitiation: true });
	}

	ProcUtil.runSync(['xz', imageTarget.get_path()], cancellable, { logInitiation: true });

	print("Complete!");
    }
});
