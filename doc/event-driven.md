Overview
========

This document describes the architecture of the event-driven build system
used to generate composes. It is current as of 2014-12-24.

Background: Starting Points
---------------------------

To understand the events we monitor, you need to understand the
inputs to `rpm-ostree-toolbox treecompose`. Here's a simplified
view of the directory in which treecompose runs:

    /srv/workdir/
    |-- config.ini                   <---- starting point
    `-- atomic-tree/
        |-- atomic-tree.json         <---- packages and repos
        |-- mybaserepo.repo
        `-- myotherrepo.repo

The starting point is `config.ini`. As of 2014-12-02 this is supposed
to be a symlink to `atomic-tree/config.ini`, which is under git,
but this is not enforced. There might still be some `/srv/foo` workdir
trees with a hand-maintained, not-under-git config.ini.

For our purposes the only interesting entry in config.ini is **tree_file**,
which points to a JSON file containing packages and repos (here
`atomic-tree.json`).

The JSON file lives in a git-managed directory. It is expected to
be readonly on the compose server, with updates via `git pull`.
To watch this, we need *git notification hooks* on the git master
server.

The JSON file defines one or more yum repos, whence it
gets the RPM packages in the compose. We detect changes to
these repos via *message bus* notifications.

Watch Mechanism
===============

Message Bus
-----------

A message bus listener triggers on **repobuild** messages. Upon
receipt it simply echoes the repo name to its stdout. When running
under systemd this goes to the **journal**.

Note that *all* repobuild messages get logged. It is up to the
`rpm-ostree-toolbox-watch` tool (below) to decide whether or not
those should trigger a compose.

Git
---

A git post-receive hook, `src/scripts/rpm-ostree-toolbox-git-post-receive-hook`,
lives on the git master server. Upon git-push it:

1. gathers a list of all branches affected by the commit(s); then
1. connects to port 8099 on a build server (hardcoded into the script); then
1. sends it that list of branches.

On the **build server**, a daemon process is listening on that socket.
It receives those branches (simple text, one branch per line) and
spits them right back out on its stdout. When running via systemd
these will go into the **journal**.

*Security*: this is totally unauthenticated. That is not easy to fix.

Triggering a Compose
--------------------

The watch process is `src/scripts/rpm-ostree-toolbox-watch`.

There is *one process per tree*. That is: there are multiple compose
trees of the form `/srv/treename`, each of them for a different git branch
of the `atomic` repo containing the JSON file and repos.

This process watches the systemd journal:

    journalctl -u rpm-ostree-toolbox-build-monitor@SOMETHING.service \
               -u rpm-ostree-toolbox-git-monitor.service \
               -ef --output=json

Note the `--output=json`. It's nice of journalctl to offer that option. It
spits out a JSON-formatted message on one line.

Upon seeing a message from **`git-monitor`**, the watcher process:

1. reads the given branch name. This is the *pushed* branch.
1. reads `atomic-dir/.git/HEAD` (or runs `git rev-parse --abbrev-ref HEAD`).
This is the *current* branch.
1. if *pushed* = *current*, run **git pull -r** and run a compose.

Upon seeing a message from **`build-monitor`**, the watcher process:

1. reads the repo name. This is the *updated* repo.
1. reads `config.ini` to get the `tree_file` path (JSON file)
1. reads the given JSON file to get its list of repos. These are
the *desired* repos.
1. if the *updated* repo is one of the *desired* repos, run a compose.

FIXME: the watcher process should add an inotify watch on `config.ini`.

Summary
=======

This mechanism improves on past efforts as follows: it provides
*granularity*, so different compose trees can
trigger only on events relevant to them. It provides *logging*, so
it's possible to determine what triggered a given compose (for
debugging). It *reduces duplication*, because the build-monitor
no longer needs a configurable (and stale-able) rule for triggering.

The build and git monitor scripts are not dockerizable: build-monitor
needs difficult-to-get Kerberos credentials, and git-monitor needs to
listen on a known host:port. But by using systemd journal, the
watch+compose portion may be dockerizable.

It does not provide security: the git-monitor listens on an open
port. A hostile entity could DOS by sending fake branch messages,
causing unnecessary composes and wasted cycles.
