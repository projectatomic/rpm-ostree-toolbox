Autobuilder
-----------

 * `treefiles`: array of strings, mandatory: Path to treefiles to use
   for composes.

 * `disks` map of string -> boolean, optional: Generate disk images
   for these given treefiles.

 * `poll-timeout` integer, mandatory: Timeout in seconds for polling
   for new repository content.

 * `autoupdate-self`: boolean, optional: If `true`, then the autocompose
   server will automatically run `git pull -r` on the git repository
   holding the treefiles.
