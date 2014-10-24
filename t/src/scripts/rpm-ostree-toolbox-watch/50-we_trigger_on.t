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
my $expect = <<'END_EXPECT';
build    repo:repo-1                         1
build    repo:repo-2                         1
build    repo:repo-3                         0
build    repo:myrepo                         0
build    unexpected output                   0
build    repo-1                              0
git      ip:10.10.10.10 branch:hithere       0
git      ip:10.10.10.10 branch:mybranch      1
git      unexpected output                   0
END_EXPECT

# Build an input line out of each of the above lines, generating the
# boilerplate journalctl output.
my @tests;
for my $line (split "\n", $expect) {
    my ($which, @rest) = split ' ', $line;
    my $tf = pop @rest;
    push @tests, {
        name  => "$which: @rest => $tf",
        input => "YYYY-MM-DDTHH:MM:SS myhost rpm-ostree-toolbox-$which-monitor\[12345\]: @rest",
        expect => $tf,
    };
}

plan tests => 1 + @tests;

# END   test setup
###############################################################################
# BEGIN run tests

# From t/src/path/script/10foo.t, get src/path/script, and load it.
(my $script_path = $0) =~ s|^t/||;
$script_path =~ s|/[^/]+$||;

ok(require($script_path), "loaded $script_path") or exit;

# run tests
chdir $tempdir
    or die "Cannot cd $tempdir: $!";
for my $t (@tests) {
    is !!RpmOstreeToolbox::Watch::we_trigger_on($t->{input})+0,
        $t->{expect},
        $t->{name};
}

# Clean up
chdir '/';
exit 0;
