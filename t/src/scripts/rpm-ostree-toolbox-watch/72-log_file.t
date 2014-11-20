# -*- perl -*-
#
# Test that log_file() returns a suitable path, and handles same-second
# calls with a sequence number.
#
use strict;
use warnings;

use File::Temp          qw(tempdir);
use Test::More;

# From t/src/path/script/10foo.t, get src/path/script, and load it.
(my $script_path = $0) =~ s|^t/||;
$script_path =~ s|/[^/]+$||;

ok(require($script_path), "loaded $script_path") or exit;

my $tempdir = tempdir("72-log_file.XXXXXXXXX", TMPDIR => 1, CLEANUP => 1);
chdir $tempdir
    or die "Cannot cd $tempdir: $!";

# Run log_dir() ten times in a row. On anything other than a TRS-80
# this will ensure that some of the calls happen within the same second,
# so the subdirectory gets a sequence number (.1).
my @log_files = map { RpmOstreeToolbox::Watch::log_file() } 1..10;

# Make sure that all of them are of the form YYYY/MM/DD/HHhMMSS*/output.txt
for my $f (@log_files) {
    $f =~ s{^.*/tasks/treecompose/}{}
        or fail "log file subdirectory not 'tasks/treecompose/': $f";
    $f =~ s{/output\.txt$}{}
        or fail "log file name is not output.txt: $f";
    like $f, qr{^\d{4}/\d\d/\d\d/\d\dh\d\d\d\d(\.\d+)?$},
        "log file is of the proper form";
}

# At least one of them must be _exactly_ HHhMMSS/output.txt
my @exact = grep { $_ =~ m|/\d\dh\d\d\d\d$| } @log_files;
ok( @exact >= 1, "At least one HHhMMSS directory");

# At least one of them must have a sequence number of .1
my @sequenced = grep { $_ =~ m|/\d\dh\d\d\d\d\.1$| } @log_files;
ok( @sequenced >= 1, "At least one sequenced (HHhMMSS.1) directory");

# And .2
@sequenced = grep { $_ =~ m|/\d\dh\d\d\d\d\.2$| } @log_files;
ok( @sequenced >= 1, "At least one .2 (HHhMMSS.2) directory");

done_testing();
