# Software License Agreement (BSD License)
#
# Copyright (c) 2010, Willow Garage, Inc.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
#
#  * Redistributions of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer.
#  * Redistributions in binary form must reproduce the above
#    copyright notice, this list of conditions and the following
#    disclaimer in the documentation and/or other materials provided
#    with the distribution.
#  * Neither the name of Willow Garage, Inc. nor the names of its
#    contributors may be used to endorse or promote products derived
#    from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
# FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
# COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
# INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
# BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
# LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
# ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

import os
import copy
import shlex
import subprocess
import logging

from vcs_base import VcsError

def normalized_rel_path(path, basepath):
    """
    If path is absolute, return relative path to it from
    basepath. If relative, return it normalized.

    :param path: an absolute or relative path
    :param basepath: if path is absolute, shall be made relative to this
    :returns: a normalized relative path
    """
    # gracefully ignore invalid input absolute path + no basepath
    if path is None:
        return basepath
    if os.path.isabs(path) and basepath is not None:
        return os.path.normpath(os.path.relpath(os.path.realpath(path), os.path.realpath(basepath)))
    return os.path.normpath(path)


def sanitized(arg):
    """
    makes sure a composed command to be executed via shell was not injected.

    A composed command would be like "ls %s"%foo.
    In this example, foo could be "; rm -rf *"
    sanitized raises an Error when it detects such an attempt
    
    :raises VcsError: on injection attempts
    """
    if arg is None or arg.strip() == '':
        return ''
    arg = str(arg.strip('"').strip())
    safe_arg = '"%s"'%arg
    # this also detects some false positives, like bar"";foo
    if '"' in arg:
        if (len(shlex.split(safe_arg, False, False)) != 1):
            raise VcsError("Shell injection attempt detected: >%s< = %s"%(arg, shlex.split(safe_arg, False, False)))
    return safe_arg


def _discard_line(line):
    # the most common feedback lines of scms. We don't care about those. We let through anything unusual only.
    discard_prefixes = ["adding ", "added ", "updating ", "requesting ", "pulling from ",
                        "searching for ", "(", "no changes found",
                        "0 files",
                        "A  ", "D  ", "U  ",
                        "At revision", "Path: ", "First,",
                        "Installing", "Using ",
                        "No ", "Tree ",
                        "All ",
                        "+N  ", "-D  ", " M  ", " M* ", "RM" # bzr
                        ]
    for pre in discard_prefixes:
        if line.startswith(pre):
            return True
    return False


def run_shell_command(cmd, cwd=None, shell=False, us_env=True, show_stdout=False, verbose=False):
    """
    executes a command and hides the stdout output, loggs stderr
    output when command result is not zero. Make sure to sanitize
    arguments in the command.

    :param cmd: A string to execute.
    :param shell: Whether to use os shell.
    this is DANGEROUS, as vulnerable to shell injection.
    :returns: ( returncode, stdout, stderr)
    :raises: VcsError on OSError
    """
    try:
        env = copy.copy(os.environ)
        if us_env:
            env ["LANG"] = "en_US.UTF-8"
        proc = subprocess.Popen(cmd,
                                shell=shell,
                                cwd=cwd,
                                stderr=subprocess.PIPE,
                                stdout=subprocess.PIPE,
                                env=env)
        # when we read output in while loop, it will not be returned
        # in communicate()
        stderr_buf = []
        stdout_buf = []
        if verbose or show_stdout:
            # listen to stdout and print
            while True:
                line = proc.stdout.readline()
                if line != '':
                    if verbose or not _discard_line(line):
                        print(line),
                        stdout_buf.append(line)
                line2 = proc.stderr.readline()
                if line2 != '':
                    if verbose or not _discard_line(line2):
                        print(line2),
                        stderr_buf.append(line2)
                if ((not line and not line2) or proc.returncode is not None):
                    break
        (stdout, stderr) = proc.communicate()
        stdout_buf.append(stdout)
        stdout = "\n".join(stdout_buf)
        stderr_buf.append(stderr)
        stderr = "\n".join(stderr_buf)
        message = None
        if proc.returncode != 0 and stderr is not None and stderr != '':
            logger = logging.getLogger('vcstools')
            message = "Command failed: '%s'"%(cmd)
            if cwd is not None:
                message += "\n run at: '%s'"%(cwd)
            message += "\n errcode: %s:\n%s"%(proc.returncode, stderr)
            logger.warn(message)
        result = stdout
        if result is not None:
            result = result.rstrip()
        return (proc.returncode, result, message)
    except OSError as ose:
        logger = logging.getLogger('vcstools')
        message = "Command failed with OSError. '%s' <%s, %s>:\n%s"%(cmd, shell, cwd, ose)
        logger.error(message)
        raise VcsError(message)