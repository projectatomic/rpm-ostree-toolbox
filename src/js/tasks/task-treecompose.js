// Copyright (C) 2011,2013,2014 Colin Walters <walters@verbum.org>
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

const Task = imports.task;
const Params = imports.params;
const FileUtil = imports.fileutil;
const ProcUtil = imports.procutil;
const JSUtil = imports.jsutil;
const StreamUtil = imports.streamutil;
const JsonUtil = imports.jsonutil;
const Snapshot = imports.snapshot;
const BuildUtil = imports.buildutil;
const Vcs = imports.vcs;

const TaskTreeCompose = new Lang.Class({
    Name: "TaskTreeCompose",
    Extends: Task.Task,

    TaskDef: {
        TaskName: "treecompose",
    },

    DefaultParameters: {treefile: null},

    BuildState: { 'failed': 'failed',
		  'successful': 'successful',
		  'unchanged': 'unchanged' },

    execute: function(cancellable) {
	let argv = ['rpm-ostree'];

	let treefilePath = Gio.File.new_for_path(this.parameters.treefile);
	JsonUtil.writeJsonFileAtomic(treefilePath, treefileData, cancellable);
	argv.push.apply(argv, ['treecompose', treefilePath.get_path()]);
	print("Running: " + argv.map(GLib.shell_quote).join(' '));
	let procContext = new GSystem.SubprocessContext({ argv: argv });
	let proc = new GSystem.Subprocess({ context: procContext });
	proc.init(cancellable);
	proc.wait_sync_check(cancellable);
    }
});
