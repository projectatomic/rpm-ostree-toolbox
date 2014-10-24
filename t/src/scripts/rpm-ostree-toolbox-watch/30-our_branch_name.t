# -*- perl -*-

use strict;
use warnings;

use Test::More;

###############################################################################
# BEGIN test setup

use FindBin qw($Bin);
require "$Bin/00-common.pl";
my $tempdir = make_test_directory();

our $expected_branch_name = 'mybranch';

plan tests => 1 + 1;

# END   test setup
###############################################################################
# BEGIN run tests

# From t/src/path/script/10foo.t, get src/path/script, and load it.
(my $script_path = $0) =~ s|^t/||;
$script_path =~ s|/[^/]+$||;

ok(require($script_path), "loaded $script_path") or exit;

chdir $tempdir
    or die "Cannot cd $tempdir: $!";

is RpmOstreeToolbox::Watch::our_branch_name(), $expected_branch_name,
    "expected branch name";

# Clean up
chdir '/';
