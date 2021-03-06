# -*- coding: utf-8 -*-
"""Parser for bash history files."""
import re

import pyparsing

from dfdatetime import posix_time as dfdatetime_posix_time

from plaso.containers import events
from plaso.containers import time_events
from plaso.lib import errors
from plaso.lib import eventdata
from plaso.parsers import manager
from plaso.parsers import text_parser


class BashHistoryEventData(events.EventData):
  """Bash history log event data.

  Attributes:
    command (str): command that was executed.
  """

  DATA_TYPE = u'bash:history:command'

  def __init__(self):
    """Initializes event data."""
    super(BashHistoryEventData, self).__init__(data_type=self.DATA_TYPE)
    self.command = None


class BashHistoryParser(text_parser.PyparsingMultiLineTextParser):
  """Parses events from Bash history files."""

  NAME = u'bash'

  DESCRIPTION = u'Parser for Bash history files'

  _ENCODING = u'utf-8'

  _TIMESTAMP = pyparsing.Suppress(u'#') + pyparsing.Word(
      pyparsing.nums, min=9, max=10).setParseAction(
          text_parser.PyParseIntCast).setResultsName(u'timestamp')

  _COMMAND = pyparsing.Regex(
      r'.*?(?=($|\n#\d{10}))', re.DOTALL).setResultsName(u'command')

  _LINE_GRAMMAR = _TIMESTAMP + _COMMAND + pyparsing.lineEnd()

  _VERIFICATION_GRAMMAR = (
      pyparsing.Regex(r'^\s?[^#].*?$', re.MULTILINE) + _TIMESTAMP +
      pyparsing.NotAny(pyparsing.pythonStyleComment))

  LINE_STRUCTURES = [(u'log_entry', _LINE_GRAMMAR)]

  def ParseRecord(self, parser_mediator, key, structure):
    """Parses a record and produces a Bash history event.

    Args:
      parser_mediator (ParserMediator): mediates interactions between parsers
          and other components, such as storage and dfvfs.
      key (str): name of the parsed structure.
      structure (pyparsing.ParseResults): elements parsed from the file.

    Raises:
      ParseError: when the structure type is unknown.
    """
    if key != u'log_entry':
      raise errors.ParseError(
          u'Unable to parse record, unknown structure: {0:s}'.format(key))

    event_data = BashHistoryEventData()
    event_data.command = structure.command

    date_time = dfdatetime_posix_time.PosixTime(timestamp=structure.timestamp)
    event = time_events.DateTimeValuesEvent(
        date_time, eventdata.EventTimestamp.MODIFICATION_TIME)
    parser_mediator.ProduceEventWithEventData(event, event_data)

  def VerifyStructure(self, unused_parser_mediator, line):
    """Verifies that this is a bash history file.

    Args:
      parser_mediator (ParserMediator): mediates interactions between parsers
          and other components, such as storage and dfvfs.
      line (str): single line from the text file.

    Returns:
      bool: True if this is the correct parser, False otherwise.
    """
    match_generator = self._VERIFICATION_GRAMMAR.scanString(line, maxMatches=1)
    return bool(list(match_generator))


manager.ParsersManager.RegisterParser(BashHistoryParser)
