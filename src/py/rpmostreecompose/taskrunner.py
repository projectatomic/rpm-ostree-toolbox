#!/usr/bin/env python
# Copyright (C) 2014 Colin Walters <walters@verbum.org>
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2 of the License, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the
# Free Software Foundation, Inc., 59 Temple Place - Suite 330,
# Boston, MA 02111-1307, USA.

import json
import os
import re
import logging
import argparse
import stat
import sys

from gi.repository import GLib,Gio,GSystem

from .versioneddir import VersionedDir

class TaskDef(object):
    def __init__(self, name, cmdline):
        self.name = name
        self.cmdline = cmdline

class Task(object):
    def __init__(self, taskdef, path):
        self.taskdef = taskdef
        self.path = path
        self.proc = None
    
    def spawn(self):
        print "%r" % (self.taskdef.cmdline, )
        ctx = GSystem.SubprocessContext(argv=self.taskdef.cmdline)
        ctx.set_cwd(self.path)
        ctx.set_stdout_file_path(os.path.join(self.path, 'output.txt'))
        ctx.set_stderr_disposition(GSystem.SubprocessStreamDisposition.STDERR_MERGE)
        self.starttime = GLib.get_monotonic_time()
        self.proc = GSystem.Subprocess.new(ctx, None)
        self.endtime = None

class TaskRunner(object):

    def __init__(self, path):
        self.path = path
        self._taskspath = os.path.join(self.path, 'tasks')
        self._taskdefs = {}
        self._taskversions = {}
        self._active = {}
        self._queued = set()
        self._task_queuetimes = {}
        self._inbox_monitor = None

        self._load_taskdefs()

    def _load_taskdefs(self):
        for child in os.listdir(self._taskspath):
            taskdef_path = os.path.join(self._taskspath, child, 'taskdef.conf')
            if not os.path.exists(taskdef_path):
                logging.warn("Task directory '%s' exists but has no taskdef.conf",
                             os.path.dirname(taskdef_path))
                continue
            logging.info("Loading: " + taskdef_path)
            keyfile = GLib.KeyFile.new()
            GLib.KeyFile.load_from_file(keyfile,taskdef_path, 0)
            execvalue = keyfile.get_value('Task', 'Exec')
            _,argv = GLib.shell_parse_argv(execvalue)
            self.define(child, argv)

    def define(self, taskname, cmdline):
        self._taskdefs[taskname] = TaskDef(taskname, cmdline)

    def _on_task_exited(self, proc, result, task):
        _,estatus = proc.wait_finish(result)
        task.endttime = GLib.get_monotonic_time()
        try:
            GLib.spawn_check_exit_status(estatus)
            success = True
            logging.info("task %s exited successfully" % (task.taskdef.name, ))
        except Exception, e:
            logging.info("task %s exited with error: %s" % (task.taskdef.name, str(e)))
            success = False

        taskname = task.taskdef.name

        del self._active[taskname]

        try:
            self._queued.remove(taskname)
            was_queued = True
        except KeyError, e:
            was_queued = False

        if was_queued:
            self.trigger(taskname)

    def trigger(self, taskname):
        taskdef = self._taskdefs[taskname]
        if taskname in self._queued:
            logging.info("task already queued: " + taskname)
            return
        if taskname in self._active:
            logging.info("queued task: " + taskname)
            self._queued.add(taskname)
            return

        taskdir = os.path.join(self._taskspath, taskname)
        if not taskname in self._taskversions:
            self._taskversions[taskname] = VersionedDir(taskdir)
        versions = self._taskversions[taskname]

        path = versions.allocate()
        verpath = os.path.relpath(path, self._taskspath)
        task = Task(taskdef, path)
        task.spawn()
        logging.info("task: %s running; pid=%d" % (verpath, task.proc.get_pid()))
        task.proc.wait(None, self._on_task_exited, task)
        self._active[taskname] = task

    def _on_taskdir_changed(self, mon, src, other, event):
        logging.debug("monitor dir changed")
        path = src.get_path()
        child = os.path.basename(path)
        if not child in self._taskdefs:
            logging.warn("Unknown task '%s' in monitored dir %s"  % (child, path, ))
            return
        try:
            mtime = os.stat(path)[stat.ST_MTIME]
        except OSError, e:
            return
        if child not in self._task_queuetimes:
            changed = True
        else:
            last_mtime = self._task_queuetimes[child]
            changed = last_mtime != mtime
        if changed:
            logging.info("Task '%s' queue notification"  % (child, ))
            self._task_queuetimes[child] = mtime
            self.trigger(child)
        else:
            logging.info("Task '%s' is unchanged" % (child, ))

    def monitor_taskdir(self, path):
        self._inbox_path = Gio.File.new_for_path(path)
        self._inbox_monitor = self._inbox_path.monitor_directory(0, None)
        logging.info("Monitoring: " + path)
        self._inbox_monitor.connect('changed', self._on_taskdir_changed)


def main():
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description='Run tasks')
    parser.add_argument('-d', '--root', type=str, default=os.getcwd(), help='Path to root')
    parser.add_argument('inbox', type=str, help='Monitor this directory for tasks')
    args = parser.parse_args()
    runner = TaskRunner(args.root)
    runner.monitor_taskdir(args.inbox)
    mainctx = GLib.MainContext.default()
    logging.info("Awaiting events")
    while True:
        mainctx.iteration(True)
        
if __name__ == '__main__':
    main()
