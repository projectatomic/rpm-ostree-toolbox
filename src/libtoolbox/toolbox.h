/* -*- mode: C; c-file-style: "gnu"; indent-tabs-mode: nil; -*-
 *
 * Copyright (C) 2014 Colin Walters <walters@redhat.com>
 *
 * This library is free software; you can redistribute it and/or
 * modify it under the terms of the GNU Lesser General Public
 * License as published by the Free Software Foundation; either
 * version 2 of the License, or (at your option) any later version.
 *
 * This library is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
 * Lesser General Public License for more details.
 *
 * You should have received a copy of the GNU Lesser General
 * Public License along with this library; if not, see <http://www.gnu.org/licenses/>.
 */

#pragma once

#include <gio/gio.h>

G_BEGIN_DECLS

typedef enum /*< flags >*/
{
  TOOLBOX_NAMESPACE_MOUNT = (1 << 0),
  TOOLBOX_NAMESPACE_PID = (1 << 1)
} ToolboxNamespaceFlags;

gboolean
toolbox_unshare_namespaces (ToolboxNamespaceFlags  flags,
			    GError               **error);

gboolean
toolbox_remount_rootfs_private (GError               **error);
