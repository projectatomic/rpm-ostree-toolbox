# -*- perl -*-
#
# Not really a thorough test: we don't check timeouts or the (unlikely!)
# case of nonterminated input. But good enough to see if single and
# multiple lines work.
#
use strict;
use warnings;

use File::Temp          qw(tempfile);
use Test::More;

# From t/src/path/script/10foo.t, get src/path/script, and load it.
(my $script_path = $0) =~ s|^t/||;
$script_path =~ s|/[^/]+$||;

ok(require($script_path), "loaded $script_path") or exit;

compare("empty", <<"END_EXPECT");
END_EXPECT

compare("one line", <<"END_EXPECT");
this is one line
END_EXPECT

compare("two lines", <<"END_EXPECT");
this is one line
this is another
END_EXPECT

done_testing();



sub compare {
    my $name  = shift;                  # in: test name
    my $lines = shift;                  # in: one or more lines

    my ($fh, $path) = tempfile("71-sysreadline.t.XXXXXXX", TMPDIR => 1);
    print { $fh } $lines;
    close $fh;
    open $fh, '<', $path
        or die "Could not open $path: $!";

    my @expect = split "\n", $lines;
    my $lineno = 1;
    while (my $actual = RpmOstreeToolbox::Watch::sysreadline($fh,1)) {
        if (@expect) {
            is $actual, shift(@expect), "$name:$lineno";
            $lineno++;
        }
        else {
            fail "$name:$lineno: was not expecting anything; got '$actual'";
        }
    }

    # Done reading. Were we expecting anything else?
    if (@expect) {
        fail "$name:$lineno: expecting '@expect', got nothing";
    }

    # Clean up tempfile
    unlink $path;
}
