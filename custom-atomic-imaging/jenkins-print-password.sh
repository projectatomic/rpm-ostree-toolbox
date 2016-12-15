#!/usr/bin/bash
set -euo pipefail
pwfile=/srv/jenkins/secrets/initialAdminPassword
while true; do
    if test -f ${pwfile}; then
	echo -n "Jenkins password: " && cat ${pwfile}
	exit 0
    fi
    sleep 1
done
