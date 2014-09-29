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

// The autobuilder is designed to loop on an input autobuilder.json
// file which has a set of input treefiles, disk configuration, and
// other variables such as a poll timeout and whether or not to run
// "git pull -r" on its configuration.

const GLib = imports.gi.GLib;
const Gio = imports.gi.Gio;
const Lang = imports.lang;

const GSystem = imports.gi.GSystem;
const OSTree = imports.gi.OSTree;

const Builtin = imports.builtin;
const JsonUtil = imports.jsonutil;
const BuildUtil = imports.buildutil;
const ProcUtil = imports.procutil;
const VersionedDir = imports.versioneddir;

const TrivialAutocompose = new Lang.Class({
    Name: 'TrivialAutocompose',
    Extends: Builtin.Builtin,

    DESCRIPTION: "Poll input yum repositories and compose trees and disk images",

    _init: function() {
	this.parent();

        this.parser.addArgument('config', { action: 'store' });
        this.parser.addArgument('--disks', { action: 'storeTrue' });
    },

    execute: function(args, loop, cancellable) {
	this._workdir = Gio.File.new_for_path(GLib.get_current_dir());

        this._composeDir = new VersionedDir.VersionedDir(this._workdir.get_child('tasks/treecompose'));
        this._imagesDir = new VersionedDir.VersionedDir(this._workdir.get_child('tasks/images'));

	this._configPath = Gio.File.new_for_path(args.config);
	this._config = JsonUtil.loadJson(this._configPath, cancellable);

	if (!this._config['poll-timeout'])
	    this._config['poll-timeout'] = 60 * 60;
	print("Will poll input pkg repositories every " + this._config['poll-timeout'] + " seconds");

	this._composeTasks = {};
	this._imageTasks = {};

	let treefiles = this._config.treefiles;
	for (let i = 0; i < treefiles.length; i++) {
	    let tf = treefiles[i];
	    this._composeTasks[tf] = null;
	    print("Added treefile: " + tf);
	}

        this._repo = new OSTree.Repo({ path: this._workdir.get_child('repo') });
        this._repo.open(cancellable);

	this._composeNeeded = false;
	this._composeTimeoutId = GLib.idle_add(GLib.PRIORITY_DEFAULT,
					       this._onComposeTimeout.bind(this));

	this._createDisksNeeded = false;
	if (args.disks) {
	    this._createDisksNeeded = true;
	    this._runCreateDisks();
	}

	loop.run();
    },

    _checkTaskSetDone: function(taskSet) {
	let allDone = true;
	let success = true;
	for (let othertf in taskSet) {
	    let task = taskSet[othertf];
	    if (task == null)
		continue;
	    if (task.proc != null) {
		allDone = false;
		break;
	    }
	    if (!task.success)
		success = false;
	}
	return [allDone, success];
    },

    _clearTaskSet: function(taskSet) {
	let changed = false;
	for (let tf in taskSet) {
	    let task = taskSet[tf];
	    if (task === null)
		continue;
	    if (task.changed)
		changed = true;
	    taskSet[tf] = null;
	}
	return changed;
    },

    _readSwappedLink: function(path, cancellable) {
	let currentInfo = null;
	try {
            currentInfo = path.query_info('standard::symlink-target', Gio.FileQueryInfoFlags.NOFOLLOW_SYMLINKS, cancellable);
	} catch (e) {
            if (e.matches(Gio.IOErrorEnum, Gio.IOErrorEnum.NOT_FOUND))
		return 0;
	    else
		throw e;
	}
	let bn = currentInfo.get_symlink_target();
	let last = bn[bn.length-1];
	if (last == '0')
	    return 0;
	else if (last == '1')
	    return 1;
	else
	    throw new Error("Invalid swapped link: " + path.get_path());
    },

    _atomicSymlinkSwap: function(linkPath, newTarget, cancellable) {
	let parent = linkPath.get_parent();
	let tmpLinkPath = parent.get_child('current-new.tmp');
	GSystem.shutil_rm_rf(tmpLinkPath, cancellable);
	let relpath = GSystem.file_get_relpath(parent, newTarget);
	tmpLinkPath.make_symbolic_link(relpath, cancellable);
	GSystem.file_rename(tmpLinkPath, linkPath, cancellable);
    },

    _onImageExited: function(proc, result, tf) {
	let cancellable = null;
	let [success, errmsg] = ProcUtil.asyncWaitCheckFinish(proc, result);

	print("Image creation subtask " + tf + ": " + (success ? "succeeded" : "failed"));
	if (!success)
	    print(errmsg);

	let task = this._imageTasks[tf];

	task.proc = null;
	task.success = success;

	let [allDone, success] = this._checkTaskSetDone(this._imageTasks);

	if (allDone) {
	    if (success) {
		print("Image creation " + this._imagesVersion + " complete");
		let imagesAutolink = this._workdir.resolve_relative_path('images/auto');
		let imagesAutoCurrentVersion = this._readSwappedLink(imagesAutolink, cancellable);
		let imagesAutoNewVersion = imagesAutoCurrentVersion == 1 ? 0 : 1;
		let imagesCurrentDir = this._workdir.resolve_relative_path('images/auto.' + imagesAutoCurrentVersion);
		let imagesTmpDir = this._workdir.resolve_relative_path('images/auto.' + imagesAutoNewVersion);

		GSystem.shutil_rm_rf(imagesTmpDir, cancellable);
		GSystem.file_ensure_directory(imagesTmpDir, true, cancellable);
		
		for (let tf in this._imageTasks) {
		    let task = this._imageTasks[tf];
		    if (task === null)
			continue;
		    let targetResultdir = imagesTmpDir.get_child(task.name);
		    GSystem.file_ensure_directory(targetResultdir.get_parent(), true, cancellable);
		    print("Renaming " + task.resultdir.get_path() + " => " + targetResultdir.get_path());
		    ProcUtil.runSync(['mv', task.resultdir.get_path(), targetResultdir.get_path()], cancellable);
		}
		
		this._atomicSymlinkSwap(imagesAutolink, imagesTmpDir, cancellable); 
	    }
	    this._clearTaskSet(this._imageTasks);
	}
    },

    _runCreateDisks: function() {
	let cancellable = null;

	let composeRevs = {};
	for (let tf in this._composeTasks) {
	    let tfPath = this._configPath.get_parent().get_child(tf);
	    let tfData = JsonUtil.loadJson(tfPath, cancellable);
	    let ref = tfData.ref;
	    let [,rev] = this._repo.resolve_rev(ref, true);
	    composeRevs[ref] = rev;
	}

	let previousVersion = this._imagesDir.currentVersion(cancellable);
        this._imagesPath = this._imagesDir.allocateNewVersion(cancellable);
        this._imagesVersion = this._imagesDir.pathToVersion(this._imagesPath);

	print("Beginning images");
	this._createDisksNeeded = false;
	
	let commonPrefix = null;
	for (let ref in composeRevs) {
	    if (commonPrefix == null) {
		let slash = ref.lastIndexOf('/');
		if (slash)
		    commonPrefix = ref.substring(0, slash+1);
	    } else {
		for (let i = 0; i < ref.length && i < commonPrefix.length; i++) {
		    if (ref[i] != commonPrefix[i])
			commonPrefix = commonPrefix.substring(0, i);
		}
	    }
	}

	for (let tf in this._composeTasks) {
	    let basename = tf.replace('.json', '');

	    if (!this._config.disks || !this._config.disks[basename]) {
		print("No disk images configured for " + tf);
		continue;
	    }

	    let tfPath = this._configPath.get_parent().get_child(tf);
	    let tfData = JsonUtil.loadJson(tfPath, cancellable);
	    let ref = tfData.ref;
	    let rev = composeRevs[ref];
	    let osname = ref.substring(0, ref.indexOf('/')); 
	    let name = osname + '-' + ref.substring(commonPrefix.length);

	    let imageWorkDir = this._imagesPath.get_child('work-' + name);
	    GSystem.shutil_rm_rf(imageWorkDir, cancellable);
	    GSystem.file_ensure_directory(imageWorkDir, true, cancellable);

	    let argv = [GLib.getenv("OSTBUILD_DATADIR") + '/trivial-autocompose-create-disks.sh',
			this._workdir.get_child('repo').get_path(),
			imageWorkDir.get_path(),
			osname,
			ref,
			rev,
			name];
	    let context = new GSystem.SubprocessContext({ argv: argv });
	    context.set_cwd(imageWorkDir.get_path());
	    let outPath = imageWorkDir.get_child('output.txt');
	    context.set_stdout_file_path(outPath.get_path());
	    context.set_stderr_disposition(GSystem.SubprocessStreamDisposition.STDERR_MERGE);
	    print("Starting: " + context.argv.map(GLib.shell_quote).join(' '));

	    let proc = new GSystem.Subprocess({ context: context });
	    proc.init(cancellable);
	    this._imageTasks[tf] = { 'proc': proc,
				     'success': null,
				     'name': name,
				     'resultdir': imageWorkDir.get_child('images'),
				     'rev': rev,
				     'changed': null
				   };
	    proc.wait(cancellable, Lang.bind(this, this._onImageExited, tf));
	}
    },

    _onComposeExited: function(proc, result, tf) {
	let [success, errmsg] = ProcUtil.asyncWaitCheckFinish(proc, result);

	print("Compose " + tf + ": " + (success ? "succeeded" : "failed"));
	if (!success)
	    print(errmsg);

	let task = this._composeTasks[tf];

	task.proc = null;
	task.success = success;

	if (success) {
	    let [,rev] = this._repo.resolve_rev(task.treefile.ref, true);
	    if (rev != task.rev) {
		print("Compose of " + task.treefile.ref + " is now " + rev);
		task.changed = true;
		task.rev = rev;
	    } else {
		print("Compose of " + task.treefile.ref + " is unchanged");
	    }
	}

	let [allDone, success] = this._checkTaskSetDone(this._composeTasks);
	if (allDone) {
	    let changed = this._clearTaskSet(this._composeTasks);
	    print("Compose " + this._composeVersion + " complete; changed=" + changed + " success=" + success);
	    if (this._composeNeeded) {
		this._runCompose();
	    } else {
		let mainCtx = GLib.MainContext.default();
		let timeoutSource = mainCtx.find_source_by_id(this._composeTimeoutId);
		let readyTime = timeoutSource.get_ready_time() / GLib.USEC_PER_SEC;
		let currentMonotonicTime = GLib.get_monotonic_time() / GLib.USEC_PER_SEC;
		let deltaSecs = (readyTime - currentMonotonicTime);
		print("Next compose scheduled for " + deltaSecs + " seconds");
	    }
	    if (success && changed) {
		this._runCreateDisks();
	    }
	}
    },

    _onComposeTimeout: function() {
	this._composeTimeoutId = 0;
	let [composeDone, success] = this._checkTaskSetDone(this._composeTasks);
	if (!composeDone) {
	    this._composeNeeded = true;
	    print("Compose timeout expired but task is still running; will schedule after completion");
	} else {
	    print("Compose timeout expired");
	    this._runCompose();
	}
	this._composeTimeoutId = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT,
							  this._config['poll-timeout'],
							  this._onComposeTimeout.bind(this));
	return false;
    },

    _runCompose: function() {
	let cancellable = null;

	if (this._autoupdate_self){
	    ProcUtil.runSync(['git', 'pull', '-r'], cancellable,
			     { cwd: this._autoupdate_self })
	}

	let [composeDone, success] = this._checkTaskSetDone(this._composeTasks);
	if (!composeDone) {
	    print("Already running compose task: " + tf + " pid=" + task.proc.get_pid());
	    return;
	}

	let previousVersion = this._composeDir.currentVersion(cancellable);
        this._composePath = this._composeDir.allocateNewVersion(cancellable);
        this._composeVersion = this._composeDir.pathToVersion(this._composePath);

	print("Beginning compose");
	this._composeNeeded = false;

	for (let tf in this._composeTasks) {
	    let tfPath = this._configPath.get_parent().get_child(tf);
	    let tfData = JsonUtil.loadJson(tfPath, cancellable);
	    let ref = tfData.ref;

	    let argv = ['rpm-ostree', 'compose', 'tree',
			"--repo=" + this._workdir.get_child('repo').get_path(),
			"--cachedir=" + this._workdir.get_child('cache').get_path(),
			tfPath.get_path()];
	    let context = new GSystem.SubprocessContext({ argv: argv });
	    context.set_cwd(this._composePath.get_path());
	    let outPath = this._composePath.get_child('log-' + tf.replace('.json', '.txt'));
	    GSystem.shutil_rm_rf(outPath, cancellable);
	    context.set_stdout_file_path(outPath.get_path());
	    context.set_stderr_disposition(GSystem.SubprocessStreamDisposition.STDERR_MERGE);

	    let [,rev] = this._repo.resolve_rev(ref, true);

	    print("Starting: " + context.argv.map(GLib.shell_quote).join(' '));

	    let proc = new GSystem.Subprocess({ context: context });
	    proc.init(cancellable);
	    this._composeTasks[tf] = { 'proc': proc,
				       'treefile': tfData,
				       'success': null,
				       'rev': rev,
				       'changed': null
				     };
	    proc.wait(cancellable, Lang.bind(this, this._onComposeExited, tf));
	}
    }	
});
