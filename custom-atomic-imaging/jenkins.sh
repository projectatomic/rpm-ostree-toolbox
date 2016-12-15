#!/usr/bin/bash
set -xeuo pipefail
exec /usr/bin/java -DJENKINS_HOME=/srv/jenkins -jar /usr/lib/jenkins/jenkins.war --logfile=/var/log/jenkins/jenkins.log --webroot=/var/cache/jenkins/war
