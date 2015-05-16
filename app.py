# Copyright (C) 2014-2015  Codethink Limited
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; version 2 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# =*= License: GPL-2 =*=

import contextlib
import os
import datetime
import shutil
from subprocess import call, check_output
from multiprocessing import cpu_count
from repos import get_upstream_ver as version


xdg_cache_home = os.environ.get('XDG_CACHE_HOME') or \
                 os.path.join(os.path.expanduser('~'), '.cache')
settings = {}


def log(component, message='', data=''):
    ''' Print a timestamped log. '''
    name = component
    try:
        name = component['name']
    except:
        pass

    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_entry = '%s [%s] %s %s\n' % (timestamp, name, message, data)
    print(log_entry),


def log_env(log, message=''):
    with open(log, "a") as logfile:
        for key in sorted(os.environ.keys()):
            msg = os.environ[key] if 'PASSWORD' not in key else '(hidden)'
            logfile.write('%s=%s\n' % (key, msg))
        logfile.write(message + '\n')
        logfile.flush()


def exit(component=False, message='', data=''):
    if component:
        log(component, message, data)
    settings['noisy'] = False
    raise SystemExit


@contextlib.contextmanager
def setup(target, arch):
    try:
        settings['noisy'] = True
        if call(['git', 'describe']):
            exit(target, 'ERROR: this directory is not a git repo')

        settings['defdir'] = os.getcwd()
        settings['def-ver'] = version('.')
        settings['target'] = target
        settings['arch'] = arch
        settings['no-ccache'] = False
        settings['no-distcc'] = True
        settings['base-path'] = ['/usr/bin', '/bin', '/usr/sbin', '/sbin']

        settings['ccache_dir'] = os.path.join(xdg_cache_home, 'ybd', 'ccache')
        settings['cache-server'] = 'http://git.baserock.org:8080/1.0/sha1s?'
        settings['tar-url'] = 'http://git.baserock.org/tarballs'
        settings['base'] = os.path.expanduser('~/.ybd/')
        if os.path.exists('/src'):
            settings['base'] = '/src'

        settings['caches'] = os.path.join(settings['base'], 'cache')
        settings['artifacts'] = os.path.join(settings['caches'],
                                             'ybd-artifacts')
        settings['gits'] = os.path.join(settings['caches'], 'gits')

        settings['tmp'] = os.path.join(settings['base'], 'tmp')
        settings['staging'] = os.path.join(settings['tmp'], 'staging')
        settings['deployment'] = os.path.join(settings['tmp'], 'deployments')

        for directory in ['base', 'caches', 'artifacts', 'gits',
                          'tmp', 'staging', 'ccache_dir', 'deployment']:
            if not os.path.exists(settings[directory]):
                os.makedirs(settings[directory])

        # git replace means we can't trust that just the sha1 of a branch
        # is enough to say what it contains, so we turn it off by setting
        # the right flag in an environment variable.
        os.environ['GIT_NO_REPLACE_OBJECTS'] = '1'

        settings['max-jobs'] = max(int(cpu_count() * 1.5 + 0.5), 1)
        settings['server'] = 'http://192.168.56.102:8000/'
        yield

    finally:
        if settings['noisy']:
            log(target, 'Finished')


@contextlib.contextmanager
def chdir(dirname=None):
    currentdir = os.getcwd()
    try:
        if dirname is not None:
            os.chdir(dirname)
        yield
    finally:
        os.chdir(currentdir)


@contextlib.contextmanager
def timer(this, start_message=''):
    starttime = datetime.datetime.now()
    log(this, start_message)
    try:
        yield
    finally:
        td = datetime.datetime.now() - starttime
        hours, remainder = divmod(int(td.total_seconds()), 60*60)
        minutes, seconds = divmod(remainder, 60)
        td_string = "%02d:%02d:%02d" % (hours, minutes, seconds)
        if settings['noisy']:
            log(this, 'Elapsed time', td_string)
