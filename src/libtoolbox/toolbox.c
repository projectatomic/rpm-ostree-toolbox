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

#include "config.h"

#include "toolbox.h"

#include <unistd.h>
#include <sys/mount.h>
#include <sys/syscall.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <time.h>
#include <sys/wait.h>
#include <errno.h>
#include <string.h>

gboolean
toolbox_unshare_namespaces (ToolboxNamespaceFlags       flags,
                            GError                    **error)
{
  int uflags = 0;
  gboolean ret = FALSE;

  if (flags & TOOLBOX_NAMESPACE_MOUNT)
    uflags |= CLONE_NEWNS;
  if (flags & TOOLBOX_NAMESPACE_PID)
    uflags |= CLONE_NEWPID;
  if (unshare (uflags) == -1)
    {
      int errsv = errno;
      g_set_error (error, G_IO_ERROR, G_IO_ERROR_FAILED,
                   "unshare(%d): %s",
                   uflags, g_strerror (errsv));
      goto out;
    }

  ret = TRUE;
 out:
  return ret;
}

gboolean
toolbox_remount_rootfs_private (GError               **error)
{
  gboolean ret = FALSE;

  if (mount (NULL, "/", "none", MS_PRIVATE | MS_REC, NULL) == -1)
    {
      int errsv = errno;
      g_set_error (error, G_IO_ERROR, G_IO_ERROR_FAILED,
                   "mount(/, MS_PRIVATE | MS_REC): %s",
                   g_strerror (errsv));
      goto out;
    }

  ret = TRUE;
 out:
  return ret;
}

gboolean
toolbox_set_file_time_0 (GFile *path, GCancellable *cancellable, GError **error)
{
  gboolean ret = FALSE;
  char *pathstr = g_file_get_path (path);
  struct timeval tvs[2];

  tvs[0].tv_sec = 0;
  tvs[0].tv_usec = 0;
  tvs[1].tv_sec = 0;
  tvs[1].tv_usec = 0;
  
  if (utimes (pathstr, tvs) == -1)
    {
      int errsv = errno;
      g_set_error (error, G_IO_ERROR, G_IO_ERROR_FAILED,
                   "utimes(%s): %s", pathstr, g_strerror (errsv));
      goto out;
    }

  ret = TRUE;
 out:
  g_free (pathstr);
  return ret;
}
