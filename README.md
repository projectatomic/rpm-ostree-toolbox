rpm-ostree-toolbox
==================

This is a higher level app on top of the core `rpm-ostree` tool.  It
contains a variety of tools and scripts for making disk images, the
"repoweb" generator, and such.

Some tools are short term hacks, like the disk image generation, which
would be better done via Anaconda.  The repoweb tool was just a quick
experiment, but may have a long life.

The "trivial-autobuilder" below is the most unstable.  I'm thinking
about a better architecture where there's a split between a frontend
web UI and a backend that runs as root.  The web UI should have
read-only access to the data.

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
