// Copyright (C) 2012,2013 Colin Walters <walters@verbum.org>
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
const Params = imports.params;
const ProcUtil = imports.procutil;

const LibGuestfs = new Lang.Class({
    Name: 'LibGuestfs',

    _init: function(diskpath, params) {
	this._params = Params.parse(params, {useLockFile: true,
					     partitionOpts: ['-i'],
					     readWrite: false});
	this._diskpath = diskpath;
	this._readWrite = params.readWrite
	this._partitionOpts = params.partitionOpts;
	if (params.useLockFile) {
	    let lockfilePath = diskpath.get_parent().get_child(diskpath.get_basename() + '.guestfish-lock');
	    this._lockfilePath = lockfilePath;
	} else {
	    this._lockfilePath = null;
	}
    },

    _lock: function() {
	if (this._lockfilePath) {
	    let stream = this._lockfilePath.create(Gio.FileCreateFlags.NONE, cancellable);
	    stream.close(cancellable);
	}
    },

    _unlock: function() {
	if (this._lockfilePath != null) {
	    GSystem.file_unlink(this._lockfilePath, cancellable);
	}
    },

    _appendOpts: function(argv) {
	argv.push.apply(argv, ['-a', this._diskpath.get_path()]);
	if (this._readWrite)
	    argv.push('--rw');
	else
	    argv.push('--ro');
	argv.push.apply(argv, this._partitionOpts);
    }
});

const GuestFish = new Lang.Class({
    Name: 'GuestFish',
    Extends: LibGuestfs,

    run: function(input, cancellable) {
	this._lock();
	try {
	    let guestfishArgv = ['guestfish'];
	    this._appendOpts(guestfishArgv);
	    return ProcUtil.runProcWithInputSyncGetLines(guestfishArgv, cancellable, input);
	} finally {
	    this._unlock();
	}
    }
});

const GuestMount = new Lang.Class({
    Name: 'GuestMount',
    Extends: LibGuestfs,

    mount: function(mntdir, cancellable) {
	this._lock();
	try {
	    this._mntdir = mntdir;
	    this._mountPidFile = mntdir.get_parent().get_child(mntdir.get_basename() + '.guestmount-pid');

	    if (this._mountPidFile.query_exists(null))
		throw new Error("guestfish pid file exists: " + this._mountPidFile.get_path());

	    let guestmountArgv = ['guestmount', '-o', 'allow_root',
				  '--pid-file', this._mountPidFile.get_path()];
	    this._appendOpts(guestmountArgv);
	    guestmountArgv.push(mntdir.get_path());
	    print('Mounting ' + mntdir.get_path() + ' : ' + guestmountArgv.join(' '));
            let context = new GSystem.SubprocessContext({ argv: guestmountArgv });
            let proc = new GSystem.Subprocess({ context: context });
	    proc.init(cancellable);

            // guestfish daemonizes, so this process will exit, and
	    // when it has, we know the mount is ready.  If there was
	    // a way to get notified instead of this indirect fashion,
	    // we'd do that.
	    proc.wait_sync_check(cancellable);

	    this._mounted = true;
	} catch (e) {
	    this._unlock();
	}
    },

    umount: function(cancellable) {
	if (!this._mounted)
	    return;

	ProcUtil.runSync(['guestunmount', '-v', this._mntdir.get_path()], cancellable,
			 { logInitiation: true });
	
	this._mounted = false;
	this._unlock();
    },
});
