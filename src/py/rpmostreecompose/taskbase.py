#!/usr/bin/env python
# Copyright (C) 2014 Colin Walters <walters@verbum.org>, Andy Grimm <agrimm@redhat.com>
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
import sys
import tempfile
import argparse
import shutil
import subprocess
import distutils.spawn
from gi.repository import Gio, OSTree, GLib
import iniparse
from .utils import fail_msg

class TaskBase(object):
    ATTRS = [ 'workdir', 'rpmostree_cache_dir', 'pkgdatadir',
              'os_name', 'os_pretty_name',
              'tree_name', 'tree_file', 'arch', 'release', 'ref',
              'yum_baseurl', 'lorax_additional_repos',
              'lorax_exclude_packages',
              'local_overrides', 'http_proxy',
              'selinux', 'configdir', 'docker_os_name'
            ]


    def __init__(self, args, cmd, profile=None):
        self._repo = None
        self.args = args
        configfile = args.config
        assert profile is not None
        defaults = { 'workdir': None,
                     'pkgdatadir':  os.environ['OSTBUILD_DATADIR'],
                     'yum_baseurl': None,
                     'local_overrides': None,
                     'selinux': True
                   }

        if not os.path.isfile(configfile):
            fail_msg("No config file: " + configfile)
        settings = iniparse.ConfigParser()
        try: 
            settings.read(configfile)
        except ConfigParser.ParsingError as e:
            fail_msg("Error parsing your config file {0}: {1}".format(configfile, e.message))            

        self.outputdir = os.getcwd()
        self.ostree_repo = self.outputdir + '/repo'

        for attr in self.ATTRS:
            val = self.getConfigValue(attr, settings, profile, defValue=defaults.get(attr))
            print (attr, val)
            setattr(self, attr, val)

        release = getattr(self, 'release')
        # Check for configdir in attrs, else fallback to dir holding config
        if getattr(self, 'configdir') is None:
            setattr(self, 'configdir', os.path.dirname(os.path.realpath(configfile)))

        if self.tree_file is None:
            fail_msg("No tree file was provided")
        else:
            self.tree_file = os.path.join(self.configdir, self.tree_file)

        # Look for virtnetwork

        if 'virtnetwork' in args:
            self.virtnetwork = args.virtnetwork

        self.os_nr = "{0}-{1}".format(getattr(self, 'os_name'), getattr(self, 'release'))

        # Set kickstart file from args, else fallback to default
        if cmd == "imagefactory":
            if 'kickstart' in args and args.kickstart is not None:
                setattr(self, 'kickstart', args.kickstart)
            else:
                defks = "{0}.ks".format(self.os_nr)

                setattr(self, 'kickstart', '{0}'.format(os.path.join(
                    getattr(self, 'configdir'), defks)))
                if not os.path.exists(getattr(self, 'kickstart')):
                    fail_msg("No kickstart was passed with -k and {0} does not exist".format(getattr(self, 'kickstart')))

        # Set tdl from args, else fallback to default
        if cmd in ["imagefactory"] or ( cmd in ['installer'] and args.virt ):
            if 'tdl' in args and args.tdl is not None:
                setattr(self, 'tdl', args.tdl)
            else:
                deftdl = "{0}.tdl".format(self.os_nr)
                setattr(self, 'tdl', '{0}'.format(os.path.join(
                    getattr(self, 'configdir'), deftdl)))
                if not os.path.exists(getattr(self, 'tdl')):
                    fail_msg("No TDL file was passed with --tdl and {0} does not exist".format(getattr(self, 'tdl')))

        # Set name from args, else fallback to default
        if 'name' in args and args.name is not None:
            setattr(self, 'name', args.name)
        else:
            setattr(self, 'name', '{0}'.format(self.os_nr))

        if cmd == "installer":
            if not self.yum_baseurl and args.yum_baseurl == None:
                fail_msg("No yum_baseurl was provided in your config.ini or with installer -b.")

            # Set util_uuid
            self.util_uuid = args.util_uuid

            if not args.util_uuid and not args.util_tdl and args.virt:
                fail_msg ("You must provide a TDL for your utility image with --util_tdl")
            else:
                self.util_tdl = args.util_tdl

        if self.http_proxy:
            os.environ['http_proxy'] = self.http_proxy

        self.workdir_is_tmp = False
        if self.workdir is None:
            self.workdir = tempfile.mkdtemp('.tmp', 'atomic-treecompose')
            self.workdir_is_tmp = True

        self.buildjson()

        return

    @staticmethod
    def baseargs():
        """ Retrieve the default arguments applicable to all tasks. """
        parser = argparse.ArgumentParser(description='Toolbox task arguments', add_help=False)
        parser.add_argument('-c', '--config', type=str, required=True, help='Path to config file')
        return parser
   
    def checkini(self, settings, profile, configfile):
        # If a release is passed via -r and does not exist, error out
        if profile is not "DEFAULT" and not settings.has_section(profile):
            sections = settings.sections()
            fail_msg("Section {0} is not defined in your config file ({1}). Valid sections/profiles are {2}".format(
                profile, configfile, sections))
        config_req = ['os_name', 'os_pretty_name',
                      'tree_name', 'tree_file', 'arch', 'release', 'ref', 'yum_baseurl',
                      'docker_os_name']
        missing_confs = []
        for req in config_req:
            if not settings.has_option(profile, req):
                missing_confs.append(req)
        if len(missing_confs) > 0:
            fail_msg("The following option(s) {0} are not defined in your configuration file.  Please define them and re-run".format(missing_confs))

    def flattenjsoninclude(self, params, includefile):
        """ This function merges a dict that represents a tree file
        with a json includefile. It can now handle recursive json
        files
        """

        if includefile is not None:
            includefile = (os.path.dirname(self.tree_file)) + "/" + includefile
        if not os.path.isfile(includefile):
            fail_msg(("Your tree file includes another file %s that could not be found") % includefile)
        else:
            jsoninclude = open(includefile)
            incparams = json.load(jsoninclude)
            if 'include' in incparams:
                # Found a recursive include
                next_includefile = incparams.pop('include', None)
                incparams = self.flattenjsoninclude(incparams, next_includefile)
            for key in incparams:
                # If its a str,bool,or list and doesn't exist, add it
                if (key not in params) and (key != "comment"):
                    params[key] = incparams[key]
                # If its a list and already exists, merge them 
                if key in params and type(incparams[key]) == list:
                    merged = list(set(params[key] + incparams[key]))
                    params[key] = merged
        return params

    def buildjson(self):
        """ This function merges content from the config.ini and
        the json treefile and then outputs a merged, temporary
        json file in tempdir 
        """

        try:
            json_in = open(self.tree_file)
        except:
            fail_msg("Unable to locate the {0} as described in the config.ini".format(self.tree_file))
        params = json.load(json_in)
        if 'ref' not in 'params':
            params['ref']  = self.ref
        if 'selinux' not in 'params':
            params['selinux'] = self.selinux
        if 'osname' not in 'params':
            params['osname'] = self.os_name
        if 'include' in params:
            includefile = params.pop('include')
            params = self.flattenjsoninclude(params, includefile)
        # Need to flatten repos
        self._copyexternals(params)
        self.jsonfilename = os.path.join(self.workdir, os.path.basename(self.tree_file))
        self.jsonfile = open(self.jsonfilename, 'w')
        json.dump(params, self.jsonfile, indent=4)
        self.jsonfile.close()

    def _copyexternals(self, params):
        """
        We're generating a new copy of the treefile, so we need
        to also copy over any files it references.
        """

        treefile_base = os.path.dirname(self.tree_file)
        repos = params.get('repos', [])
        for repo in repos:
            repo_filename = repo + '.repo'
            repo_path = os.path.join(treefile_base, repo_filename) 
            if not os.path.exists(repo_path):
                fail_msg("Unable to find %s as declared in the json input file(s)" % repo_path)
            try:
                shutil.copyfile(repo_path, os.path.join(self.workdir, repo_filename))
            except:
                fail_msg("Unable to copy {0} to tempdir".format(repo_filename))
        post_script = params.get('postprocess-script')
        if post_script is not None:
            shutil.copy2(os.path.join(treefile_base, post_script), self.workdir)
            

    @property
    def repo(self):
        if not os.path.exists(self.ostree_repo):
            #  Remove the cache, if the repo. is gone ... or rpm-ostree is very
            # confused.
            if (self.rpmostree_cache_dir is not None and
                os.path.exists(self.rpmostree_cache_dir)):
                shutil.rmtree(self.rpmostree_cache_dir)
            os.makedirs(self.ostree_repo)
            subprocess.check_call(['ostree', 'init',
                                   "--repo="+self.ostree_repo, '--mode=archive-z2'])
        if self._repo is None:
            self._repo = OSTree.Repo(path=Gio.File.new_for_path(self.ostree_repo))
            self._repo.open(None)
        return self._repo

    def show_config(self):
        print "\n".join([ "%s=%s" % (x, str(getattr(self, x))) for x in self.ATTRS ])

    def cleanup(self):
        if self.workdir_is_tmp:
            shutil.rmtree(self.workdir)

    def hasValue(self, configkey, settings, profile):
        """
        This is a helper function for getConfigValue() and basically
        checks the profile of a config.ini and looks to see if the
        key exists.  If so, it returns the value, else None
        """
        configvalue = None
        if configkey in dict(settings.items(profile)):
            configvalue = settings.get(profile, configkey)
        return None if configvalue is None else configvalue

    def getConfigValue(self, configkey, settings, profile, defValue=None):
        """
        This function helps to safely extract config.ini values given a key,
        a ConfigParser object, a profile, and an optional default value. The
        function will search the profile first for a key/value, then the 
        default profile.  It will return the value or None if a default 
        fallback value is not provided
        """
        configvalue = self.hasValue(configkey, settings, profile)
        configvalue = self.hasValue(configkey, settings, "DEFAULT") if configvalue is None else configvalue
        return defValue if configvalue is None else configvalue

