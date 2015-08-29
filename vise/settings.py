#!/usr/bin/env python
# vim:fileencoding=utf-8
# License: GPL v3 Copyright: 2015, Kovid Goyal <kovid at kovidgoyal.net>

import os
import apsw
import json
import errno
from base64 import standard_b64decode, standard_b64encode
from collections import defaultdict

from PyQt5.Qt import QWebEngineProfile, QApplication

from .constants import config_dir, appname, cache_dir, str_version


def to_json(obj):
    if isinstance(obj, bytearray):
        return {'__class__': 'bytearray',
                '__value__': standard_b64encode(bytes(obj)).decode('ascii')}
    raise TypeError(repr(obj) + ' is not JSON serializable')


def from_json(obj):
    cls = obj.get('__class__')
    if cls == 'bytearray':
        return bytearray(standard_b64decode(obj['__value__']))
    return obj


class DynamicPrefs:

    def __init__(self, name):
        self.path = os.path.join(config_dir, '%s.sqlite' % name)
        self._conn = None
        self._cache = {}
        self.defaults = defaultdict(lambda: None)
        self.pending_commits = {}
        self._buffer_commits = False

    @property
    def conn(self):
        if self._conn is None:
            self._conn = apsw.Connection(self.path)
            c = self._conn.cursor()
            uv = next(c.execute('PRAGMA user_version'))[0]
            if uv == 0:
                c.execute('CREATE TABLE prefs (id INTEGER PRIMARY KEY, name TEXT NOT NULL, value TEXT NOT NULL, UNIQUE(name)); PRAGMA user_version=1;')
            c.close()
        return self._conn

    def __getitem__(self, name):
        try:
            return self._cache[name]
        except KeyError:
            try:
                val = next(self.conn.cursor().execute('SELECT value FROM prefs WHERE name=?', (name,)))[0]
                val = json.loads(val, object_hook=from_json)
            except StopIteration:
                val = self.defaults[name]
            self._cache[name] = val
            return val

    def __setitem__(self, name, val):
        if self._buffer_commits:
            self.pending_commits[name] = val
            return
        c = self.conn.cursor()
        if val == self.defaults[name]:
            c.execute('DELETE FROM prefs WHERE name=?', (name,))
        else:
            val = json.dumps(val, ensure_ascii=False, indent=2, default=to_json)
            c.execute('INSERT or REPLACE INTO prefs(name, value) VALUES (?, ?)', (name, val))

    @property
    def buffer_commits(self):
        return self._buffer_commits

    @buffer_commits.setter
    def buffer_commits(self, val):
        if val:
            self._buffer_commits = True
        else:
            self._buffer_commits = False
            with self.conn:
                for k, v in self.pending_commits.items():
                    self[k] = v

    def __enter__(self):
        self.buffer_commits = True
        return self

    def __exit__(self, *args):
        self.buffer_commits = False

gprefs = DynamicPrefs('gui-dynamic')


def safe_makedirs(path):
    try:
        os.makedirs(path)
    except EnvironmentError as e:
        if e.errno != errno.EEXIST:
            raise


def create_profile(parent=None, private=False):
    if parent is None:
        parent = QApplication.instance()
    if private:
        ans = QWebEngineProfile(parent)
    else:
        ans = QWebEngineProfile(appname, parent)
        ans.setCachePath(os.path.join(cache_dir, appname, 'cache'))
        safe_makedirs(ans.cachePath())
        ans.setPersistentStoragePath(os.path.join(cache_dir, appname, 'storage'))
        safe_makedirs(ans.persistentStoragePath())
    ans.setHttpUserAgent(ans.httpUserAgent().replace('QtWebEngine/', '%s/%s QtWebEngine/' % (appname, str_version)))
    return ans

_profile = None


def profile():
    global _profile
    if _profile is None:
        _profile = create_profile()
    return _profile
