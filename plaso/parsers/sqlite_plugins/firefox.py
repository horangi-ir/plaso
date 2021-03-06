# -*- coding: utf-8 -*-
"""This file contains a parser for the Mozilla Firefox history."""

try:
  from pysqlite2 import dbapi2 as sqlite3
except ImportError:
  import sqlite3

from dfdatetime import posix_time as dfdatetime_posix_time

from plaso.containers import events
from plaso.containers import time_events
from plaso.lib import eventdata
from plaso.parsers import sqlite
from plaso.parsers.sqlite_plugins import interface


# Check SQlite version, bail out early if too old.
if sqlite3.sqlite_version_info < (3, 7, 8):
  raise ImportWarning(
      u'FirefoxHistoryParser requires at least SQLite version 3.7.8.')


class FirefoxPlacesBookmarkAnnotationEventData(events.EventData):
  """Firefox bookmark annotation event data.

  Attributes:
    content (str): annotation content.
    title (str): title of the bookmark folder.
    url (str): bookmarked URL.
  """

  DATA_TYPE = u'firefox:places:bookmark_annotation'

  def __init__(self):
    """Initializes event data."""
    super(FirefoxPlacesBookmarkAnnotationEventData, self).__init__(
        data_type=self.DATA_TYPE)
    self.content = None
    self.title = None
    self.url = None


class FirefoxPlacesBookmarkFolderEventData(events.EventData):
  """Firefox bookmark folder event data.

  Attributes:
    title (str): title of the bookmark folder.
  """

  DATA_TYPE = u'firefox:places:bookmark_folder'

  def __init__(self):
    """Initializes event data."""
    super(FirefoxPlacesBookmarkFolderEventData, self).__init__(
        data_type=self.DATA_TYPE)
    self.title = None


class FirefoxPlacesBookmarkEventData(events.EventData):
  """Firefox bookmark event data.

  Attributes:
    bookmark_type (int): bookmark type.
    hostname (str): hostname.
    places_title (str): places title.
    title (str): title of the bookmark folder.
    url (str): bookmarked URL.
    visit_count (int): visit count.
  """

  DATA_TYPE = u'firefox:places:bookmark'

  def __init__(self):
    """Initializes event data."""
    super(FirefoxPlacesBookmarkEventData, self).__init__(
        data_type=self.DATA_TYPE)
    self.host = None
    self.places_title = None
    self.title = None
    self.type = None
    self.url = None
    self.visit_count = None


# TODO: refactor extra attribute.
class FirefoxPlacesPageVisitedEventData(events.EventData):
  """Firefox page visited event data.

  Attributes:
    extra (list[object]): extra event data.
    hostname (str): visited hostname.
    title (str): title of the visited page.
    url (str): URL of the visited page.
    visit_count (int): visit count.
    visit_type (str): transition type for the event.
  """

  DATA_TYPE = u'firefox:places:page_visited'

  def __init__(self):
    """Initializes event data."""
    super(FirefoxPlacesPageVisitedEventData, self).__init__(
        data_type=self.DATA_TYPE)
    self.extra = None
    self.host = None
    self.title = None
    self.url = None
    self.visit_count = None
    self.visit_type = None


class FirefoxDownloadEventData(events.EventData):
  """Firefox download event data.

  Attributes:
    full_path (str): full path of the target of the download.
    mime_type (str): mime type of the download.
    name (str): name of the download.
    received_bytes (int): number of bytes received.
    referrer (str): referrer URL of the download.
    temporary_location (str): temporary location of the download.
    total_bytes (int): total number of bytes of the download.
    url (str): source URL of the download.
  """

  DATA_TYPE = u'firefox:downloads:download'

  def __init__(self):
    """Initializes event data."""
    super(FirefoxDownloadEventData, self).__init__(
        data_type=self.DATA_TYPE)
    self.full_path = None
    self.mime_type = None
    self.name = None
    self.offset = None
    self.received_bytes = None
    self.referrer = None
    self.temporary_location = None
    self.total_bytes = None
    self.url = None


class FirefoxHistoryPlugin(interface.SQLitePlugin):
  """Parses a Firefox history file.

     The Firefox history is stored in a SQLite database file named
     places.sqlite.
  """

  NAME = u'firefox_history'
  DESCRIPTION = u'Parser for Firefox history SQLite database files.'

  # Define the needed queries.
  QUERIES = [
      ((u'SELECT moz_historyvisits.id, moz_places.url, moz_places.title, '
        u'moz_places.visit_count, moz_historyvisits.visit_date, '
        u'moz_historyvisits.from_visit, moz_places.rev_host, '
        u'moz_places.hidden, moz_places.typed, moz_historyvisits.visit_type '
        u'FROM moz_places, moz_historyvisits '
        u'WHERE moz_places.id = moz_historyvisits.place_id'),
       u'ParsePageVisitedRow'),
      ((u'SELECT moz_bookmarks.type, moz_bookmarks.title AS bookmark_title, '
        u'moz_bookmarks.dateAdded, moz_bookmarks.lastModified, '
        u'moz_places.url, moz_places.title AS places_title, '
        u'moz_places.rev_host, moz_places.visit_count, moz_bookmarks.id '
        u'FROM moz_places, moz_bookmarks '
        u'WHERE moz_bookmarks.fk = moz_places.id AND moz_bookmarks.type <> 3'),
       u'ParseBookmarkRow'),
      ((u'SELECT moz_items_annos.content, moz_items_annos.dateAdded, '
        u'moz_items_annos.lastModified, moz_bookmarks.title, '
        u'moz_places.url, moz_places.rev_host, moz_items_annos.id '
        u'FROM moz_items_annos, moz_bookmarks, moz_places '
        u'WHERE moz_items_annos.item_id = moz_bookmarks.id '
        u'AND moz_bookmarks.fk = moz_places.id'),
       u'ParseBookmarkAnnotationRow'),
      ((u'SELECT moz_bookmarks.id, moz_bookmarks.title,'
        u'moz_bookmarks.dateAdded, moz_bookmarks.lastModified '
        u'FROM moz_bookmarks WHERE moz_bookmarks.type = 2'),
       u'ParseBookmarkFolderRow')]

  # The required tables.
  REQUIRED_TABLES = frozenset([
      u'moz_places', u'moz_historyvisits', u'moz_bookmarks',
      u'moz_items_annos'])

  # Cache queries.
  URL_CACHE_QUERY = (
      u'SELECT h.id AS id, p.url, p.rev_host FROM moz_places p, '
      u'moz_historyvisits h WHERE p.id = h.place_id')

  # TODO: move to formatter.
  _BOOKMARK_TYPES = {
      1: u'URL',
      2: u'Folder',
      3: u'Separator',
  }

  def ParseBookmarkAnnotationRow(
      self, parser_mediator, row, query=None, **unused_kwargs):
    """Parses a bookmark annotation row.

    Args:
      parser_mediator (ParserMediator): mediates interactions between parsers
          and other components, such as storage and dfvfs.
      row (sqlite3.Row): row.
      query (Optional[str]): query.
    """
    # Note that pysqlite does not accept a Unicode string in row['string'] and
    # will raise "IndexError: Index must be int or string".

    event_data = FirefoxPlacesBookmarkAnnotationEventData()
    event_data.content = row['content']
    event_data.offset = row['id']
    event_data.query = query
    event_data.title = row['title']
    event_data.url = row['url']

    timestamp = row['dateAdded']
    if timestamp:
      date_time = dfdatetime_posix_time.PosixTimeInMicroseconds(
          timestamp=timestamp)
      event = time_events.DateTimeValuesEvent(
          date_time, eventdata.EventTimestamp.ADDED_TIME)
      parser_mediator.ProduceEventWithEventData(event, event_data)

    timestamp = row['lastModified']
    if timestamp:
      date_time = dfdatetime_posix_time.PosixTimeInMicroseconds(
          timestamp=timestamp)
      event = time_events.DateTimeValuesEvent(
          date_time, eventdata.EventTimestamp.MODIFICATION_TIME)
      parser_mediator.ProduceEventWithEventData(event, event_data)

  def ParseBookmarkFolderRow(
      self, parser_mediator, row, query=None, **unused_kwargs):
    """Parses a bookmark folder row.

    Args:
      parser_mediator (ParserMediator): mediates interactions between parsers
          and other components, such as storage and dfvfs.
      row (sqlite3.Row): row.
      query (Optional[str]): query.
    """
    # Note that pysqlite does not accept a Unicode string in row['string'] and
    # will raise "IndexError: Index must be int or string".

    event_data = FirefoxPlacesBookmarkFolderEventData()
    event_data.offset = row['id']
    event_data.query = query
    event_data.title = row['title'] or u'N/A'

    timestamp = row['dateAdded']
    if timestamp:
      date_time = dfdatetime_posix_time.PosixTimeInMicroseconds(
          timestamp=timestamp)
      event = time_events.DateTimeValuesEvent(
          date_time, eventdata.EventTimestamp.ADDED_TIME)
      parser_mediator.ProduceEventWithEventData(event, event_data)

    timestamp = row['lastModified']
    if timestamp:
      date_time = dfdatetime_posix_time.PosixTimeInMicroseconds(
          timestamp=timestamp)
      event = time_events.DateTimeValuesEvent(
          date_time, eventdata.EventTimestamp.MODIFICATION_TIME)
      parser_mediator.ProduceEventWithEventData(event, event_data)

  def ParseBookmarkRow(
      self, parser_mediator, row, query=None, **unused_kwargs):
    """Parses a bookmark row.

    Args:
      parser_mediator (ParserMediator): mediates interactions between parsers
          and other components, such as storage and dfvfs.
      row (sqlite3.Row): row.
      query (Optional[str]): query.
    """
    event_data = FirefoxPlacesBookmarkEventData()
    event_data.host = row['rev_host'] or u'N/A'
    event_data.offset = row['id']
    event_data.places_title = row['places_title']
    event_data.query = query
    event_data.title = row['bookmark_title']
    event_data.type = self._BOOKMARK_TYPES.get(row['type'], u'N/A')
    event_data.url = row['url']
    event_data.visit_count = row['visit_count']

    timestamp = row['dateAdded']
    if timestamp:
      date_time = dfdatetime_posix_time.PosixTimeInMicroseconds(
          timestamp=timestamp)
      event = time_events.DateTimeValuesEvent(
          date_time, eventdata.EventTimestamp.ADDED_TIME)
      parser_mediator.ProduceEventWithEventData(event, event_data)

    timestamp = row['lastModified']
    if timestamp:
      date_time = dfdatetime_posix_time.PosixTimeInMicroseconds(
          timestamp=timestamp)
      event = time_events.DateTimeValuesEvent(
          date_time, eventdata.EventTimestamp.MODIFICATION_TIME)
      parser_mediator.ProduceEventWithEventData(event, event_data)

  def ParsePageVisitedRow(
      self, parser_mediator, row, cache=None, database=None, query=None,
      **unused_kwargs):
    """Parses a page visited row.

    Args:
      parser_mediator (ParserMediator): mediates interactions between parsers
          and other components, such as storage and dfvfs.
      row (sqlite3.Row): row.
      cache (SQLiteCache): cache.
      database (SQLiteDatabase): database.
      query (Optional[str]): query.
    """
    # Note that pysqlite does not accept a Unicode string in row['string'] and
    # will raise "IndexError: Index must be int or string".

    # TODO: make extra conditional formatting.
    extras = []
    if row['from_visit']:
      extras.append(u'visited from: {0:s}'.format(
          self._GetUrl(row['from_visit'], cache, database)))

    if row['hidden'] == u'1':
      extras.append(u'(url hidden)')

    if row['typed'] == u'1':
      extras.append(u'(directly typed)')
    else:
      extras.append(u'(URL not typed directly)')

    event_data = FirefoxPlacesPageVisitedEventData()
    event_data.host = self._ReverseHostname(row['rev_host'])
    event_data.offset = row['id']
    event_data.query = query
    event_data.title = row['title']
    event_data.url = row['url']
    event_data.visit_count = row['visit_count']
    event_data.visit_type = row['visit_type']

    if extras:
      event_data.extra = extras

    timestamp = row['visit_date']
    if timestamp:
      date_time = dfdatetime_posix_time.PosixTimeInMicroseconds(
          timestamp=timestamp)
      event = time_events.DateTimeValuesEvent(
          date_time, eventdata.EventTimestamp.PAGE_VISITED)
      parser_mediator.ProduceEventWithEventData(event, event_data)

  def _ReverseHostname(self, hostname):
    """Reverses the hostname and strips the leading dot.

    The hostname entry is reversed:
      moc.elgoog.www.
    Should be:
      www.google.com

    Args:
      hostname: The reversed hostname.

    Returns:
      Reversed string without a leading dot.
    """
    if not hostname:
      return u''

    if len(hostname) > 1:
      if hostname[-1] == '.':
        return hostname[::-1][1:]
      else:
        return hostname[::-1][0:]
    return hostname

  def _GetUrl(self, url_id, cache, database):
    """Return an URL from a reference to an entry in the from_visit table."""
    url_cache_results = cache.GetResults(u'url')
    if not url_cache_results:
      result_set = database.Query(self.URL_CACHE_QUERY)

      # Note that pysqlite does not accept a Unicode string in row['string'] and
      # will raise "IndexError: Index must be int or string".
      cache.CacheQueryResults(
          result_set, 'url', 'id', ('url', 'rev_host'))
      url_cache_results = cache.GetResults(u'url')

    url, reverse_host = url_cache_results.get(url_id, [u'', u''])

    if not url:
      return u''

    hostname = self._ReverseHostname(reverse_host)
    return u'{0:s} ({1:s})'.format(url, hostname)


class FirefoxDownloadsPlugin(interface.SQLitePlugin):
  """Parses a Firefox downloads file.

  The Firefox downloads history is stored in a SQLite database file named
  downloads.sqlite.
  """

  NAME = u'firefox_downloads'
  DESCRIPTION = u'Parser for Firefox downloads SQLite database files.'

  # Define the needed queries.
  QUERIES = [
      ((u'SELECT moz_downloads.id, moz_downloads.name, moz_downloads.source, '
        u'moz_downloads.target, moz_downloads.tempPath, '
        u'moz_downloads.startTime, moz_downloads.endTime, moz_downloads.state, '
        u'moz_downloads.referrer, moz_downloads.currBytes, '
        u'moz_downloads.maxBytes, moz_downloads.mimeType '
        u'FROM moz_downloads'),
       u'ParseDownloadsRow')]

  # The required tables.
  REQUIRED_TABLES = frozenset([u'moz_downloads'])

  def ParseDownloadsRow(
      self, parser_mediator, row, query=None, **unused_kwargs):
    """Parses a downloads row.

    Args:
      parser_mediator (ParserMediator): mediates interactions between parsers
          and other components, such as storage and dfvfs.
      row (sqlite3.Row): row.
      query (Optional[str]): query.
    """
    # Note that pysqlite does not accept a Unicode string in row['string'] and
    # will raise "IndexError: Index must be int or string".

    event_data = FirefoxDownloadEventData()
    event_data.full_path = row['target']
    event_data.mime_type = row['mimeType']
    event_data.name = row['name']
    event_data.offset = row['id']
    event_data.query = query
    event_data.received_bytes = row['currBytes']
    event_data.referrer = row['referrer']
    event_data.temporary_location = row['tempPath']
    event_data.total_bytes = row['maxBytes']
    event_data.url = row['source']

    timestamp = row['startTime']
    if timestamp:
      date_time = dfdatetime_posix_time.PosixTimeInMicroseconds(
          timestamp=timestamp)
      event = time_events.DateTimeValuesEvent(
          date_time, eventdata.EventTimestamp.START_TIME)
      parser_mediator.ProduceEventWithEventData(event, event_data)

    timestamp = row['endTime']
    if timestamp:
      date_time = dfdatetime_posix_time.PosixTimeInMicroseconds(
          timestamp=timestamp)
      event = time_events.DateTimeValuesEvent(
          date_time, eventdata.EventTimestamp.END_TIME)
      parser_mediator.ProduceEventWithEventData(event, event_data)


sqlite.SQLiteParser.RegisterPlugins([
    FirefoxHistoryPlugin, FirefoxDownloadsPlugin])
