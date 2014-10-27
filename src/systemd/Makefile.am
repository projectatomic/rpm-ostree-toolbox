EXTRA_DIST = \
	$(srcdir)/src/systemd/rpm-ostree-toolbox-build-monitor@.service \
	$(srcdir)/src/systemd/rpm-ostree-toolbox-git-monitor@.service \
	$(srcdir)/src/systemd/rpm-ostree-toolbox-git-monitor.socket \
	$(srcdir)/src/systemd/rpm-ostree-toolbox-kinit@.service \
	$(srcdir)/src/systemd/rpm-ostree-toolbox-kinit@.timer \
	$(srcdir)/src/systemd/rpm-ostree-toolbox-watch@.service

SYSTEMD_UNIT_DIR = $(prefix)/lib/systemd/system

install-systemd: $(EXTRA_DIST)
	$(MKDIR_P)                    $(DESTDIR)$(SYSTEMD_UNIT_DIR)
	$(INSTALL_DATA) $(EXTRA_DIST) $(DESTDIR)$(SYSTEMD_UNIT_DIR)/

install-data-local: install-systemd
