// Copyright (C) 2011 Colin Walters <walters@verbum.org>
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

const Gio = imports.gi.Gio;
const Lang = imports.lang;
const GSystem = imports.gi.GSystem;

const Task = imports.task;
const ProcUtil = imports.procutil;
const JsonUtil = imports.jsonutil;
const Snapshot = imports.snapshot;
const Vcs = imports.vcs;

const TaskResolve = new Lang.Class({
    Name: "TaskResolve",
    Extends: Task.Task,

    TaskDef: {
        TaskName: "resolve",
    },

    DefaultParameters: {treefiles: []},

    execute: function(cancellable) {
        let treefiles = this.parameters.treefiles;
	if (treefiles.length == 0)
	    throw new Error("No treefiles specified");

	}

    }
});
