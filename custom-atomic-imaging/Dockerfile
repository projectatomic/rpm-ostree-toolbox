FROM projectatomic/custom-atomic-imager-base
ENV container docker
VOLUME ["/srv"]
EXPOSE 8080
ADD supervisord.conf /etc/supervisord.conf
ADD jenkins.sh /usr/bin/jenkins-run
ADD jenkins-print-password.sh /usr/bin/jenkins-print-password
CMD ["supervisord", "-n"]
