#!/usr/bin/bash
set -xeuo pipefail
yum -y install epel-release
cat > /etc/yum.repos.d/atomic7-testing.repo <<EOF
[atomic7-testing]
baseurl=https://cbs.centos.org/repos/atomic7-testing/x86_64/os/
gpgcheck=0
EOF
cat > /etc/yum.repos.d/jenkins.repo <<EOF
[jenkins]
name=Jenkins
baseurl=http://pkg.jenkins.io/redhat
gpgcheck=1
EOF
yum -y install nginx \
    rpm-ostree-toolbox rpm-ostree ostree \
    jenkins

cd /srv
ostree --repo=repo
git clone https://github.com/CentOS/sig-atomic-buildscripts
cat > Makefile <<EOF
tree:
	
EOF


