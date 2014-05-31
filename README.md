rpm-ostree-toolbox
==================

This is a higher level app on top of the core `rpm-ostree` tool.  It
contains a variety of tools and scripts for making disk images and
such.

Running an unattended compose
-----------------------------

Most likely, you want to start using rpm-ostree by running a "compose"
server.  We use the term "compose" instead of "build" as there's no
actual source code being changed here, just a mechanical
transformation of RPM -> OSTree -> disk images.

First, you need to run through the setup instructions of the current
rpm-ostree README.md.

Once you've done this, see `doc/autobuilder.json` for a sample JSON
configuration file for the autobuilder.

	$ rpm-ostree-toolbox trivial-autocompose /path/to/autobuilder.json
