#!/usr/bin/env python3
#
# Copyright (C) 2014  Codethink Limited
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
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#
# =*= License: GPL-2 =*=

import os
import app
import re
from subprocess import call
from subprocess import check_output
import string
import definitions


def get_repo_url(this):
    url = this['repo']
    url = url.replace('upstream:', 'git://git.baserock.org/delta/')
    url = url.replace('baserock:baserock/',
                      'git://git.baserock.org/baserock/baserock/')
    url = url.replace('freedesktop:', 'git://anongit.freedesktop.org/')
    url = url.replace('github:', 'git://github.com/')
    url = url.replace('gnome:', 'git://git.gnome.org')
    if url.endswith('.git'):
        url = url[:-4]
    return url


def quote_url(url):
    ''' Convert URIs to strings that only contain digits, letters, % and _.

    NOTE: When changing the code of this function, make sure to also apply
    the same to the quote_url() function of lorry. Otherwise the git tarballs
    generated by lorry may no longer be found by morph.

    '''
    valid_chars = string.digits + string.letters + '%_'
    transl = lambda x: x if x in valid_chars else '_'
    return ''.join([transl(x) for x in url])


def get_repo_name(this):
    return quote_url(get_repo_url(this))
#    return re.split('[:/]', this['repo'])[-1]


def get_tree(this):
    tree = None
    defs = definitions.Definitions()

    if defs.lookup(this, 'repo') == []:
        return tree

    if defs.lookup(this, 'git') == []:
        this['git'] = (os.path.join(app.config['gits'],
                       get_repo_name(this)))

    if defs.version(this):
        ref = defs.version(this)

    if defs.lookup(this, 'ref'):
        ref = defs.lookup(this, 'ref')

    try:
        if not os.path.exists(this['git']):
            mirror(this)
        with app.chdir(this['git']), open(os.devnull, "w") as fnull:
            if call(['git', 'rev-parse', ref + '^{object}'],
                    stdout=fnull,
                    stderr=fnull):
                # can't resolve this ref. is it upstream?
                call(['git', 'fetch', 'origin'],
                     stdout=fnull,
                     stderr=fnull)
                if call(['git', 'rev-parse', ref + '^{object}'],
                        stdout=fnull,
                        stderr=fnull):
                    app.log(this, 'ERROR: ref is not unique or missing', ref)
                    raise SystemExit

            tree = check_output(['git', 'rev-parse', ref + '^{tree}'],
                                universal_newlines=True)[0:-1]

    except:
            # either we don't have a git dir, or ref is not unique
            # or ref does not exist

        app.log(this, 'ERROR: could not find tree for ref', ref)
        raise SystemExit

    return tree


def copy_repo(repo, destdir):
    '''Copies a cached repository into a directory using cp.

    This also fixes up the repository afterwards, so that it can contain
    code etc.  It does not leave any given branch ready for use.

    '''

    # core.bare should be false so that git believes work trees are possible
    # we do not want the origin remote to behave as a mirror for pulls
    # we want a traditional refs/heads -> refs/remotes/origin ref mapping
    # set the origin url to the cached repo so that we can quickly clean up
    # by packing the refs, we can then edit then en-masse easily
    call(['cp', '-a', repo, os.path.join(destdir, '.git')])
    call(['git', 'config', 'core.bare', 'false'])
    call(['git', 'config', '--unset', 'remote.origin.mirror'])
    with open(os.devnull, "w") as fnull:
        call(['git', 'config', 'remote.origin.fetch',
              '+refs/heads/*:refs/remotes/origin/*'],
             stdout=fnull,
             stderr=fnull)
    call(['git',  'config', 'remote.origin.url', repo])
    call(['git',  'pack-refs', '--all', '--prune'])

    # turn refs/heads/* into refs/remotes/origin/* in the packed refs
    # so that the new copy behaves more like a traditional clone.
    with open(os.path.join(destdir, ".git", "packed-refs"), "r") as ref_fh:
        pack_lines = ref_fh.read().split("\n")
    with open(os.path.join(destdir, ".git", "packed-refs"), "w") as ref_fh:
        ref_fh.write(pack_lines.pop(0) + "\n")
        for refline in pack_lines:
            if ' refs/remotes/' in refline:
                continue
            if ' refs/heads/' in refline:
                sha, ref = refline[:40], refline[41:]
                if ref.startswith("refs/heads/"):
                    ref = "refs/remotes/origin/" + ref[11:]
                refline = "%s %s" % (sha, ref)
            ref_fh.write("%s\n" % (refline))
    # Finally run a remote update to clear up the refs ready for use.
    with open(os.devnull, "w") as fnull:
        call(['git', 'remote', 'update', 'origin', '--prune'],
             stdout=fnull,
             stderr=fnull)


def mirror(this):
    # try tarball first
    try:
        os.makedirs(this['git'])
        with app.chdir(this['git']):
            app.log(this, 'Fetching tarball')
            repo_url = get_repo_url(this)
            tar_file = quote_url(repo_url) + '.tar'
            tar_url = os.path.join("http://git.baserock.org/tarballs",
                                   tar_file)
            with open(os.devnull, "w") as fnull:
                call(['wget', tar_url], stdout=fnull, stderr=fnull)
                call(['tar', 'xf', tar_file], stdout=fnull, stderr=fnull)
                call(['git', 'config', 'remote.origin.url', repo_url],
                     stdout=fnull, stderr=fnull)
                call(['git', 'config', 'remote.origin.mirror', 'true'],
                     stdout=fnull, stderr=fnull)
                if call(['git', 'config', 'remote.origin.fetch',
                         '+refs/*:refs/*'],
                        stdout=fnull, stderr=fnull) != 0:
                    raise BaseException('Did not get a valid git repo')
    except:
        app.log(this, 'Using git clone', get_repo_url(this))
        try:
            with open(os.devnull, "w") as fnull:
                call(['git', 'clone', '--mirror', '-n', get_repo_url(this),
                      this['git']], stdout=fnull, stderr=fnull)
        except:
            app.log(this, 'ERROR: failed to clone', get_repo_url(this))
            raise SystemExit

    app.log(this, 'Git repo is mirrored at', this['git'])


def checkout(this):
    # checkout the required version of this from git
    with app.chdir(this['build']):
        this['tree'] = get_tree(this)
        copy_repo(this['git'], this['build'])
        with open(os.devnull, "w") as fnull:
            if call(['git', 'checkout', this['ref']],
                    stdout=fnull, stderr=fnull) != 0:
                app.log(this, 'ERROR: git checkout failed for', this['tree'])
                raise SystemExit


