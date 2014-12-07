rpm-ostree-toolbox
==================

This is a higher level app on top of the core `rpm-ostree` tool.  It
contains a variety of tools and scripts for making disk images, installer images, and ostree trees.

The rpm-ostree-toolbox should be called with one of three subcommands:

* treecompose
* imagefactory
* installer


Getting started
---------------
Depending on the subcommand being called with rpm-ostree-toolbox, a number of different input files are required.  The main configuration file is generally called config.ini.  A sample is provided with rpm-ostree-toolbox.  Be sure to review and edit the config.ini where applicable.  It is heavily commented and self-explanatory.

There is a git repository to help you get started with rpm-ostree-toolbox and Fedora located at https://git.fedorahosted.org/cgit/fedora-atomic.git .


rpm-ostree-toolbox treecompose
------------------------------
This allows you to create a tree of ostree content.  It takes various inputs from a JSON file to perform most of its actions.  When complete, you will have an ostree with content suitable for creating 

rpm-ostree-toolbox imagefactory
-------------------------------
With imagefactory, you can create various virtualized images with libvirt related tooling.  Currently it is capable of making qcow2, raw, vsphere, and rhevm images.  This can be altered with the -i argument.  

rpm-ostree-toolbox installer
----------------------------
This command creates ISO and PXE images that can be used as install media.  This can either be done with a container-based approach or using libvirt.

