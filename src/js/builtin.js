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
const JsonUtil = imports.jsonutil;
const ArgParse = imports.argparse;
const BuildUtil = imports.buildutil;

const Builtin = new Lang.Class({
    Name: 'Builtin',

    DESCRIPTION: null,

    _init: function() {
	this.parser = new ArgParse.ArgumentParser(this.DESCRIPTION);
	this._workdirInitialized = false;
    },

    main: function(argv, loop, cancellable) {
	let args = this.parser.parse(argv);
	this.execute(args, loop, cancellable);
    }
});
