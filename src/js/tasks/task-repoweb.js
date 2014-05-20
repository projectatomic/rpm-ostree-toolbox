// -*- indent-tabs-mode: nil; tab-width: 2; -*-
// Copyright (C) 2013,2014 Colin Walters <walters@verbum.org>
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
const OSTree = imports.gi.OSTree;
const Format = imports.format;

const GSystem = imports.gi.GSystem;

const Builtin = imports.builtin;
const ArgParse = imports.argparse;
const Task = imports.task;
const ProcUtil = imports.procutil;
const BuildUtil = imports.buildutil;
const LibQA = imports.libqa;
const JsonUtil = imports.jsonutil;
const JSUtil = imports.jsutil;
const GuestFish = imports.guestfish;

const TaskRepoweb = new Lang.Class({
    Name: 'TaskRepoweb',
    Extends: Task.Task,

    TaskDef: {
        TaskName: "repoweb",
        TaskAfter: ['build']
    },

    MAXDEPTH: 100,

    DefaultParameters: { },
    execute: function(cancellable) {
	      this._repoPath = this.workdir.get_child('repo');
	      this._repoWebPath = this.workdir.get_child('repoweb-data');

        GSystem.file_ensure_directory(this._repoWebPath, true, cancellable);

        this._repo = new OSTree.Repo({ path: this._repoPath });
        this._repo.open(cancellable);
        
        let [,allRefs] = this._repo.list_refs(null, cancellable);
        let allRefsCopy = {};

        for (let refName in allRefs) {
            let revision = allRefs[refName];
            allRefsCopy[refName] = revision;
            print("Generating history for " + refName);
            this._generateHistoryFor(refName, revision, 0, cancellable);
        }
        JsonUtil.writeJsonFileAtomic(this._repoWebPath.get_child('refs.json'), { 'refs': allRefsCopy }, cancellable);
    },
});
