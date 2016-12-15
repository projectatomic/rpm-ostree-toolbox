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
baseurl=https://pkg.jenkins.io/redhat
gpgcheck=1
EOF
rpm --import https://pkg.jenkins.io/redhat/jenkins.io.key
yum -y install nginx supervisor \
    rpm-ostree-toolbox rpm-ostree ostree \
    jenkins java


