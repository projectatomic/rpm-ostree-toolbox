# -*- perl -*-

use strict;
use warnings;

use Test::More;


###############################################################################
# BEGIN test setup

use FindBin qw($Bin);
require "$Bin/00-common.pl";
my $tempdir = make_test_directory();

# END   test setup
###############################################################################

# From t/src/path/script/10foo.t, get src/path/script, and load it.
(my $script_path = $0) =~ s|^t/||;
$script_path =~ s|/[^/]+$||;

ok(require($script_path), "loaded $script_path") or exit;

# Override we_trigger_on()

# run tests
chdir $tempdir
    or die "Cannot cd $tempdir: $!";

my %event = (
    _PID          => "123",
    _SYSTEMD_UNIT => "rpm-ostree-toolbox-git-monitor.service",
    MESSAGE       => "ip:1.2.3.4 branch:mybranch",
);


# Create a fake rpm-ostree-toolbox script
mkdir 'bin', 0755 or die "mkdir bin: $!\n";
write_file("bin/rpm-ostree-toolbox", <<'END_TOOLBOX');
#!/bin/sh
echo "BEGIN $0"
for i in "$@"; do
    echo "  $i"
done
echo "END   $0"

exit 0
END_TOOLBOX
chmod 0755 => "bin/rpm-ostree-toolbox";
link "bin/rpm-ostree-toolbox", "bin/git";
$ENV{PATH} = "$tempdir/bin";

my $begin_end;
close STDOUT;
open STDOUT, '>', \$begin_end
    or die "Could not reopen STDOUT: $!";
RpmOstreeToolbox::Watch::start_job(\%event);

# WAIT! The child process is still running. Wait for it to complete.
# Yes, this is not robust. Got a better idea?
sleep 2;

# We can't use like() because it doesn't give us captures :(
$begin_end =~  qr{^BEGIN \s+ compose;\s+                see\s+(\S+)\n
                   END   \s+ compose;\s+status=(\S+);\s+see\s+(\S+)\n$}x
    or do {
        fail "Logged output: expected 'BEGIN/END compose' lines";
        diag "Expected:\nBEGIN...\nActual:\n$begin_end\n";
        die "Cannot proceed with tests";
    };

# Log path on BEGIN and END must be identical
my ($log1, $status, $log2) = ($1, $2, $3);
is $log1, $log2, "matching log file paths for BEGIN and END";

# Status code 0
is $status, "0", "exit code of subprocess = 0";

# Read the log, make sure it looks reasonable.
# this will not be fun to debug if it ever fails. I'm sorry.
my $actual_log   = read_file($log1);
my $expected_log = <<'EXPECTED_LOG_RE';
######+
#
# Log created by \S+
# Triggered by the following journal event:
#
#    MESSAGE       = ip:1.2.3.4 branch:mybranch
#    _PID          = 123
#    _SYSTEMD_UNIT = rpm-ostree-toolbox-git-monitor.service
#
# \d+-\d+-\d+T\d+:\d+:\d+ BEGIN

\$ \(cd atomic && git pull -r\)
BEGIN \S+/bin/git
  pull
  -r
END   \S+/bin/git

\$ rpm-ostree-toolbox treecompose -c ./config.ini
BEGIN \S+/bin/rpm-ostree-toolbox
  treecompose
  -c
  ./config.ini
END   \S+/bin/rpm-ostree-toolbox

# \d+-\d+-\d+T\d+:\d+:\d+ FINISHED: success
####+
EXPECTED_LOG_RE

like $actual_log, qr{$expected_log}s, "Log file contents";

done_testing();


sub read_file {
    my $path = shift;
    my $s = '';
    open my $fh, '<', $path
        or die "Cannot read $path: $!";
    my $contents = do { local $/ = undef; <$fh>; };
    close $fh;

    return $contents;
}
