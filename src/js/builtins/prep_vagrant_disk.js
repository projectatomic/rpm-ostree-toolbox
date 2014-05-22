// -*- indent-tabs-mode: nil; tab-width: 2; -*-
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

const GLib = imports.gi.GLib;
const Gio = imports.gi.Gio;
const Lang = imports.lang;
const Format = imports.format;

const GSystem = imports.gi.GSystem;
const OSTree = imports.gi.OSTree;

const Builtin = imports.builtin;
const ArgParse = imports.argparse;
const ProcUtil = imports.procutil;
const LibQA = imports.libqa;
const GuestFish = imports.guestfish;

const PrepVagrantDisk = new Lang.Class({
    Name: 'PrepVagrantDisk',
    Extends: Builtin.Builtin,

    DESCRIPTION: "Prepare a disk image for Vagrant",

    _init: function() {
        this.parent();
        this.parser.addArgument('diskpath');
    },

    execute: function(args, loop, cancellable) {
        let tmpdir = Gio.File.new_for_path(GLib.dir_make_tmp('rpmostreetoolbox.XXXXXX'));
        let mntdir = tmpdir.get_child('mnt');
        GSystem.file_ensure_directory(mntdir, true, cancellable);
        let gfmnt = new GuestFish.GuestMount(Gio.File.new_for_path(args.diskpath),
                                             { partitionOpts: LibQA.DEFAULT_GF_PARTITION_OPTS,
                                               readWrite: true });
        gfmnt.mount(mntdir, cancellable);
        try {
            let sysroot = OSTree.Sysroot.new(mntdir);
            sysroot.load(null);
            let deployments = sysroot.get_deployments();
            let deployment = deployments[0];
            let deployDir = sysroot.get_deployment_directory(deployment);

            let doVagrantPrepData = '#!/bin/bash\n\
set -e\n\
set -x\n\
if ! getent passwd vagrant 1>/dev/null; then useradd vagrant; fi\n\
echo "vagrant" | passwd --stdin vagrant\n\
if ! groups vagrant | grep wheel; then usermod -a -G wheel vagrant; fi\n\
sed -i \'s,Defaults\\s*requiretty,Defaults !requiretty,\' /etc/sudoers\n\
echo \'%wheel ALL=NOPASSWD: ALL\' > /etc/sudoers.d/vagrant-nopasswd-wheel\n\
sed -i \'s/.*UseDNS.*/UseDNS no/\' /etc/ssh/sshd_config\n\
mkdir -m 0700 -p ~vagrant/.ssh\n\
cat > ~vagrant/.ssh/authorized_keys << EOF\n\
ssh-rsa AAAAB3NzaC1yc2EAAAABIwAAAQEA6NF8iallvQVp22WDkTkyrtvp9eWW6A8YVr+kz4TjGYe7gHzIw+niNltGEFHzD8+v1I2YJ6oXevct1YeS0o9HZyN1Q9qgCgzUFtdOKLv6IedplqoPkcmF0aYet2PkEDo3MlTBckFXPITAMzF8dJSIFo9D8HfdOV0IAdx4O7PtixWKn5y2hMNG0zQPyUecp4pzC6kivAIhyfHilFR61RGL+GPXQ2MWZWFYbAGjyiYJnAmCP3NOTd0jMZEnDkbUvxhMmBYSdETk1rRgm+R4LOzFUGaHqHDLKLX+FIPKcF96hrucXzcWyLbIbEgE98OHlnVYCzRdK8jlqm8tehUc9c9WhQ== vagrant insecure public key\n\
EOF\n\
chmod 600 ~vagrant/.ssh/authorized_keys\n\
chown -R vagrant:vagrant ~vagrant/.ssh/\n\
touch /var/completed-vagrant-prep\n\
';
            let execPath = deployDir.resolve_relative_path('usr/libexec/do-vagrant-prep');
            execPath.replace_contents(doVagrantPrepData, null, false, Gio.FileCreateFlags.REPLACE_DESTINATION, cancellable);
            GSystem.file_chmod(execPath, 493, cancellable);
            print("Created " + execPath.get_path());

            let doVagrantPrepPath = deployDir.resolve_relative_path('usr/libexec/do-vagrant-prep');

            let doVagrantPrepServiceData = '[Unit]\n\
Description=Initialize vagrant\n\
Before=sshd.service\n\
ConditionPathExists=!/var/completed-vagrant-prep\n\
[Service]\n\
ExecStart=/usr/libexec/do-vagrant-prep\n\
Type=oneshot\n';
            let serviceRelpath = 'usr/lib/systemd/system/do-vagrant-prep.service';
            deployDir.resolve_relative_path(serviceRelpath).replace_contents(doVagrantPrepServiceData, null, false, Gio.FileCreateFlags.REPLACE_DESTINATION, cancellable);
            let linkTarget = deployDir.resolve_relative_path('etc/systemd/system/multi-user.target.wants/do-vagrant-prep.service');
            linkTarget.make_symbolic_link('/' + serviceRelpath, cancellable);
            print("Created " + linkTarget.get_path());
        } finally {
            gfmnt.umount(cancellable);
        }
    }
});
