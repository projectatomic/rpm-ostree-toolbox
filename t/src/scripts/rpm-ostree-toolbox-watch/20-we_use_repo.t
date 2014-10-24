# -*- perl -*-

use strict;
use warnings;

use Test::More;

###############################################################################
# BEGIN test setup

use FindBin qw($Bin);
require "$Bin/00-common.pl";
my $tempdir = make_test_directory();

# Given the setup in 00-common.pl, this is what we expect:
our %expect = (
    "repo-1"  => 1,
    "repo-2"  => 1,
    "repo-3"  => 0,
    "repo-"   => 0,
    "repo-11" => 0,
    "1"       => 0,
);

plan tests => 1 + keys(%expect);

# END   test setup
###############################################################################
# BEGIN run tests

# From t/src/path/script/10foo.t, get src/path/script, and load it.
(my $script_path = $0) =~ s|^t/||;
$script_path =~ s|/[^/]+$||;

ok(require($script_path), "loaded $script_path") or exit;

chdir $tempdir
    or die "Cannot cd $tempdir: $!";
for my $t (sort keys %expect) {
    is RpmOstreeToolbox::Watch::we_use_repo($t), $expect{$t},
        "we_use_repo($t) = $expect{$t}";
}

# Clean up
chdir '/';
