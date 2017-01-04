rpm-ostree-toolbox
==================

This is a higher level app on top of a few tools:

 - `rpm-ostree`: https://github.com/projectatomic/rpm-ostree
 - `lorax`: https://github.com/rhinstaller/lorax/
 - `imagefactory`: https://github.com/redhat-imaging/imagefactory
 
It is intended to streamline things for local development on
a workstation to build trees, installers, and cloud images.
It is also used in CentOS to build the installer.

However, it is now deprecated in favor of calling the above tools directly. The
most common developer use case is to make custom ostree commits, and invoking
`rpm-ostree compose tree` directly is better for this.

For automation, there is https://pagure.io/pungi which increasingly knows how to
operate with OSTree-based systems too. This is used in Fedora today, where the
OSTree-embedding logic for the installer is instead in
https://pagure.io/fedora-lorax-templates

For cloud images, we would like to instead improve ImageFactory
to streamline the "Anaconda kickstart" case.

You can also of course define Jenkins jobs or whatever that
call the above tools, as the CentOS Atomic Host jobs do:
https://github.com/CentOS/sig-atomic-buildscripts/tree/master/centos-ci

Getting started
---------------

Depending on the subcommand being called with rpm-ostree-toolbox, a
number of different input files are required.  The main configuration
file is generally called config.ini.  These are intended to be kept
inside revision control.  For example, this git repository holds the
Fedora Atomic configuration:

https://git.fedorahosted.org/cgit/fedora-atomic.git

rpm-ostree-toolbox treecompose
------------------------------

This allows you to create a tree of ostree content.  It takes various
inputs from a JSON file to perform most of its actions.  When
complete, you will have an ostree with content suitable for creating
disk images.

Example invocation:

    rpm-ostree-toolbox treecompose -c fedora-atomic/config.ini

It will write output into the current working directory.

rpm-ostree-toolbox installer
----------------------------

This command creates ISO and PXE images that can be used as install
media.  This can either be done with a container-based approach or
using libvirt.

rpm-ostree-toolbox imagefactory
-------------------------------

With imagefactory, you can create various virtualized images with
libvirt related tooling.  Currently it is capable of making qcow2,
raw, vsphere, and rhevm images.  This can be altered with the -i
argument.

These need to reference an installer image.

