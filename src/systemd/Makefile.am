EXTRA_DIST = \
	src/systemd/rpm-ostree-build-monitor.service \
	src/systemd/rpm-ostree-kinit.service \
	src/systemd/rpm-ostree-kinit.timer

SYSTEMD_UNIT_DIR = $(prefix)/lib/systemd/system

install-systemd: $(EXTRA_DIST)
	$(MKDIR_P)                    $(DESTDIR)$(SYSTEMD_UNIT_DIR)
	$(INSTALL_DATA) $(EXTRA_DIST) $(DESTDIR)$(SYSTEMD_UNIT_DIR)/

uninstall-systemd:
	$(RM) -f $(DESTDIR)$(SYSTEMD_UNIT_DIR)/rpm-ostree-build-monitor.service
	$(RM) -f $(DESTDIR)$(SYSTEMD_UNIT_DIR)/rpm-ostree-kinit.service
	$(RM) -f $(DESTDIR)$(SYSTEMD_UNIT_DIR)/rpm-ostree-kinit.timer
	$(RMDIR) $(DESTDIR)$(SYSTEMD_UNIT_DIR) || :

install-data-local: install-systemd
uninstall-local:  uninstall-systemd
