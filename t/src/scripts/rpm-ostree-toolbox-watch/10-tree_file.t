# -*- perl -*-

use strict;
use warnings;

use Test::More;
use File::Temp                  qw(tempfile);

###############################################################################
# BEGIN test setup.
#
# Tests are defined in __END__ section below.
#

# See below for syntax of tests. This gives each icon a readable name.
my %iconmap = (
    '*' => 'name',
    '>' => 'expect',
    '!' => 'fatal',
);
my $icon_re = join('|', map { "\\$_" } sort keys %iconmap);

# Read the test list, convert to list form.
our @tests = ({});
while (my $line = <DATA>) {
    chomp $line;
    next unless $line;                  # skip blank lines

    # Line of hyphens: new test
    if ($line =~ /^-+$/) {
        push @tests, {};
    }

    # One of our icons:
    #  * test name
    #  > expected_tree_name
    #  ! fatal error
    elsif ($line =~ /^($icon_re)\s+(.*)/) {
        $tests[-1]->{$iconmap{$1}} = $2;
    }

    # Anything else: part of a config file
    else {
        $tests[-1]->{config} .= $line . "\n";
    }
}

plan tests => 1 + @tests;

# END   test setup
###############################################################################

# From t/src/path/script/10foo.t, get src/path/script, and load it.
(my $script_path = $0) =~ s|^t/||;
$script_path =~ s|/[^/]+$||;

ok(require($script_path), "loaded $script_path") or exit;


# Run each test.
for my $t (@tests) {
    # config.ini file (tempfile)
    (my $template = $0) =~ s|/|-|g;
    my ($fh, $cfgpath) = tempfile( "$template.XXXXXXX", TMPDIR => 1 );
    print { $fh } $t->{config} || '';
    close $fh
        or die "Error writing $cfgpath: $!";
    # In case we add a test for failing on missing config file
    unlink $cfgpath if ! $t->{config};

    {
        no warnings 'once';
        $RpmOstreeToolbox::Watch::Config_File = $cfgpath;
    }

    # Invoke tree_file()
    my $actual = eval { RpmOstreeToolbox::Watch::tree_file() };
    my $died = $@;

    # Expecting a fatal error?
    if ($t->{'fatal'}) {
        if ($died) {
            chomp $died;
            $died =~ s/^\S+:\s+//;
            $died =~ s/^$cfgpath:\s+//;
            is $died, $t->{'fatal'}, "$t->{name}: fails with expected error";
        }
        else {
            # This should not happen!
            fail $t->{name};
            diag "expected a fatal error, but function invocation succeeded";
        }
    }

    # Not expecting an error. Compare return value from function.
    else {
        if ($died) {
            # Should not happen!
            fail $t->{name};
            diag "function invocation died unexpectedly: $died";
        }
        else {
            is $actual, $t->{expect}, "$t->{name}: return value";
        }
    }

    # FIXME: check warnings

    unlink $cfgpath;

}

#
# Test definitions. Format is:
#
#     * test name begins with star
#
#     [ini file section name]
#     keyword = value with %(python_string_replacement)s
#
#     > expected-return-value
#     ! or-expected-error-message
#
__END__

* trivial case

[DEFAULT]
tree_file  = foo.json

> foo.json

------------------------------------------------------------------------------

* string substitutions

[DEFAULT]

outputdir   = /home/cloud-user/srv/beta
ostree_repo = %(outputdir)s/repo
rpmostree_cache_dir = %(outputdir)s/cache
os_name     = atomic-foo
os_pretty_name = Atomic Foo
tree_name   = standard
tree_file   = %(outputdir)s/atomic-foo/%(os_name)s.json
arch        = x86_64

> /home/cloud-user/srv/beta/atomic-foo/atomic-foo.json

------------------------------------------------------------------------------

* missing value

[DEFAULT]

tree_flie = uh-oh typo alert

! No value for 'tree_file'

------------------------------------------------------------------------------

* tree_file not in DEFAULT

[somethingelse]
tree_file = sdfsdfsdf

! No value for 'tree_file'

------------------------------------------------------------------------------

* substitution with missing value

[DEFAULT]
tree_file = this is ok but %(that)s is not

! No setting for 'that' in tree_file value 'this is ok but %(that)s is not'
