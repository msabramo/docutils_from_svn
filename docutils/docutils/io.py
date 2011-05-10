# $Id$
# Author: David Goodger <goodger@python.org>
# Copyright: This module has been placed in the public domain.

"""
I/O classes provide a uniform API for low-level input and output.  Subclasses
will exist for a variety of input/output mechanisms.
"""

__docformat__ = 'reStructuredText'

import sys
import re
import codecs
from docutils import TransformSpec
from docutils._compat import b, bytes


# Guess the locale's encoding.
# If no valid guess can be made, locale_encoding is set to `None`:
try:
    import locale # module missing in Jython
except ImportError:
    locale_encoding = None
else:
    locale_encoding = locale.getlocale()[1] or locale.getdefaultlocale()[1]
    # locale.getpreferredencoding([do_setlocale=True|False])
    # has side-effects | might return a wrong guess.
    # (cf. Update 1 in http://stackoverflow.com/questions/4082645/using-python-2-xs-locale-module-to-format-numbers-and-currency)
    try:
        codecs.lookup(locale_encoding or '') # None -> ''
    except LookupError:
        locale_encoding = None


class Input(TransformSpec):

    """
    Abstract base class for input wrappers.
    """

    component_type = 'input'

    default_source_path = None

    def __init__(self, source=None, source_path=None, encoding=None,
                 error_handler='strict'):
        self.encoding = encoding
        """Text encoding for the input source."""

        self.error_handler = error_handler
        """Text decoding error handler."""

        self.source = source
        """The source of input data."""

        self.source_path = source_path
        """A text reference to the source."""

        if not source_path:
            self.source_path = self.default_source_path

        self.successful_encoding = None
        """The encoding that successfully decoded the source data."""

    def __repr__(self):
        return '%s: source=%r, source_path=%r' % (self.__class__, self.source,
                                                  self.source_path)

    def read(self):
        raise NotImplementedError

    def decode(self, data):
        """
        Decode a string, `data`, heuristically.
        Raise UnicodeError if unsuccessful.

        The client application should call ``locale.setlocale`` at the
        beginning of processing::

            locale.setlocale(locale.LC_ALL, '')
        """
        if self.encoding and self.encoding.lower() == 'unicode':
            assert isinstance(data, unicode), (
                'input encoding is "unicode" '
                'but input is not a unicode object')
        if isinstance(data, unicode):
            # Accept unicode even if self.encoding != 'unicode'.
            return data
        if self.encoding:
            # We believe the user/application when the encoding is
            # explicitly given.
            encodings = [self.encoding]
        else:
            data_encoding = self.determine_encoding_from_data(data)
            if data_encoding:
                # If the data declares its encoding (explicitly or via a BOM),
                # we believe it.
                encodings = [data_encoding]
            else:
                # Apply heuristics only if no encoding is explicitly given and
                # no BOM found.  Start with UTF-8, because that only matches
                # data that *IS* UTF-8:
                encodings = ['utf-8',
                             locale_encoding,
                             'latin-1', # fallback encoding
                            ]
        error = None
        error_details = ''
        for enc in encodings:
            if not enc:
                continue
            try:
                decoded = unicode(data, enc, self.error_handler)
                self.successful_encoding = enc
                # Return decoded, removing BOMs.
                return decoded.replace(u'\ufeff', u'')
            except (UnicodeError, LookupError), tmperror:
                error = tmperror  # working around Python 3 deleting the
                                  # error variable after the except clause
        if error is not None:
            error_details = '\n(%s: %s)' % (error.__class__.__name__, error)
        raise UnicodeError(
            'Unable to decode input data.  Tried the following encodings: '
            '%s.%s'
            % (', '.join([repr(enc) for enc in encodings if enc]),
               error_details))

    coding_slug = re.compile(b("coding[:=]\s*([-\w.]+)"))
    """Encoding declaration pattern."""

    byte_order_marks = ((codecs.BOM_UTF8, 'utf-8'), # actually 'utf-8-sig'
                        (codecs.BOM_UTF16_BE, 'utf-16-be'),
                        (codecs.BOM_UTF16_LE, 'utf-16-le'),)
    """Sequence of (start_bytes, encoding) tuples for encoding detection.
    The first bytes of input data are checked against the start_bytes strings.
    A match indicates the given encoding."""

    def determine_encoding_from_data(self, data):
        """
        Try to determine the encoding of `data` by looking *in* `data`.
        Check for a byte order mark (BOM) or an encoding declaration.
        """
        # check for a byte order mark:
        for start_bytes, encoding in self.byte_order_marks:
            if data.startswith(start_bytes):
                return encoding
        # check for an encoding declaration pattern in first 2 lines of file:
        for line in data.splitlines()[:2]:
            match = self.coding_slug.search(line)
            if match:
                return match.group(1).decode('ascii')
        return None


class Output(TransformSpec):

    """
    Abstract base class for output wrappers.
    """

    component_type = 'output'

    default_destination_path = None

    def __init__(self, destination=None, destination_path=None,
                 encoding=None, error_handler='strict'):
        self.encoding = encoding
        """Text encoding for the output destination."""

        self.error_handler = error_handler or 'strict'
        """Text encoding error handler."""

        self.destination = destination
        """The destination for output data."""

        self.destination_path = destination_path
        """A text reference to the destination."""

        if not destination_path:
            self.destination_path = self.default_destination_path

    def __repr__(self):
        return ('%s: destination=%r, destination_path=%r'
                % (self.__class__, self.destination, self.destination_path))

    def write(self, data):
        """`data` is a Unicode string, to be encoded by `self.encode`."""
        raise NotImplementedError

    def encode(self, data):
        if self.encoding and self.encoding.lower() == 'unicode':
            assert isinstance(data, unicode), (
                'the encoding given is "unicode" but the output is not '
                'a Unicode string')
            return data
        if not isinstance(data, unicode):
            # Non-unicode (e.g. binary) output.
            return data
        else:
            return data.encode(self.encoding, self.error_handler)


class ErrorOutput(object):
    """
    Wrapper class for file-like error streams with
    failsave de- and encoding of `str`, `bytes`, `unicode` and
    `Exception` instances.

    Note that the output stream is not automatically closed.
    Call the close() method if required.
    """

    def __init__(self, stream=None, encoding=None,
                 encoding_errors='backslashreplace',
                 decoding_errors='replace'):
        """
        :Parameters:
            - `stream`: a file-like object (which is written to)
            - `encoding`: `stream` text encoding. Guessed if None.
            - `encoding_errors`: how to treat encoding errors.
        """
        if stream is None:
            stream = sys.stderr
        elif stream: # if `stream` is a file name, open it
            if type(stream) is bytes:
                stream = open(stream, 'w')
            elif type(stream) is unicode:
                stream = open(stream.encode(sys.getfilesystemencoding()), 'w')

        self.stream = stream
        """Where warning output is sent."""

        self.encoding = (encoding or getattr(stream, 'encoding', None) or
                         locale_encoding or 'ascii')
        """The output character encoding."""

        self.encoding_errors = encoding_errors
        """Encoding error handler."""

        self.decoding_errors = decoding_errors
        """Decoding error handler."""

    def write(self, data):
        """`data` can be a `string`, `unicode`, or `Exception` instance.
        """
        if isinstance(data, Exception):
            # Convert now to detect errors:
            # In Python <= 2.6, unicode(<exception instance>)
            # uses __str__ and fails with non-ASCII chars in arguments
            try:
                data = unicode(data)
            except UnicodeError, err:
                try:
                    data = u', '.join(data.args)
                except AttributeError:
                    raise err
                except UnicodeDecodeError:
                    data = str(data)
        try:
            self.stream.write(data)
        except UnicodeEncodeError:
            self.stream.write(data.encode(self.encoding,
                                               self.encoding_errors))
        except TypeError: # in Python 3, stderr expects unicode
            self.stream.write(data.decode(self.encoding,
                                          self.decoding_errors))

    def close(self):
        self.stream.close()


class FileInput(Input):

    """
    Input for single, simple file-like objects.
    """
    def __init__(self, source=None, source_path=None,
                 encoding=None, error_handler='strict',
                 autoclose=1, handle_io_errors=1, mode='rU'):
        """
        :Parameters:
            - `source`: either a file-like object (which is read directly), or
              `None` (which implies `sys.stdin` if no `source_path` given).
            - `source_path`: a path to a file, which is opened and then read.
            - `encoding`: the expected text encoding of the input file.
            - `error_handler`: the encoding error handler to use.
            - `autoclose`: close automatically after read (boolean); always
              false if `sys.stdin` is the source.
            - `handle_io_errors`: summarize I/O errors here, and exit?
            - `mode`: how the file is to be opened (see standard function
              `open`). The default 'rU' provides universal newline support
              for text files.
        """
        Input.__init__(self, source, source_path, encoding, error_handler)
        self.autoclose = autoclose
        self.handle_io_errors = handle_io_errors
        self._stderr = ErrorOutput()

        if source is None:
            if source_path:
                # Specify encoding in Python 3
                if sys.version_info >= (3,0):
                    kwargs = {'encoding': self.encoding,
                              'errors': self.error_handler}
                else:
                    kwargs = {}

                try:
                    self.source = open(source_path, mode, **kwargs)
                except IOError, error:
                    if not handle_io_errors:
                        raise
                    print >>self._stderr, '%s: %s' % (
                        error.__class__.__name__, error)
                    print >>self._stderr, (u'Unable to open source'
                        u" file for reading ('%s'). Exiting." % source_path)
                    sys.exit(1)
            else:
                self.source = sys.stdin
                self.autoclose = None
        if not source_path:
            try:
                self.source_path = self.source.name
            except AttributeError:
                pass

    def read(self):
        """
        Read and decode a single file and return the data (Unicode string).
        """
        try:
            data = self.source.read()
        finally:
            if self.autoclose:
                self.close()
        return self.decode(data)

    def readlines(self):
        """
        Return lines of a single file as list of Unicode strings.
        """
        try:
            lines = self.source.readlines()
        finally:
            if self.autoclose:
                self.close()
        return [self.decode(line) for line in lines]

    def close(self):
        self.source.close()


class FileOutput(Output):

    """
    Output for single, simple file-like objects.
    """

    def __init__(self, destination=None, destination_path=None,
                 encoding=None, error_handler='strict', autoclose=True,
                 handle_io_errors=True):
        """
        :Parameters:
            - `destination`: either a file-like object (which is written
              directly) or `None` (which implies `sys.stdout` if no
              `destination_path` given).
            - `destination_path`: a path to a file, which is opened and then
              written.
            - `autoclose`: close automatically after write (boolean); always
              False if `sys.stdout` or `sys.stderr` is the destination.
        """
        Output.__init__(self, destination, destination_path,
                        encoding, error_handler)
        self.opened = True
        self.autoclose = autoclose
        self.handle_io_errors = handle_io_errors
        self._stderr = ErrorOutput()
        if destination is None:
            if destination_path:
                self.opened = False
            else:
                self.destination = sys.stdout
        if destination in (sys.stdout, sys.stderr):
            self.autoclose = False
        if not destination_path:
            try:
                self.destination_path = self.destination.name
            except AttributeError:
                pass

    def open(self):
        # Specify encoding in Python 3.
        # (Do not use binary mode ('wb') as this prevents the
        # conversion of newlines to the system specific default.)
        if sys.version_info >= (3,0):
            kwargs = {'encoding': self.encoding,
                      'errors': self.error_handler}
        else:
            kwargs = {}

        try:
            self.destination = open(self.destination_path, 'w', **kwargs)
        except IOError, error:
            if not self.handle_io_errors:
                raise
            print >>self._stderr, '%s: %s' % (error.__class__.__name__, error)
            print >>self._stderr, (u'Unable to open destination file'
                u" for writing ('%s').  Exiting." % self.destination_path)
            sys.exit(1)
        self.opened = 1

    def write(self, data):
        """Encode `data`, write it to a single file, and return it.

        In Python 3, a (unicode) string is returned.
        """
        if sys.version_info >= (3,0):
            output = data # in py3k, write expects a (Unicode) string
        else:
            output = self.encode(data)
        if not self.opened:
            self.open()
        try:
            self.destination.write(output)
        finally:
            if self.autoclose:
                self.close()
        return output

    def close(self):
        self.destination.close()
        self.opened = False


class BinaryFileOutput(FileOutput):
    """
    A version of docutils.io.FileOutput which writes to a binary file.
    """
    def open(self):
        try:
            self.destination = open(self.destination_path, 'wb')
        except IOError, error:
            if not self.handle_io_errors:
                raise
            print >>self._stderr, '%s: %s' % (error.__class__.__name__, error)
            print >>self._stderr, (u'Unable to open destination file'
                u" for writing ('%s').  Exiting." % self.destination_path)
            sys.exit(1)
        self.opened = True


class StringInput(Input):

    """
    Direct string input.
    """

    default_source_path = '<string>'

    def read(self):
        """Decode and return the source string."""
        return self.decode(self.source)


class StringOutput(Output):

    """
    Direct string output.
    """

    default_destination_path = '<string>'

    def write(self, data):
        """Encode `data`, store it in `self.destination`, and return it."""
        self.destination = self.encode(data)
        return self.destination


class NullInput(Input):

    """
    Degenerate input: read nothing.
    """

    default_source_path = 'null input'

    def read(self):
        """Return a null string."""
        return u''


class NullOutput(Output):

    """
    Degenerate output: write nothing.
    """

    default_destination_path = 'null output'

    def write(self, data):
        """Do nothing ([don't even] send data to the bit bucket)."""
        pass


class DocTreeInput(Input):

    """
    Adapter for document tree input.

    The document tree must be passed in the ``source`` parameter.
    """

    default_source_path = 'doctree input'

    def read(self):
        """Return the document tree."""
        return self.source
