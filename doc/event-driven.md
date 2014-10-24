Overview
========

This document describes the proposed architecture for an event-driven
build system. It is current as of 2014-10-23.

Background: Starting Points
---------------------------

To understand the events we monitor, you need to understand the
inputs to `rpm-ostree-toolbox treecompose`. Here's a simplified
view of the directory in which treecompose runs:

    workdir/
    |-- config.ini                   <---- starting point
    `-- atomic-tree/
        |-- atomic-tree.json         <---- packages and repos
        |-- mybaserepo.repo
        `-- myotherrepo.repo

The starting point is `config.ini`. This is a hand-maintained file,
not under source control. For our purposes the only interesting
entry in it is **tree_file**, which points to a JSON file containing
packages and repos (here `atomic-tree.json`). `config.ini` can be
watched via *inotify*.

The JSON file lives in a git-managed directory. It is expected to
be readonly on the compose server, with updates via `git pull`.
To watch this, we need *git notification hooks* on the git master
server.

The JSON file defines one or more yum repos, whence it
gets the RPM packages in the compose. We detect changes to
these repos via *message bus* notifications.

Proposed Watch Mechanism
========================

Message Bus
-----------

A message bus listener triggers on **repobuild** messages. Upon
receipt it simply echoes the repo name to its stdout. When running
under systemd this goes to the **journal**.

(*Note*: this is a change from the current 2014-10-23 implementation,
in which the message bus listener has a configurable rule for
which repos to trigger on. That was a bad design decision, caused
by my ignorance of the compose process. The proposed mechanism
echoes **ALL** repos, leaving it up to another process to decide
whether the repo is a desired one or not. This also gets rid of
the trigger_command config setting.)

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

There is *one process per tree*. That is: there are multiple compose
trees, each of them for a different git branch of the `atomic` repo
containing the JSON file and repos.

This process watches the systemd journal:

    journalctl -u rpm-ostree-compose-build-monitor@koji.service \
               -u rpm-ostree-compose-git-monitor.service \
               -ef

Output will look like:

    <timestamp> <hostname> <service>[pid]: <useful info>

e.g.

    Oct 22 16:56:35 myhost rpm-ostree-toolbox-git-monitor[27275]: ip:127.0.0.5 branch:master
    Oct 22 18:11:23 myhost rpm-ostree-toolbox-build-monitor[27355]: foo-repo
    Oct 22 18:11:28 myhost rpm-ostree-toolbox-build-monitor[27355]: bar-repo

Upon seeing a **`git-monitor`** line, the watcher process:

1. reads the given branch name. This is the *pushed* branch.
1. reads `atomic-dir/.git/HEAD` (or runs `git rev-parse --abbrev-ref HEAD`).
This is the *current* branch.
1. if *pushed* = *current*, run **git pull -r** and run a compose.

Upon seeing a **`build-monitor`** line, the watcher process:

1. reads the repo name. This is the *updated* repo.
1. reads `config.ini` to get the `tree_file` path (JSON file)
1. reads the given JSON file to get its list of repos. These are
the *desired* repos.
1. if the *updated* repo is one of the *desired* repos, run a compose.

The watcher process should also add an inotify watch on `config.ini`.

Summary
=======

I believe this is much saner than the current one-trigger-fits-all
mechanism: it provides *granularity*, so different compose trees can
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
