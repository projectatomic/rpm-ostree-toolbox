# -*- perl -*-
#
# common module for setting up a test environment
#

use File::Temp                  qw(tempdir);

sub make_test_directory {
    # Create a working directory. It will contain a bogus set of configs.
    my $tempdir = tempdir("watch.XXXXXX", TMPDIR => 1, CLEANUP => 1);

    # Write our initial config.ini file
    write_file("$tempdir/config.ini", <<'END_INI');
[DEFAULT]
tree_file = atomic/atomic.json
END_INI

    mkdir "$tempdir/atomic", 0700;
    mkdir "$tempdir/atomic/.git", 0700;

    write_file("$tempdir/atomic/.git/HEAD", "mybranch\n");

    write_file("$tempdir/atomic/atomic.json", <<'END_JSON');
{
    "comment": "this is not a comment",
    "repos": ["repo-1", "repo-2"],
    "packages": ["pkg1", "pkg2"]
}
END_JSON

    return $tempdir;
}


sub write_file {
    my $path = shift;
    open my $fh, '>', $path     or die "Cannot create $path: $!";
    print { $fh } @_;
    close $fh                   or die "Error writing $path: $!";
}

1;
