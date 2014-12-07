rpm-ostree-toolbox
==================

This is a higher level app on top of the core `rpm-ostree` tool.  It
contains a variety of tools and scripts for making disk images,
installer images, and ostree trees.

The rpm-ostree-toolbox should be called with one of three subcommands:

* treecompose
* installer
* imagefactory

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

