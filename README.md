rpm-ostree-toolbox
==================

This is a higher level app on top of the core `rpm-ostree` tool.  It
contains a variety of tools and scripts for making disk images and
such.

Running a tool
--------------

Here's an example command, where /srv/rpm-ostree holds an OSTree
repository named "repo".

$ docker run --privileged -v /srv/rpm-ostree:/srv/rpm-ostree cgwalters/rpm-ostree-toolbox rpm-ostree-toolbox qa-make-disk /srv/rpm-ostree/repo fedora-atomic-host fedora-atomic-host/rawhide/x86_64/base /srv/rpm-ostree/fedora-atomic-host.qcow2

