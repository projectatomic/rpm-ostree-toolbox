FROM fedora:20
RUN cd /etc/yum.repos.d && curl -O http://copr-fe.cloud.fedoraproject.org/coprs/walters/rpm-ostree/repo/fedora-20-i386/walters-rpm-ostree-fedora-20-i386.repo
RUN yum -y update  #nocache20140522.0
# Copies of selected dependencies so we're not doing a huge transaction locally
RUN yum -y install kernel gjs /usr/bin/guestmount libguestfs-xfs ostree #nocache20140522.0
RUN yum -y install strace # Random debugging bits
RUN depmod $(cd /lib/modules && echo *)   # Not sure why this isn't run
ADD @PACKAGE@ /var/tmp/@PACKAGE@
RUN yum -y localinstall /var/tmp/@PACKAGE@
RUN mv /usr/bin/rpm-ostree-toolbox{,.real}
ADD rpm-ostree-toolbox-docker-wrapper /usr/bin/rpm-ostree-toolbox
ENTRYPOINT ["rpm-ostree-toolbox"]
