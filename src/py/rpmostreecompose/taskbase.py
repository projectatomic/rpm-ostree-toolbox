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
from gi.repository import Gio, OSTree, GLib  # pylint: disable=no-name-in-module
import iniparse
import ConfigParser  # for errors
from .utils import fail_msg, log, run_sync
import urlparse
import urllib2

def _merge_lists(x, y):
    try:
        return list(set(x + y))
    except TypeError:
        pass # no __hash__, Eg. List of lists

    ret = []
    for i in x:
        if i in ret:
            continue
        ret.append(i)
    for i in y:
        if i in ret:
            continue
        ret.append(i)
    return ret

class TaskBase(object):
    ATTRS = [ 'workdir', 'rpmostree_cache_dir', 'pkgdatadir',
              'os_name', 'os_pretty_name', 'ostree_repo',
              'tree_name', 'tree_file', 'arch', 'release', 'ref',
              'yum_baseurl', 'lorax_additional_repos',
              'is_final',
              'lorax_exclude_packages',
              'lorax_include_packages',
              'local_overrides', 'http_proxy',
              'selinux', 'configdir', 'docker_os_name'
            ]


    def __init__(self, args, cmd, profile=None):
        self.workdir = None
        self.tree_file = None
        self.rpmostree_cache_dir = None
        self.pkgdatadir = None
        self.os_name = None
        self.os_pretty_name = None
        self.tree_name = None
        self.tree_file = None
        self.arch = None
        self.release = None
        self.ref = None
        self.yum_baseurl = None
        self.lorax_additional_repos = None
        self.is_final = None
        self.lorax_exclude_packages = None
        self.lorax_include_packages = None
        self.local_overrides = None
        self.http_proxy = None
        self.selinux = None
        self.configdir = None
        self.docker_os_name = None

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

        if os.path.isdir(self.outputdir + "/.git"):
            fail_msg("Found .git in the current directory; you most likely don't want to build in source directory")

        for attr in self.ATTRS:
            val = self.getConfigValue(attr, settings, profile, defValue=defaults.get(attr))
            setattr(self, attr, val)

        # Checking ostreerepo
        self.ostree_port = None
        self.ostree_repo_is_remote = False
        self.httpd_path = ""
        self.httpd_host = ""
        if args.ostreerepo is not None:
            self.ostree_repo = args.ostreerepo
            # The ostree_repo is given in URL format
            if 'http' in self.ostree_repo:
                self.ostree_repo_is_remote = True
                urlp = urlparse.urlparse(self.ostree_repo)
                # FIXME
                # When ostree creates the summary file by default, re-enable this.
                # try:
                #     summaryfile = urllib2.urlopen(urlparse.urljoin(self.ostree_repo, "summary")).read()

                # except urllib2.HTTPError, e:
                #     fail_msg("Unable to open the ostree sumarry file with the URL {0} due to {1}".format(self.ostree_repo, str(e)))

                # except urllib2.URLError, e:
                #     fail_msg("Unable to open the ostree summary file with the URL {0} due to {1}".format(self.ostree_repo, str(e)))
                self.httpd_port = str(urlp.port if urlp.port is not None else 80)
                self.httpd_path = urlp.path
                self.httpd_host = urlp.hostname

                # FIXME
                # When ostree creates the summary file by default, re-enable this.
                # if not self.checkRefExists(getattr(self,'ref'), summaryfile):
                #     fail_msg("The ref {0} cannot be found in in the URL {1}".format(getattr(self,'ref'), self.ostree_repo))
        if not self.ostree_repo:
            self.ostree_repo = os.environ.get('OSTREE_REPO')
        if not self.ostree_repo:
            self.ostree_repo = self.outputdir + '/repo'
        release = self.release
        # Check for configdir in attrs, else fallback to dir holding config
        if self.configdir is None:
            self.configdir = os.path.dirname(os.path.realpath(configfile))

        if self.tree_file is None:
            fail_msg("No tree file was provided")
        else:
            self.tree_file = os.path.join(self.configdir, self.tree_file)

        # Look for virtnetwork

        if 'virtnetwork' in args:
            self.virtnetwork = args.virtnetwork
        else:
            self.virtnetwork = None

        self.os_nr = "{0}-{1}".format(self.os_name, self.release)

        # Set name from args, else fallback to default
        if 'name' in args and args.name is not None:
            self.name = args.name
        else:
            self.name = self.os_nr

        if cmd == "installer":
            if not self.yum_baseurl and args.yum_baseurl == None:
                fail_msg("No yum_baseurl was provided in your config.ini or with installer -b.")

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
        parser.add_argument('--ostreerepo', type=str, required=False, help='Path to OSTree repository (default: ${pwd}/repo)')
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

    def _require_ostree_repo(self, url):
        configurl = url + '/config'
        try:
            subprocess.check_call(['curl', '--head', configurl])
        except subprocess.CalledProcessError, e:
            fail_msg("Unable to find OSTree repository config {0}; Please verify the location and re-run.".format(configurl))
        log("Verified OSTree repository: {0}".format(url))

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
                    params[key] = _merge_lists(params[key], incparams[key])
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

        repo_dict = {}  # map repository names to .repo files
        for basename in os.listdir(treefile_base):
            if not basename.endswith('.repo'):
                continue
            repo_data = iniparse.ConfigParser()
            try:
                repo_data.read(os.path.join(treefile_base, basename))
            except ConfigParser.Error as e:
                fail_msg("Error parsing file {0}: {1}".format(basename, e.message))
            for repo_name in repo_data.sections():
                repo_dict[repo_name] = basename

        copy_files = {}
        repos = params.get('repos', [])
        for repo_name in repos:
            try:
                basename = repo_dict[repo_name]
            except KeyError:
                fail_msg("Unable to find repo '%s' as declared in the json input file(s)" % repo_name)
            copy_orig = os.path.join(treefile_base, basename)
            copy_dest = os.path.join(self.workdir, basename)
            copy_files[copy_orig] = copy_dest

        for copy_orig, copy_dest in copy_files.items():
            try:
                shutil.copyfile(copy_orig, copy_dest)
            except:
                fail_msg("Unable to copy {0} to tempdir".format(copy_orig))
        post_script = params.get('postprocess-script')
        if post_script is not None:
            shutil.copy2(os.path.join(treefile_base, post_script), self.workdir)
        for key in ['check-passwd', 'check-groups']:
            check = params.get(key)
            if check and check['type'] == 'file':
                filename = check['filename']
                shutil.copy2(os.path.join(treefile_base, filename), self.workdir)

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

            try:
                self._repo.open(None)
            except:
                fail_msg("The repo location {0} has not been initialized.  Use 'ostree --repo={0} init --mode=archive-z2' to initialize and re-run rpm-ostree-toolbox".format(self.ostree_repo))

        return self._repo

    def show_config(self):
        log("\n".join([ "%s=%s" % (x, str(getattr(self, x))) for x in self.ATTRS ]))

    def cleanup(self):
        if self.workdir_is_tmp:
            shutil.rmtree(self.workdir)

    def getrepos(self, flatjson):
        fj = open(self.jsonfilename)
        fjparams = json.load(fj)
        repos = ""
        repoids = []
        for repo in fjparams['repos']:
            repofile = os.path.join(self.configdir, repo + ".repo")
            repos = repos + open(repofile).read()
            repos = repos + "enabled=1"
            repos = repos + "\n"
            repoids.append(repo)
        if self.lorax_additional_repos:
            for i,repourl in enumerate(self.lorax_additional_repos.split(',')):
                repos += "[lorax-repo-{0}]\nbaseurl={1}\nenabled=1\ngpgcheck=0\n".format(i, repourl)
                repoids.append('lorax-repo-{0}'.format(i))
        return repoids,repos

    def generateDockerName(self, name, packages, suffix):
        return 'rpm-ostree-toolbox/' + self.os_name + '-' + self.release + '-' + name + '-' + suffix

    def buildDockerWorkerBaseImage(self, name, packages):
        """
        Generate a local Docker image named @name containing packages
        @packages.  This won't be runnable directly, you probably want
        to use buildDockerWorker().
        """

        fullname = self.generateDockerName(name, packages, 'base')

        repoids, repos = self.getrepos(self.jsonfilename)
        log("Using lorax.repo:\n" + repos)
        with open(self.workdir + '/lorax.repo', 'w') as f:
            f.write(repos)

        docker_builder_argv = ['rpm-ostree-toolbox', 'docker-image',
                               '--minimize=docs',
                               '--minimize=langs',
                               '--reposdir', self.workdir,
                               '--name', fullname]
        for r in repoids:
            docker_builder_argv.append('--enablerepo=' + r)

        docker_builder_argv.extend(packages)
                               
        run_sync(docker_builder_argv)

        return fullname

    def buildDockerWorker(self, name, packages, dockerfile, contextdir=None):
        """
        Generate a local Docker image using @packages as a base and
        @contextdir for the Dockerfile.
        """
        basename = self.buildDockerWorkerBaseImage(name, packages)
        fullname = self.generateDockerName(name, packages, 'app')
        if contextdir is None:
            contextdir = os.path.join(self.workdir, 'tmp-' + name)
        with open(contextdir + '/Dockerfile', 'w') as f:
            f.write("FROM " + basename + '\n' + dockerfile)
        # Docker build
        db_cmd = ['docker', 'build', '-t', fullname, contextdir]
        child_env = dict(os.environ)
        if 'http_proxy' in child_env:
            del child_env['http_proxy']
        run_sync(db_cmd, env=child_env)
        return fullname

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

    def checkRefExists(self, ref, httpresponse):
        """
        This function determines if the HTTP ostree location has the same
        ref that is required.
        """
        typestr = GLib.VariantType.new('(a(s(taya{sv}))a{sv})')
        bytedata = GLib.Bytes.new(str(httpresponse))
        d = GLib.Variant.new_from_bytes(typestr, bytedata, False)
        httprefs = []
        for httpref in d[0]:
            httprefs.append(httpref[0])
        if ref in httprefs:
            return True
        else:
            return False

class ImageTaskBase(TaskBase):
    """For everything except treecompose.  Something that outputs 
    an image blob with log files."""

    def __init__(self, args, cmd, **kwargs):
        TaskBase.__init__(self, args, cmd, **kwargs)
        self.image_workdir = os.path.abspath(args.outputdir) + '/work'
        self.image_content_outputdir = self.image_workdir + '/images'
        self.image_log_outputdir = self.image_workdir + '/logs'

    @staticmethod
    def all_baseargs():
        """All arguments for a task, plus image arguments."""
        parser = argparse.ArgumentParser(description='Image task arguments', add_help=False)
        parser.add_argument('-o', '--outputdir', type=str, required=True, help='Path to image output directory')
        parser.add_argument('--overwrite', action='store_true', help='If true, replace any existing output')
        parser.add_argument('--preserve-ks-url', action='store_true', help='If true, do not auto-substitute kickstart ostreesetup url') 
        return [TaskBase.baseargs(), parser]

    def impl_create(self, **kwargs):
        """Subclasses must implement this"""
        raise NotImplementedError()
 
    def create(self, **kwargs):
        """Primary entrypoint for image creation.
        """
        exists = os.path.lexists(self.args.outputdir)
        if self.args.overwrite and exists:
            shutil.rmtree(self.args.outputdir)
        elif exists:
            fail_msg("The directory {0} already exists.".format(self.args.outputdir))
        os.makedirs(self.image_workdir)

        self.impl_create(**kwargs)
        self._finish()

    def _finish(self):
        """Generate a SHA256SUMs file, and move the staged work/ content to
        its final location.

        """
        run_sync(['/bin/sh', '-c', 'find .  -type f | grep -v \'.*SUMS$\' | xargs sha256sum'], cwd=self.image_content_outputdir,
                 stdout=open(self.image_content_outputdir + '/SHA256SUMS', 'w'))
        shutil.move(self.image_content_outputdir, self.args.outputdir)
        shutil.move(self.image_log_outputdir, self.args.outputdir)
        shutil.rmtree(self.image_workdir)
        log("Complete!  Images/ and logs/ written to {0}".format(self.args.outputdir))
