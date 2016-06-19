# Copyright (C) 2014-2016  Codethink Limited
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

import yaml
import os
from app import chdir, config, log, exit
from defaults import Defaults


class Morphs(object):

    def __init__(self, directory='.'):
        '''Load all definitions from a directory tree.'''
        self._data = {}
        self._trees = {}
        self.defaults = Defaults()
        config['cpu'] = self.defaults.cpus.get(config['arch'], config['arch'])
        self.parse_files(directory)

    def parse_files(self, directory):
        with chdir(directory):
            for dirname, dirnames, filenames in os.walk('.'):
                filenames.sort()
                dirnames.sort()
                if '.git' in dirnames:
                    dirnames.remove('.git')
                for filename in filenames:
                    if filename.endswith(('.def', '.morph')):
                        path = os.path.join(dirname, filename)
                        data = self._load(path)
                        if data is not None:
                            data['path'] = self._demorph(path[2:])
                            self._fix_keys(data)
                            self._tidy_and_insert_recursively(data)

    def _load(self, path):
        '''Load a single definition file as a dict.

        The file is assumed to be yaml, and we insert the provided path into
        the dict keyed as 'path'.

        '''
        try:
            with open(path) as f:
                text = f.read()
            contents = yaml.safe_load(text)
        except yaml.YAMLError, exc:
            exit('DEFINITIONS', 'ERROR: could not parse %s' % path, exc)
        except:
            log('DEFINITIONS', 'WARNING: Unexpected error loading', path)
            return None

        if type(contents) is not dict:
            log('DEFINITIONS', 'WARNING: %s contents is not dict:' % path,
                str(contents)[0:50])
            return None
        return contents

    def _tidy_and_insert_recursively(self, item):
        '''Insert a definition and its contents into the dictionary.

        Takes a dict containing the content of a definition file.

        Inserts the definitions referenced or defined in the
        'build-depends' and 'contents' keys of `definition` into the
        dictionary, and then inserts `definition` itself into the
        dictionary.

        '''
        # handle morph syntax oddities...
        for index, component in enumerate(item.get('build-depends', [])):
            self._fix_keys(component)
            item['build-depends'][index] = self._insert(component)

        # The 'contents' field in the internal data model corresponds to the
        # 'chunks' field in a stratum .morph file, or the 'strata' field in a
        # system .morph file.
        item['contents'] = item.get('contents', [])
        item['contents'] += item.pop('chunks', []) + item.pop('strata', [])

        lookup = {}
        for index, component in enumerate(item['contents']):
            self._fix_keys(component, item['path'])
            lookup[component['name']] = component['path']
            if component['name'] == item['name']:
                log(item, 'WARNING: %s contains' % item['path'], item['name'])

            for x, it in enumerate(component.get('build-depends', [])):
                if it not in lookup:
                    # it is defined as a build depend, but hasn't actually been
                    # defined yet...
                    dependency = {'name': it}
                    self._fix_keys(dependency,  item['path'])
                    lookup[it] = dependency['path']
                component['build-depends'][x] = lookup[it]

            component['build-depends'] = (item.get('build-depends', []) +
                                          component.get('build-depends', []))

            splits = component.get('artifacts', [])
            item['contents'][index] = {self._insert(component): splits}

        return self._insert(item)

    def _fix_keys(self, item, base=None):
        '''Normalizes keys for a definition dict and its contents

        Some definitions have a 'morph' field which is a relative path. Others
        only have a 'name' field, which has no directory part. A few do not
        have a 'name'

        This sets our key to be 'path', and fixes any missed 'name' to be
        the same as 'path' but replacing '/' by '-'

        '''
        if item.get('morph'):
            if not os.path.isfile(item.get('morph')):
                log('DEFINITION', 'WARNING: missing definition', item['morph'])
            item['path'] = self._demorph(item.pop('morph'))

        if 'path' not in item:
            if 'name' not in item:
                exit(item, 'ERROR: no path, no name?')
            if config.get('artifact-version') in range(0, 4):
                item['path'] = item['name']
            else:
                item['path'] = os.path.join(self._demorph(base), item['name'])
                if os.path.isfile(item['path'] + '.morph'):
                    # morph file exists, but is not mentioned in stratum
                    # so we ignore it
                    log(item, 'WARNING: ignoring', item['path'] + '.morph')
                    item['path'] += '.default'

        item['path'] = self._demorph(item['path'])
        item.setdefault('name', item['path'].replace('/', '-'))

        if item['name'] == config['target']:
            config['target'] = item['path']

        n = self._demorph(os.path.basename(item['name']))
        p = self._demorph(os.path.basename(item['path']))
        if os.path.splitext(p)[0] not in n:
            if config.get('check-definitions') == 'warn':
                log('DEFINITIONS',
                    'WARNING: %s has wrong name' % item['path'], item['name'])
            if config.get('check-definitions') == 'exit':
                exit('DEFINITIONS',
                     'ERROR: %s has wrong name' % item['path'], item['name'])

        for system in (item.get('systems', []) + item.get('subsystems', [])):
            self._fix_keys(system)

    def _insert(self, new_def):
        '''Insert a new definition into the dictionary, return the key.

        Takes a dict representing a single definition.

        If a definition with the same 'path' doesn't exist, just add
        `new_def` to the dictionary.

        If a definition with the same 'path' already exists, extend the
        existing definition with the contents of `new_def` unless it
        and the new definition both contain a 'ref'. If any keys are
        duplicated in the existing definition, output a warning.

        '''
        item = self._data.get(new_def['path'])
        if item:
            if (item.get('ref') is None or new_def.get('ref') is None):
                for key in new_def:
                    item[key] = new_def[key]

            for key in new_def:
                if item.get(key) != new_def[key]:
                    log(new_def, 'WARNING: multiple definitions of', key)
                    log(new_def, '%s | %s' % (item.get(key), new_def[key]))
        else:
            self._data[new_def['path']] = new_def

        return new_def['path']

    def _demorph(self, path):
        if config.get('artifact-version', 0) not in range(0, 4):
            if path.endswith('.morph'):
                path = path.rpartition('.morph')[0]
        return path
