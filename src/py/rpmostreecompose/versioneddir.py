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
import sys

from gi.repository import GLib  # pylint: disable=no-name-in-module

class VersionedDir(object):

    def __init__(self, path):
        self.path = path
        self._latest = None
        self._numeric_re = re.compile(r'^(\d+)$')
        self._ymd_serial_version_re = re.compile(r'^(\d+)(\d\d)(\d\d)\.(\d+)$/')

        self._cache_latest()

    def _get_latest_in(self, path):
        largest = None
        for child in os.listdir(path):
            childpath = os.path.join(path, child)
            if not os.path.isdir(childpath):
                continue
            if not self._numeric_re.match(child):
                continue
            v = int(child)
            if largest is None or v > largest:
                largest = v
        return largest

    def _cache_latest(self):
        year = self._get_latest_in(self.path)
        if year is None:
            return
        monthdir = os.path.join(self.path, str(year))
        month = self._get_latest_in(monthdir)
        if month is None:
            return
        daydir = os.path.join(monthdir, '%02d' % month)
        day = self._get_latest_in(daydir)
        if day is None:
            return
        serialdir = os.path.join(daydir, '%02d' % day)
        serial = self._get_latest_in(serialdir)
        if serial is None:
            return
        self._latest = [year, month, day, serial]

    def allocate(self):
        current_time = GLib.DateTime.new_now_utc();
        [year, month, day] = [current_time.get_year(),
                              current_time.get_month(),
                              current_time.get_day_of_month()]
        if (self._latest is not None and
            self._latest[0] == year and
            self._latest[1] == month and
            self._latest[2] == day):
            newserial = self._latest[3] + 1
        else:
            newserial = 0
        path = os.path.join(self.path, str(year), '%02d' % month, '%02d' % day, str(newserial))
        os.makedirs(path)
        self._latest = [year, month, day, newserial]
        return path
