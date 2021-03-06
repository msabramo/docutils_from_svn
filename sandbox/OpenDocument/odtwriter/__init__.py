
"""
Open Document Format (ODF) Writer.

"""

VERSION = '1.0a'

__docformat__ = 'reStructuredText'


import sys
import os
import os.path
import tempfile
import zipfile
from xml.dom import minidom
import time
import re
import StringIO
import inspect
import imp
import copy
import docutils
from docutils import frontend, nodes, utils, writers, languages
from docutils.parsers import rst
from docutils.readers import standalone
from docutils.transforms import references


WhichElementTree = ''
try:
    # 1. Try to use lxml.
    from lxml import etree
    WhichElementTree = 'lxml'
except ImportError, e:
    try:
        # 2. Try to use ElementTree from the Python standard library.
        from xml.etree import ElementTree as etree
        WhichElementTree = 'elementtree'
    except ImportError, e:
        try:
            # 3. Try to use a version of ElementTree installed as a separate
            #    product.
            from elementtree import ElementTree as etree
            WhichElementTree = 'elementtree'
        except ImportError, e:
            print '***'
            print '*** Error: Must install either ElementTree or lxml or'
            print '***   a version of Python containing ElementTree.'
            print '***'
            raise

try:
    import pygments
    import pygments.formatter
    import pygments.lexers
    class OdtPygmentsFormatter(pygments.formatter.Formatter):
        def __init__(self, rststyle_function):
            pygments.formatter.Formatter.__init__(self)
            self.rststyle_function = rststyle_function

        def rststyle(self, name, parameters=( )):
            return self.rststyle_function(name, parameters)

    class OdtPygmentsProgFormatter(OdtPygmentsFormatter):
        def format(self, tokensource, outfile):
            tokenclass = pygments.token.Token
            for ttype, value in tokensource:
                value = escape_cdata(value)
                if ttype == tokenclass.Keyword:
                    s2 = self.rststyle('codeblock-keyword')
                    s1 = '<text:span text:style-name="%s">%s</text:span>' % \
                        (s2, value, )
                elif ttype == tokenclass.Literal.String:
                    s2 = self.rststyle('codeblock-string')
                    s1 = '<text:span text:style-name="%s">%s</text:span>' % \
                        (s2, value, )
                elif ttype in (
                        tokenclass.Literal.Number.Integer,
                        tokenclass.Literal.Number.Integer.Long,
                        tokenclass.Literal.Number.Float,
                        tokenclass.Literal.Number.Hex,
                        tokenclass.Literal.Number.Oct,
                        tokenclass.Literal.Number,
                        ):
                    s2 = self.rststyle('codeblock-number')
                    s1 = '<text:span text:style-name="%s">%s</text:span>' % \
                        (s2, value, )
                elif ttype == tokenclass.Operator:
                    s2 = self.rststyle('codeblock-operator')
                    s1 = '<text:span text:style-name="%s">%s</text:span>' % \
                        (s2, value, )
                elif ttype == tokenclass.Comment:
                    s2 = self.rststyle('codeblock-comment')
                    s1 = '<text:span text:style-name="%s">%s</text:span>' % \
                        (s2, value, )
                elif ttype == tokenclass.Name.Class:
                    s2 = self.rststyle('codeblock-classname')
                    s1 = '<text:span text:style-name="%s">%s</text:span>' % \
                        (s2, value, )
                elif ttype == tokenclass.Name.Function:
                    s2 = self.rststyle('codeblock-functionname')
                    s1 = '<text:span text:style-name="%s">%s</text:span>' % \
                        (s2, value, )
                elif ttype == tokenclass.Name:
                    s2 = self.rststyle('codeblock-name')
                    s1 = '<text:span text:style-name="%s">%s</text:span>' % \
                        (s2, value, )
                else:
                    s1 = value
                outfile.write(s1)
    class OdtPygmentsLaTeXFormatter(OdtPygmentsFormatter):
        def format(self, tokensource, outfile):
            tokenclass = pygments.token.Token
            for ttype, value in tokensource:
                value = escape_cdata(value)
                if ttype == tokenclass.Keyword:
                    s2 = self.rststyle('codeblock-keyword')
                    s1 = '<text:span text:style-name="%s">%s</text:span>' % \
                        (s2, value, )
                elif ttype in (tokenclass.Literal.String,
                        tokenclass.Literal.String.Backtick,
                        ):
                    s2 = self.rststyle('codeblock-string')
                    s1 = '<text:span text:style-name="%s">%s</text:span>' % \
                        (s2, value, )
                elif ttype == tokenclass.Name.Attribute:
                    s2 = self.rststyle('codeblock-operator')
                    s1 = '<text:span text:style-name="%s">%s</text:span>' % \
                        (s2, value, )
                elif ttype == tokenclass.Comment:
                    if value[-1] == '\n':
                        s2 = self.rststyle('codeblock-comment')
                        s1 = '<text:span text:style-name="%s">%s</text:span>\n' % \
                            (s2, value[:-1], )
                    else:
                        s2 = self.rststyle('codeblock-comment')
                        s1 = '<text:span text:style-name="%s">%s</text:span>' % \
                            (s2, value, )
                elif ttype == tokenclass.Name.Builtin:
                    s2 = self.rststyle('codeblock-name')
                    s1 = '<text:span text:style-name="%s">%s</text:span>' % \
                        (s2, value, )
                else:
                    s1 = value
                outfile.write(s1)

except ImportError, e:
    pygments = None

#
# Is the PIL imaging library installed?
try:
    import Image
except ImportError, exp:
    Image = None

## import warnings
## warnings.warn('importing IPShellEmbed', UserWarning)
## from IPython.Shell import IPShellEmbed
## args = ['-pdb', '-pi1', 'In <\\#>: ', '-pi2', '   .\\D.: ',
##         '-po', 'Out<\\#>: ', '-nosep']
## ipshell = IPShellEmbed(args,
##                        banner = 'Entering IPython.  Press Ctrl-D to exit.',
##                        exit_msg = 'Leaving Interpreter, back to program.')


#
# ElementTree does not support getparent method (lxml does).
# This wrapper class and the following support functions provide
#   that support for the ability to get the parent of an element.
#
if WhichElementTree == 'elementtree':
    class _ElementInterfaceWrapper(etree._ElementInterface):
        def __init__(self, tag, attrib=None):
            etree._ElementInterface.__init__(self, tag, attrib)
            if attrib is None:
                attrib = {}
            self.parent = None
        def setparent(self, parent):
            self.parent = parent
        def getparent(self):
            return self.parent


#
# Constants and globals

# Turn tracing on/off.  See methods trace_visit_node/trace_depart_node.
DEBUG = 0
SPACES_PATTERN = re.compile(r'( +)')
TABS_PATTERN = re.compile(r'(\t+)')
FILL_PAT1 = re.compile(r'^ +')
FILL_PAT2 = re.compile(r' {2,}')

TableStylePrefix = 'Table'

GENERATOR_DESC = 'Docutils.org/odtwriter'

NAME_SPACE_1 = 'urn:oasis:names:tc:opendocument:xmlns:office:1.0'

CONTENT_NAMESPACE_DICT = CNSD = {
#    'office:version': '1.0',
    'chart': 'urn:oasis:names:tc:opendocument:xmlns:chart:1.0',
    'dc': 'http://purl.org/dc/elements/1.1/',
    'dom': 'http://www.w3.org/2001/xml-events',
    'dr3d': 'urn:oasis:names:tc:opendocument:xmlns:dr3d:1.0',
    'draw': 'urn:oasis:names:tc:opendocument:xmlns:drawing:1.0',
    'fo': 'urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0',
    'form': 'urn:oasis:names:tc:opendocument:xmlns:form:1.0',
    'math': 'http://www.w3.org/1998/Math/MathML',
    'meta': 'urn:oasis:names:tc:opendocument:xmlns:meta:1.0',
    'number': 'urn:oasis:names:tc:opendocument:xmlns:datastyle:1.0',
    'office': NAME_SPACE_1,
    'ooo': 'http://openoffice.org/2004/office',
    'oooc': 'http://openoffice.org/2004/calc',
    'ooow': 'http://openoffice.org/2004/writer',
    'presentation': 'urn:oasis:names:tc:opendocument:xmlns:presentation:1.0',
    
    'script': 'urn:oasis:names:tc:opendocument:xmlns:script:1.0',
    'style': 'urn:oasis:names:tc:opendocument:xmlns:style:1.0',
    'svg': 'urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0',
    'table': 'urn:oasis:names:tc:opendocument:xmlns:table:1.0',
    'text': 'urn:oasis:names:tc:opendocument:xmlns:text:1.0',
    'xforms': 'http://www.w3.org/2002/xforms',
    'xlink': 'http://www.w3.org/1999/xlink',
    'xsd': 'http://www.w3.org/2001/XMLSchema',
    'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
    }

STYLES_NAMESPACE_DICT = SNSD = {
#    'office:version': '1.0',
    'chart': 'urn:oasis:names:tc:opendocument:xmlns:chart:1.0',
    'dc': 'http://purl.org/dc/elements/1.1/',
    'dom': 'http://www.w3.org/2001/xml-events',
    'dr3d': 'urn:oasis:names:tc:opendocument:xmlns:dr3d:1.0',
    'draw': 'urn:oasis:names:tc:opendocument:xmlns:drawing:1.0',
    'fo': 'urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0',
    'form': 'urn:oasis:names:tc:opendocument:xmlns:form:1.0',
    'math': 'http://www.w3.org/1998/Math/MathML',
    'meta': 'urn:oasis:names:tc:opendocument:xmlns:meta:1.0',
    'number': 'urn:oasis:names:tc:opendocument:xmlns:datastyle:1.0',
    'office': NAME_SPACE_1,
    'presentation': 'urn:oasis:names:tc:opendocument:xmlns:presentation:1.0',
    'ooo': 'http://openoffice.org/2004/office',
    'oooc': 'http://openoffice.org/2004/calc',
    'ooow': 'http://openoffice.org/2004/writer',
    'script': 'urn:oasis:names:tc:opendocument:xmlns:script:1.0',
    'style': 'urn:oasis:names:tc:opendocument:xmlns:style:1.0',
    'svg': 'urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0',
    'table': 'urn:oasis:names:tc:opendocument:xmlns:table:1.0',
    'text': 'urn:oasis:names:tc:opendocument:xmlns:text:1.0',
    'xlink': 'http://www.w3.org/1999/xlink',
    }

MANIFEST_NAMESPACE_DICT = MANNSD = {
    'manifest': 'urn:oasis:names:tc:opendocument:xmlns:manifest:1.0',
}

META_NAMESPACE_DICT = METNSD = {
#    'office:version': '1.0',
    'dc': 'http://purl.org/dc/elements/1.1/',
    'meta': 'urn:oasis:names:tc:opendocument:xmlns:meta:1.0',
    'office': NAME_SPACE_1,
    'ooo': 'http://openoffice.org/2004/office',
    'xlink': 'http://www.w3.org/1999/xlink',
}

#
# Attribute dictionaries for use with ElementTree (not lxml), which
#   does not support use of nsmap parameter on Element() and SubElement().

CONTENT_NAMESPACE_ATTRIB = {
    'office:version': '1.0',
    'xmlns:chart': 'urn:oasis:names:tc:opendocument:xmlns:chart:1.0',
    'xmlns:dc': 'http://purl.org/dc/elements/1.1/',
    'xmlns:dom': 'http://www.w3.org/2001/xml-events',
    'xmlns:dr3d': 'urn:oasis:names:tc:opendocument:xmlns:dr3d:1.0',
    'xmlns:draw': 'urn:oasis:names:tc:opendocument:xmlns:drawing:1.0',
    'xmlns:fo': 'urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0',
    'xmlns:form': 'urn:oasis:names:tc:opendocument:xmlns:form:1.0',
    'xmlns:math': 'http://www.w3.org/1998/Math/MathML',
    'xmlns:meta': 'urn:oasis:names:tc:opendocument:xmlns:meta:1.0',
    'xmlns:number': 'urn:oasis:names:tc:opendocument:xmlns:datastyle:1.0',
    'xmlns:office': NAME_SPACE_1,
    'xmlns:presentation': 'urn:oasis:names:tc:opendocument:xmlns:presentation:1.0',
    'xmlns:ooo': 'http://openoffice.org/2004/office',
    'xmlns:oooc': 'http://openoffice.org/2004/calc',
    'xmlns:ooow': 'http://openoffice.org/2004/writer',
    'xmlns:script': 'urn:oasis:names:tc:opendocument:xmlns:script:1.0',
    'xmlns:style': 'urn:oasis:names:tc:opendocument:xmlns:style:1.0',
    'xmlns:svg': 'urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0',
    'xmlns:table': 'urn:oasis:names:tc:opendocument:xmlns:table:1.0',
    'xmlns:text': 'urn:oasis:names:tc:opendocument:xmlns:text:1.0',
    'xmlns:xforms': 'http://www.w3.org/2002/xforms',
    'xmlns:xlink': 'http://www.w3.org/1999/xlink',
    'xmlns:xsd': 'http://www.w3.org/2001/XMLSchema',
    'xmlns:xsi': 'http://www.w3.org/2001/XMLSchema-instance',
    }

STYLES_NAMESPACE_ATTRIB = {
    'office:version': '1.0',
    'xmlns:chart': 'urn:oasis:names:tc:opendocument:xmlns:chart:1.0',
    'xmlns:dc': 'http://purl.org/dc/elements/1.1/',
    'xmlns:dom': 'http://www.w3.org/2001/xml-events',
    'xmlns:dr3d': 'urn:oasis:names:tc:opendocument:xmlns:dr3d:1.0',
    'xmlns:draw': 'urn:oasis:names:tc:opendocument:xmlns:drawing:1.0',
    'xmlns:fo': 'urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0',
    'xmlns:form': 'urn:oasis:names:tc:opendocument:xmlns:form:1.0',
    'xmlns:math': 'http://www.w3.org/1998/Math/MathML',
    'xmlns:meta': 'urn:oasis:names:tc:opendocument:xmlns:meta:1.0',
    'xmlns:number': 'urn:oasis:names:tc:opendocument:xmlns:datastyle:1.0',
    'xmlns:office': NAME_SPACE_1,
    'xmlns:presentation': 'urn:oasis:names:tc:opendocument:xmlns:presentation:1.0',
    'xmlns:ooo': 'http://openoffice.org/2004/office',
    'xmlns:oooc': 'http://openoffice.org/2004/calc',
    'xmlns:ooow': 'http://openoffice.org/2004/writer',
    'xmlns:script': 'urn:oasis:names:tc:opendocument:xmlns:script:1.0',
    'xmlns:style': 'urn:oasis:names:tc:opendocument:xmlns:style:1.0',
    'xmlns:svg': 'urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0',
    'xmlns:table': 'urn:oasis:names:tc:opendocument:xmlns:table:1.0',
    'xmlns:text': 'urn:oasis:names:tc:opendocument:xmlns:text:1.0',
    'xmlns:xlink': 'http://www.w3.org/1999/xlink',
    }

MANIFEST_NAMESPACE_ATTRIB = {
    'xmlns:manifest': 'urn:oasis:names:tc:opendocument:xmlns:manifest:1.0',
}

META_NAMESPACE_ATTRIB = {
    'office:version': '1.0',
    'xmlns:dc': 'http://purl.org/dc/elements/1.1/',
    'xmlns:meta': 'urn:oasis:names:tc:opendocument:xmlns:meta:1.0',
    'xmlns:office': NAME_SPACE_1,
    'xmlns:ooo': 'http://openoffice.org/2004/office',
    'xmlns:xlink': 'http://www.w3.org/1999/xlink',
}


#
# Functions
#

#
# ElementTree support functions.
# In order to be able to get the parent of elements, must use these
#   instead of the functions with same name provided by ElementTree.
#
def Element(tag, attrib=None, nsmap=None, nsdict=CNSD):
    if attrib is None:
        attrib = {}
    tag, attrib = fix_ns(tag, attrib, nsdict)
    if WhichElementTree == 'lxml':
        el = etree.Element(tag, attrib, nsmap=nsmap)
    else:
        el = _ElementInterfaceWrapper(tag, attrib)
    return el

def SubElement(parent, tag, attrib=None, nsmap=None, nsdict=CNSD):
    if attrib is None:
        attrib = {}
    tag, attrib = fix_ns(tag, attrib, nsdict)
    if WhichElementTree == 'lxml':
        el = etree.SubElement(parent, tag, attrib, nsmap=nsmap)
    else:
        el = _ElementInterfaceWrapper(tag, attrib)
        parent.append(el)
        el.setparent(parent)
    return el

def fix_ns(tag, attrib, nsdict):
    nstag = add_ns(tag, nsdict)
    nsattrib = {}
    for key, val in attrib.iteritems():
        nskey = add_ns(key, nsdict)
        nsattrib[nskey] = val
    return nstag, nsattrib

def add_ns(tag, nsdict=CNSD):
    if WhichElementTree == 'lxml':
        nstag, name = tag.split(':')
        ns = nsdict.get(nstag)
        if ns is None:
            raise RuntimeError, 'Invalid namespace prefix: %s' % nstag
        tag = '{%s}%s' % (ns, name,)
    return tag

def ToString(et):
    outstream = StringIO.StringIO()
    et.write(outstream)
    s1 = outstream.getvalue()
    outstream.close()
    return s1

def escape_cdata(text):
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    ascii = ''
    for char in text:
      if ord(char) >= ord("\x7f"):
          ascii += "&#x%X;" % ( ord(char), )
      else:
          ascii += char
    return ascii


#
# Classes
#

# Does this version of Docutils has Directive support?
if hasattr(rst, 'Directive'):
    #
    # Class to control syntax highlighting.
    class SyntaxHighlightCodeBlock(rst.Directive):
        required_arguments = 1
        optional_arguments = 0
        has_content = True
        #
        # See visit_literal_block for code that processes the node 
        #   created here.
        def run(self):
            language = self.arguments[0]
            code_block = nodes.literal_block(classes=["code-block", language],
                language=language)
            lines = self.content
            content = '\n'.join(lines)
            text_node = nodes.Text(content)
            code_block.append(text_node)
            # Mark this node for high-lighting so that visit_literal_block
            #   will be able to hight-light those produced here and
            #   *not* high-light regular literal blocks (:: in reST).
            code_block['hilight'] = True
            #import pdb; pdb.set_trace()
            return [code_block]

    rst.directives.register_directive('sourcecode', SyntaxHighlightCodeBlock)
    rst.directives.register_directive('code', SyntaxHighlightCodeBlock)

    rst.directives.register_directive('code-block', SyntaxHighlightCodeBlock)

#
# Register directives defined in a module named "odtwriter_plugins".
#
def load_plugins():
    plugin_mod = None
    count = 0
    try:
        name = 'odtwriter_plugins'
        fp, pathname, description = imp.find_module(name)
        plugin_mod = imp.load_module(name, fp, pathname, description)
        #import odtwriter_plugins
        #plugin_mod = odtwriter_plugins
    except ImportError, e:
        pass
    if plugin_mod is None:
        return count
    klasses = inspect.getmembers(plugin_mod, inspect.isclass)
    for klass in klasses:
        if register_plugin(*klass):
            count += 1
    return count

def register_plugin(name, klass):
    plugin_name = getattr(klass, 'plugin_name', None)
    if plugin_name is not None:
        rst.directives.register_directive(plugin_name, klass)

load_plugins()


WORD_SPLIT_PAT1 = re.compile(r'\b(\w*)\b\W*')

def split_words(line):
    # We need whitespace at the end of the string for our regexpr.
    line += ' '
    words = []
    pos1 = 0
    mo = WORD_SPLIT_PAT1.search(line, pos1)
    while mo is not None:
        word = mo.groups()[0]
        words.append(word)
        pos1 = mo.end()
        mo = WORD_SPLIT_PAT1.search(line, pos1)
    return words


#
# Information about the indentation level for lists nested inside
#   other contexts, e.g. dictionary lists.
class ListLevel(object):
    def __init__(self, level, sibling_level=True, nested_level=True):
        self.level = level
        self.sibling_level = sibling_level
        self.nested_level = nested_level
    def set_sibling(self, sibling_level): self.sibling_level = sibling_level
    def get_sibling(self): return self.sibling_level
    def set_nested(self, nested_level): self.nested_level = nested_level
    def get_nested(self): return self.nested_level
    def set_level(self, level): self.level = level
    def get_level(self): return self.level


class Writer(writers.Writer):

    MIME_TYPE = 'application/vnd.oasis.opendocument.text'
    EXTENSION = '.odt'

    supported = ('html', 'html4css1', 'xhtml')
    """Formats this writer supports."""

    default_stylesheet = 'styles' + EXTENSION

    default_stylesheet_path = utils.relative_path(
        os.path.join(os.getcwd(), 'dummy'),
        os.path.join(os.path.dirname(__file__), default_stylesheet))

    default_template = 'template.txt'

    default_template_path = utils.relative_path(
        os.path.join(os.getcwd(), 'dummy'),
        os.path.join(os.path.dirname(__file__), default_template))

    settings_spec = (
        'ODF-Specific Options',
        None,
        (
        ('Specify a stylesheet URL, used verbatim.  Overrides '
            '--stylesheet-path.',
            ['--stylesheet'],
            {'metavar': '<URL>', 'overrides': 'stylesheet_path'}),
        ('Specify a stylesheet file, relative to the current working '
            'directory.  The path is adjusted relative to the output ODF '
            'file.  Overrides --stylesheet.  Default: "%s"'
            % default_stylesheet_path,
            ['--stylesheet-path'],
            {'metavar': '<file>', 'overrides': 'stylesheet',
                'default': default_stylesheet_path}),
        ('Specify a configuration/mapping file relative to the '
            'current working '
            'directory for additional ODF options.  '
            'In particular, this file may contain a section named '
            '"Formats" that maps default style names to '
            'names to be used in the resulting output file allowing for '
            'adhering to external standards. '
            'For more info and the format of the configuration/mapping file, '
            'see the odtwriter doc.',
            ['--odf-config-file'],
            {'metavar': '<file>'}),
        ('Obfuscate email addresses to confuse harvesters while still '
            'keeping email links usable with standards-compliant browsers.',
            ['--cloak-email-addresses'],
            {'default': False,
                'action': 'store_true',
                'dest': 'cloak_email_addresses',
                'validator': frontend.validate_boolean}),
        ('Do not obfuscate email addresses.',
            ['--no-cloak-email-addresses'],
            {'default': False,
                'action': 'store_false',
                'dest': 'cloak_email_addresses',
                'validator': frontend.validate_boolean}),
        ('Specify the thickness of table borders in thousands of a cm.  '
            'Default is 35.',
            ['--table-border-thickness'],
            {'default': 35,
                'validator': frontend.validate_nonnegative_int}),
        ('Add syntax highlighting in literal code blocks.',
            ['--add-syntax-highlighting'],
            {'default': False,
                'action': 'store_true',
                'dest': 'add_syntax_highlighting',
                'validator': frontend.validate_boolean}),
        ('Do not add syntax highlighting in literal code blocks. (default)',
            ['--no-add-syntax-highlighting'],
            {'default': False,
                'action': 'store_false',
                'dest': 'add_syntax_highlighting',
                'validator': frontend.validate_boolean}),
        ('Create sections for headers.  (default)',
            ['--create-sections'],
            {'default': True, 
                'action': 'store_true',
                'dest': 'create_sections',
                'validator': frontend.validate_boolean}),
        ('Do not create sections for headers.',
            ['--no-create-sections'],
            {'default': True, 
                'action': 'store_false',
                'dest': 'create_sections',
                'validator': frontend.validate_boolean}),
        ('Create links.',
            ['--create-links'],
            {'default': False,
                'action': 'store_true',
                'dest': 'create_links',
                'validator': frontend.validate_boolean}),
        ('Do not create links.  (default)',
            ['--no-create-links'],
            {'default': False,
                'action': 'store_false',
                'dest': 'create_links',
                'validator': frontend.validate_boolean}),
        ('Generate endnotes at end of document, not footnotes '
            'at bottom of page.',
            ['--endnotes-end-doc'],
            {'default': False,
                'action': 'store_true',
                'dest': 'endnotes_end_doc',
                'validator': frontend.validate_boolean}),
        ('Generate footnotes at bottom of page, not endnotes '
            'at end of document. (default)',
            ['--no-endnotes-end-doc'],
            {'default': False,
                'action': 'store_false',
                'dest': 'endnotes_end_doc',
                'validator': frontend.validate_boolean}),
        ))

    settings_defaults = {
        'output_encoding_error_handler': 'xmlcharrefreplace',
        }

    relative_path_settings = (
        'stylesheet_path',
        )

    config_section = 'opendocument odf writer'
    config_section_dependencies = (
        'writers',
        )

    def __init__(self):
        writers.Writer.__init__(self)
        self.translator_class = ODFTranslator

    def translate(self):
        self.settings = self.document.settings
        self.visitor = self.translator_class(self.document)
        self.document.walkabout(self.visitor)
        self.visitor.add_doc_title()
        self.assemble_my_parts()
        self.output = self.parts['whole']

    def assemble_my_parts(self):
        """Assemble the `self.parts` dictionary.  Extend in subclasses.
        """
        #ipshell('At assemble_parts')
        writers.Writer.assemble_parts(self)
        f = tempfile.NamedTemporaryFile()
        zfile = zipfile.ZipFile(f, 'w', zipfile.ZIP_DEFLATED)
        content = self.visitor.content_astext()
        self.write_zip_str(zfile, 'content.xml', content)
        self.write_zip_str(zfile, 'mimetype', self.MIME_TYPE)
        s1 = self.create_manifest()
        self.write_zip_str(zfile, 'META-INF/manifest.xml', s1)
        s1 = self.create_meta()
        self.write_zip_str(zfile, 'meta.xml', s1)
        s1 = self.get_stylesheet()
        self.write_zip_str(zfile, 'styles.xml', s1)
        s1 = self.get_settings()
        self.write_zip_str(zfile, 'settings.xml', s1)
        self.store_embedded_files(zfile)
        zfile.close()
        f.seek(0)
        whole = f.read()
        f.close()
        self.parts['whole'] = whole
        self.parts['encoding'] = self.document.settings.output_encoding
        self.parts['version'] = docutils.__version__

    def write_zip_str(self, zfile, name, bytes):
        localtime = time.localtime(time.time())
        zinfo = zipfile.ZipInfo(name, localtime)
        # Add some standard UNIX file access permissions (-rw-r--r--).
        zinfo.external_attr = (0x81a4 & 0xFFFF) << 16L
        zinfo.compress_type = zipfile.ZIP_DEFLATED
        zfile.writestr(zinfo, bytes)

    def store_embedded_files(self, zfile):
        embedded_files = self.visitor.get_embedded_file_list()
        for source, destination in embedded_files:
            if source is None:
                continue
            try:
                # encode/decode
                destination1 = destination.decode('latin-1').encode('utf-8')
                zfile.write(source, destination1, zipfile.ZIP_STORED)
            except OSError, e:
                print "Error: Can't open file %s." % (source, )

    def get_settings(self):
        """
        modeled after get_stylesheet
        """
        stylespath = utils.get_stylesheet_reference(self.settings,
                                                    os.path.join(os.getcwd(), 'dummy'))
        zfile = zipfile.ZipFile(stylespath, 'r')
        s1 = zfile.read('settings.xml')
        zfile.close()
        return s1

    def get_stylesheet(self):
        """Retrieve the stylesheet from either a .xml file or from
        a .odt (zip) file.  Return the content as a string.
        """
        stylespath = utils.get_stylesheet_reference(self.settings,
            os.path.join(os.getcwd(), 'dummy'))
        ext = os.path.splitext(stylespath)[1]
        if ext == '.xml':
            stylesfile = open(stylespath, 'r')
            s1 = stylesfile.read()
            stylesfile.close()
        elif ext == self.EXTENSION:
            zfile = zipfile.ZipFile(stylespath, 'r')
            s1 = zfile.read('styles.xml')
            zfile.close()
        else:
            raise RuntimeError, 'stylesheet path (%s) must be %s or .xml file' %(stylespath, self.EXTENSION)
        s1 = self.visitor.setup_page(s1)
        return s1

    def assemble_parts(self):
        pass

    def create_manifest(self):
        if WhichElementTree == 'lxml':
            root = Element('manifest:manifest',
                nsmap=MANIFEST_NAMESPACE_DICT,
                nsdict=MANIFEST_NAMESPACE_DICT,
                )
        else:
            root = Element('manifest:manifest',
                attrib=MANIFEST_NAMESPACE_ATTRIB,
                nsdict=MANIFEST_NAMESPACE_DICT,
                )
        doc = etree.ElementTree(root)
        SubElement(root, 'manifest:file-entry', attrib={
            'manifest:media-type': self.MIME_TYPE,
            'manifest:full-path': '/',
            }, nsdict=MANNSD)
        SubElement(root, 'manifest:file-entry', attrib={
            'manifest:media-type': 'text/xml',
            'manifest:full-path': 'content.xml',
            }, nsdict=MANNSD)
        SubElement(root, 'manifest:file-entry', attrib={
            'manifest:media-type': 'text/xml',
            'manifest:full-path': 'styles.xml',
            }, nsdict=MANNSD)
        SubElement(root, 'manifest:file-entry', attrib={
            'manifest:media-type': 'text/xml',
            'manifest:full-path': 'meta.xml',
            }, nsdict=MANNSD)
        s1 = ToString(doc)
        doc = minidom.parseString(s1)
        s1 = doc.toprettyxml('  ')
        return s1

    def create_meta(self):
        if WhichElementTree == 'lxml':
            root = Element('office:document-meta',
                nsmap=META_NAMESPACE_DICT,
                nsdict=META_NAMESPACE_DICT,
                )
        else:
            root = Element('office:document-meta',
                attrib=META_NAMESPACE_ATTRIB,
                nsdict=META_NAMESPACE_DICT,
                )
        doc = etree.ElementTree(root)
        root = SubElement(root, 'office:meta', nsdict=METNSD)
        el1 = SubElement(root, 'meta:generator', nsdict=METNSD)
        el1.text = 'Docutils/rst2odf.py/%s' % (VERSION, )
        s1 = os.environ.get('USER', '')
        el1 = SubElement(root, 'meta:initial-creator', nsdict=METNSD)
        el1.text = s1
        s2 = time.strftime('%Y-%m-%dT%H:%M:%S', time.localtime())
        el1 = SubElement(root, 'meta:creation-date', nsdict=METNSD)
        el1.text = s2
        el1 = SubElement(root, 'dc:creator', nsdict=METNSD)
        el1.text = s1
        el1 = SubElement(root, 'dc:date', nsdict=METNSD)
        el1.text = s2
        el1 = SubElement(root, 'dc:language', nsdict=METNSD)
        el1.text = 'en-US'
        el1 = SubElement(root, 'meta:editing-cycles', nsdict=METNSD)
        el1.text = '1'
        el1 = SubElement(root, 'meta:editing-duration', nsdict=METNSD)
        el1.text = 'PT00M01S'
        title = self.visitor.get_title()
        el1 = SubElement(root, 'dc:title', nsdict=METNSD)
        if title:
            el1.text = title
        else:
            el1.text = '[no title]'
        meta_dict = self.visitor.get_meta_dict()
        keywordstr = meta_dict.get('keywords')
        if keywordstr is not None:
            keywords = split_words(keywordstr)
            for keyword in keywords:
                el1 = SubElement(root, 'meta:keyword', nsdict=METNSD)
                el1.text = keyword
        description = meta_dict.get('description')
        if description is not None:
            el1 = SubElement(root, 'dc:description', nsdict=METNSD)
            el1.text = description
        s1 = ToString(doc)
        #doc = minidom.parseString(s1)
        #s1 = doc.toprettyxml('  ')
        return s1

# class ODFTranslator(nodes.SparseNodeVisitor):

class ODFTranslator(nodes.GenericNodeVisitor):
  
    used_styles = (
        'attribution', 'blockindent', 'blockquote', 'blockquote-bulletitem',
        'blockquote-bulletlist', 'blockquote-enumitem', 'blockquote-enumlist',
        'bulletitem', 'bulletlist', 'caption', 'centeredtextbody', 'codeblock',
        'codeblock-classname', 'codeblock-comment', 'codeblock-functionname',
        'codeblock-keyword', 'codeblock-name', 'codeblock-number',
        'codeblock-operator', 'codeblock-string', 'emphasis', 'enumitem',
        'enumlist', 'epigraph', 'epigraph-bulletitem', 'epigraph-bulletlist',
        'epigraph-enumitem', 'epigraph-enumlist', 'footer',
        'footnote', 'citation',
        'header', 'highlights', 'highlights-bulletitem',
        'highlights-bulletlist', 'highlights-enumitem', 'highlights-enumlist',
        'horizontalline', 'inlineliteral', 'quotation', 'rubric',
        'strong', 'table-title', 'textbody', 'tocbulletlist', 'tocenumlist',
        'title',
        'subtitle',
        'heading1',
        'heading2',
        'heading3',
        'heading4',
        'heading5',
        'heading6',
        'heading7',
        'admon-attention-hdr',
        'admon-attention-body',
        'admon-caution-hdr',
        'admon-caution-body',
        'admon-danger-hdr',
        'admon-danger-body',
        'admon-error-hdr',
        'admon-error-body',
        'admon-generic-hdr',
        'admon-generic-body',
        'admon-hint-hdr',
        'admon-hint-body',
        'admon-important-hdr',
        'admon-important-body',
        'admon-note-hdr',
        'admon-note-body',
        'admon-tip-hdr',
        'admon-tip-body',
        'admon-warning-hdr',
        'admon-warning-body',
        'tableoption',
        'tableoption.%c', 'tableoption.%c%d', 'Table%d', 'Table%d.%c',
        'Table%d.%c%d',
        'lineblock1',
        'lineblock2',
        'lineblock3',
        'lineblock4',
        'lineblock5',
        'lineblock6',
        )

    def __init__(self, document):
        #nodes.SparseNodeVisitor.__init__(self, document)
        nodes.GenericNodeVisitor.__init__(self, document)
        self.settings = document.settings
        self.format_map = { }
        if self.settings.odf_config_file:
            from ConfigParser import ConfigParser

            parser = ConfigParser()
            parser.read(self.settings.odf_config_file)
            for rststyle, format in parser.items("Formats"):
                if rststyle not in self.used_styles:
                    print '***'
                    print ('*** Warning: Style "%s" '
                        'is not a style used by odtwriter.' % (
                        rststyle, ))
                    print '***'
                    #raise RuntimeError, 'Unused style "%s"' % ( rststyle, )
                self.format_map[rststyle] = format
        self.section_level = 0
        self.section_count = 0
        # Create ElementTree content and styles documents.
        if WhichElementTree == 'lxml':
            root = Element(
                'office:document-content',
                nsmap=CONTENT_NAMESPACE_DICT,
                )
        else:
            root = Element(
                'office:document-content',
                attrib=CONTENT_NAMESPACE_ATTRIB,
                )
        self.content_tree = etree.ElementTree(element=root)
        self.current_element = root
        SubElement(root, 'office:scripts')
        SubElement(root, 'office:font-face-decls')
        el = SubElement(root, 'office:automatic-styles')
        self.automatic_styles = el
        el = SubElement(root, 'office:body')
        el = self.generate_content_element(el)
        self.current_element = el
        self.body_text_element = el
        self.paragraph_style_stack = [self.rststyle('textbody'), ]
        self.list_style_stack = []
        self.table_count = 0
        self.column_count = ord('A') - 1
        self.trace_level = -1
        self.optiontablestyles_generated = False
        self.field_name = None
        self.field_element = None
        self.title = None
        self.image_count = 0
        self.image_style_count = 0
        self.image_dict = {}
        self.embedded_file_list = []
        self.syntaxhighlighting = 1
        self.syntaxhighlight_lexer = 'python'
        self.header_content = []
        self.footer_content = []
        self.in_header = False
        self.in_footer = False
        self.blockstyle = ''
        self.in_table_of_contents = False
        self.footnote_ref_dict = {}
        self.footnote_list = []
        self.footnote_chars_idx = 0
        self.footnote_level = 0
        self.pending_ids = [ ]
        self.in_paragraph = False
        self.found_doc_title = False
        self.bumped_list_level_stack = []
        self.meta_dict = {}
        self.line_block_level = 0
        self.line_indent_level = 0
        self.citation_id = None

    def add_doc_title(self):
        text = self.settings.title
        if text:
            self.title = text
            if not self.found_doc_title:
                el = Element('text:p', attrib = {
                    'text:style-name': self.rststyle('title'),
                    })
                el.text = text
                self.body_text_element.insert(0, el)

    def rststyle(self, name, parameters=( )):
        """
        Returns the style name to use for the given style.

        If `parameters` is given `name` must contain a matching number of ``%`` and
        is used as a format expression with `parameters` as the value.
        """
        name1 = name % parameters
        stylename = self.format_map.get(name1, 'rststyle-%s' % name1)
        return stylename

    def generate_content_element(self, root):
        return SubElement(root, 'office:text')

    def setup_page(self, content):
        root_el = etree.fromstring(content)
        self.setup_paper(root_el)
        if len(self.header_content) > 0 or len(self.footer_content) > 0:
            self.add_header_footer(root_el)
        new_content = etree.tostring(root_el)
        return new_content

    def setup_paper(self, root_el):
        try:
            fin = os.popen("paperconf -s 2> /dev/null")
            w, h = map(float, fin.read().split())
            fin.close()
        except:
            w, h = 612, 792     # default to Letter
        def walk(el):
            if el.tag == "{%s}page-layout-properties" % SNSD["style"] and \
                    not el.attrib.has_key("{%s}page-width" % SNSD["fo"]):
                el.attrib["{%s}page-width" % SNSD["fo"]] = "%.3fpt" % w
                el.attrib["{%s}page-height" % SNSD["fo"]] = "%.3fpt" % h
                el.attrib["{%s}margin-left" % SNSD["fo"]] = \
                        el.attrib["{%s}margin-right" % SNSD["fo"]] = \
                        "%.3fpt" % (.1 * w)
                el.attrib["{%s}margin-top" % SNSD["fo"]] = \
                        el.attrib["{%s}margin-bottom" % SNSD["fo"]] = \
                        "%.3fpt" % (.1 * h)
            else:
                for subel in el.getchildren(): walk(subel)
        walk(root_el)

    def add_header_footer(self, root_el):
        path = '{%s}master-styles' % (NAME_SPACE_1, )
        master_el = root_el.find(path)
        if master_el is None:
            return
        path = '{%s}master-page' % (SNSD['style'], )
        master_el = master_el.find(path)
        if master_el is None:
            return
        el1 = master_el
        if len(self.header_content) > 0:
            if WhichElementTree == 'lxml':
                el2 = SubElement(el1, 'style:header', nsdict=SNSD)
            else:
                el2 = SubElement(el1, 'style:header',
                    attrib=STYLES_NAMESPACE_ATTRIB,
                    nsdict=STYLES_NAMESPACE_DICT,
                    )
            for el in self.header_content:
                attrkey = add_ns('text:style-name', nsdict=SNSD)
                el.attrib[attrkey] = self.rststyle('header')
                el2.append(el)
        if len(self.footer_content) > 0:
            if WhichElementTree == 'lxml':
                el2 = SubElement(el1, 'style:footer', nsdict=SNSD)
            else:
                el2 = SubElement(el1, 'style:footer',
                    attrib=STYLES_NAMESPACE_ATTRIB,
                    nsdict=STYLES_NAMESPACE_DICT,
                    )
            for el in self.footer_content:
                attrkey = add_ns('text:style-name', nsdict=SNSD)
                el.attrib[attrkey] = self.rststyle('footer')
                el2.append(el)
        #new_tree = etree.ElementTree(root_el)
        #new_content = ToString(new_tree)

    def astext(self):
        root = self.content_tree.getroot()
        et = etree.ElementTree(root)
        s1 = ToString(et)
        return s1

    def content_astext(self):
        return self.astext()

    def set_title(self, title): self.title = title
    def get_title(self): return self.title
    def set_embedded_file_list(self, embedded_file_list):
        self.embedded_file_list = embedded_file_list
    def get_embedded_file_list(self): return self.embedded_file_list
    def get_meta_dict(self): return self.meta_dict

    def process_footnotes(self):
        for node, el1 in self.footnote_list:
            backrefs = node.attributes.get('backrefs', [])
            first = True
            for ref in backrefs:
                el2 = self.footnote_ref_dict.get(ref)
                if el2 is not None:
                    if first:
                        first = False
                        el3 = copy.deepcopy(el1)
                        el2.append(el3)
                    else:
                        children = el2.getchildren()
                        if len(children) > 0: #  and 'id' in el2.attrib:
                            child = children[0]
                            ref1 = child.text
                            attribkey = add_ns('text:id', nsdict=SNSD)
                            id1 = el2.get(attribkey, 'footnote-error')
                            if id1 is None:
                                id1 = ''
                            tag = add_ns('text:note-ref', nsdict=SNSD)
                            el2.tag = tag
                            if self.settings.endnotes_end_doc:
                                note_class = 'endnote'
                            else:
                                note_class = 'footnote'
                            el2.attrib.clear()
                            attribkey = add_ns('text:note-class', nsdict=SNSD)
                            el2.attrib[attribkey] = note_class
                            attribkey = add_ns('text:ref-name', nsdict=SNSD)
                            el2.attrib[attribkey] = id1
                            attribkey = add_ns('text:reference-format', nsdict=SNSD)
                            el2.attrib[attribkey] = 'page'
                            el2.text = ref1

    #
    # Utility methods

    def append_child(self, tag, attrib=None, parent=None):
        if parent is None:
            parent = self.current_element
        if attrib is None:
            el = SubElement(parent, tag)
        else:
            el = SubElement(parent, tag, attrib)
        return el

    def append_p(self, style, text=None):
        result = self.append_child('text:p', attrib={
                'text:style-name': self.rststyle(style)})
        self.append_pending_ids(result)
        if text is not None:
            result.text = text
        return result

    def append_pending_ids(self, el):
        if self.settings.create_links:
            for id in self.pending_ids:
                SubElement(el, 'text:reference-mark', attrib={
                        'text:name': id})
        self.pending_ids = [ ]

    def set_current_element(self, el):
        self.current_element = el

    def set_to_parent(self):
        self.current_element = self.current_element.getparent()

    def generate_labeled_block(self, node, label):
        el = self.append_p('textbody')
        el1 = SubElement(el, 'text:span',
            attrib={'text:style-name': self.rststyle('strong')})
        el1.text = label
        el = self.append_p('blockindent')
        return el

    def generate_labeled_line(self, node, label):
        el = self.append_p('textbody')
        el1 = SubElement(el, 'text:span',
            attrib={'text:style-name': self.rststyle('strong')})
        el1.text = label
        el1.tail = node.astext()
        return el

    def encode(self, text):
        text = text.replace(u'\u00a0', " ")
        return text

    def trace_visit_node(self, node):
        if DEBUG >= 1:
            self.trace_level += 1
            self._trace_show_level(self.trace_level)
            if DEBUG >= 2:
                print '(visit_%s) node: %s' % (node.tagname, node.astext(), )
            else:
                print '(visit_%s)' % node.tagname

    def trace_depart_node(self, node):
        if not DEBUG:
            return
        self._trace_show_level(self.trace_level)
        print '(depart_%s)' % node.tagname
        self.trace_level -= 1

    def _trace_show_level(self, level):
        for idx in range(level):
            print '   ',

    #
    # Visitor functions
    #
    # In alphabetic order, more or less.
    #   See docutils.docutils.nodes.node_class_names.
    #

    def dispatch_visit(self, node):
        """Override to catch basic attributes which many nodes have."""
        self.handle_basic_atts(node)
        nodes.GenericNodeVisitor.dispatch_visit(self, node)

    def handle_basic_atts(self, node):
        if isinstance(node, nodes.Element) and node['ids']:
            self.pending_ids += node['ids']

    def default_visit(self, node):
        #ipshell('At default_visit')
        print 'missing visit_%s' % (node.tagname, )

    def default_departure(self, node):
        print 'missing depart_%s' % (node.tagname, )

    def visit_Text(self, node):
        #ipshell('At visit_Text')
        # Skip nodes whose text has been processed in parent nodes.
        if isinstance(node.parent, docutils.nodes.literal_block):
            #isinstance(node.parent, docutils.nodes.term) or \
            #isinstance(node.parent, docutils.nodes.definition):
            return
        text = node.astext()
        # Are we in mixed content?  If so, add the text to the
        #   etree tail of the previous sibling element.
        if len(self.current_element.getchildren()) > 0:
            if self.current_element.getchildren()[-1].tail:
                self.current_element.getchildren()[-1].tail += text
            else:
                self.current_element.getchildren()[-1].tail = text
        else:
            if self.current_element.text:
                self.current_element.text += text
            else:
                self.current_element.text = text

    def depart_Text(self, node):
        pass

    #
    # Pre-defined fields
    #
    
    def visit_address(self, node):
        #ipshell('At visit_address')
        el = self.generate_labeled_block(node, 'Address: ')
        self.set_current_element(el)

    def depart_address(self, node):
        self.set_to_parent()

    def visit_author(self, node):
        if isinstance(node.parent, nodes.authors):
            el = self.append_p('blockindent')
        else:
            el = self.generate_labeled_block(node, 'Author: ')
        self.set_current_element(el)

    def depart_author(self, node):
        self.set_to_parent()

    def visit_authors(self, node):
        #ipshell('At visit_authors')
        #self.trace_visit_node(node)
        label = 'Authors:'
        el = self.append_p('textbody')
        el1 = SubElement(el, 'text:span',
            attrib={'text:style-name': self.rststyle('strong')})
        el1.text = label

    def depart_authors(self, node):
        #self.trace_depart_node(node)
        pass

    def visit_contact(self, node):
        el = self.generate_labeled_block(node, 'Contact: ')
        self.set_current_element(el)

    def depart_contact(self, node):
        self.set_to_parent()

    def visit_copyright(self, node):
        el = self.generate_labeled_block(node, 'Copyright: ')
        self.set_current_element(el)

    def depart_copyright(self, node):
        self.set_to_parent()

    def visit_date(self, node):
        self.generate_labeled_line(node, 'Date: ')

    def depart_date(self, node):
        pass

    def visit_organization(self, node):
        el = self.generate_labeled_block(node, 'Organization: ')
        self.set_current_element(el)

    def depart_organization(self, node):
        self.set_to_parent()

    def visit_status(self, node):
        el = self.generate_labeled_block(node, 'Status: ')
        self.set_current_element(el)

    def depart_status(self, node):
        self.set_to_parent()

    def visit_revision(self, node):
        self.generate_labeled_line(node, 'Revision: ')

    def depart_revision(self, node):
        pass

    def visit_version(self, node):
        el = self.generate_labeled_line(node, 'Version: ')
        #self.set_current_element(el)

    def depart_version(self, node):
        #self.set_to_parent()
        pass

    def visit_attribution(self, node):
        #ipshell('At visit_attribution')
        el = self.append_p('attribution', node.astext())

    def depart_attribution(self, node):
        #ipshell('At depart_attribution')
        pass

    def visit_block_quote(self, node):
        #ipshell('At visit_block_quote')
        if 'epigraph' in node.attributes['classes']:
            self.paragraph_style_stack.append(self.rststyle('epigraph'))
            self.blockstyle = self.rststyle('epigraph')
        elif 'highlights' in node.attributes['classes']:
            self.paragraph_style_stack.append(self.rststyle('highlights'))
            self.blockstyle = self.rststyle('highlights')
        else:
            self.paragraph_style_stack.append(self.rststyle('blockquote'))
            self.blockstyle = self.rststyle('blockquote')
        self.line_indent_level += 1

    def depart_block_quote(self, node):
        self.paragraph_style_stack.pop()
        self.blockstyle = ''
        self.line_indent_level -= 1

    def visit_bullet_list(self, node):
        #ipshell('At visit_bullet_list')
        if self.in_table_of_contents:
            if node.has_key('classes') and \
                    'auto-toc' in node.attributes['classes']:
                el = SubElement(self.current_element, 'text:list', attrib={
                    'text:style-name': self.rststyle('tocenumlist'),
                    })
                self.list_style_stack.append(self.rststyle('enumitem'))
            else:
                el = SubElement(self.current_element, 'text:list', attrib={
                    'text:style-name': self.rststyle('tocbulletlist'),
                    })
                self.list_style_stack.append(self.rststyle('bulletitem'))
        else:
            if self.blockstyle == self.rststyle('blockquote'):
                el = SubElement(self.current_element, 'text:list', attrib={
                    'text:style-name': self.rststyle('blockquote-bulletlist'),
                    })
                self.list_style_stack.append(self.rststyle('blockquote-bulletitem'))
            elif self.blockstyle == self.rststyle('highlights'):
                el = SubElement(self.current_element, 'text:list', attrib={
                    'text:style-name': self.rststyle('highlights-bulletlist'),
                    })
                self.list_style_stack.append(self.rststyle('highlights-bulletitem'))
            elif self.blockstyle == self.rststyle('epigraph'):
                el = SubElement(self.current_element, 'text:list', attrib={
                    'text:style-name': self.rststyle('epigraph-bulletlist'),
                    })
                self.list_style_stack.append(self.rststyle('epigraph-bulletitem'))
            else:
                el = SubElement(self.current_element, 'text:list', attrib={
                    'text:style-name': self.rststyle('bulletlist'),
                    })
                self.list_style_stack.append(self.rststyle('bulletitem'))
        self.set_current_element(el)

    def depart_bullet_list(self, node):
        self.set_to_parent()
        self.list_style_stack.pop()

    def visit_caption(self, node):
        raise nodes.SkipChildren()
        pass

    def depart_caption(self, node):
        pass

    def visit_comment(self, node):
        #ipshell('At visit_comment')
        el = self.append_p('textbody')
        el1 =  SubElement(el, 'office:annotation', attrib={})
        el2 =  SubElement(el1, 'text:p', attrib={})
        el2.text = node.astext()

    def depart_comment(self, node):
        pass

    def visit_compound(self, node):
        # The compound directive currently receives no special treatment.
        pass

    def depart_compound(self, node):
        pass

    def visit_container(self, node):
        styles = node.attributes.get('classes', ())
        if len(styles) > 0:
            self.paragraph_style_stack.append(self.rststyle(styles[0]))

    def depart_container(self, node):
        #ipshell('At depart_container')
        styles = node.attributes.get('classes', ())
        if len(styles) > 0:
            self.paragraph_style_stack.pop()

    def visit_decoration(self, node):
        #global DEBUG
        #ipshell('At visit_decoration')
        #DEBUG = 1
        #self.trace_visit_node(node)
        pass

    def depart_decoration(self, node):
        #ipshell('At depart_decoration')
        pass

    def visit_definition(self, node):
        self.paragraph_style_stack.append(self.rststyle('blockindent'))
        self.bumped_list_level_stack.append(ListLevel(1))

    def depart_definition(self, node):
        self.paragraph_style_stack.pop()
        self.bumped_list_level_stack.pop()

    def visit_definition_list(self, node):
        pass

    def depart_definition_list(self, node):
        pass

    def visit_definition_list_item(self, node):
        pass

    def depart_definition_list_item(self, node):
        pass

    def visit_term(self, node):
        #ipshell('At visit_term')
        el = self.append_p('textbody')
        el1 = SubElement(el, 'text:span',
            attrib={'text:style-name': self.rststyle('strong')})
        #el1.text = node.astext()
        self.set_current_element(el1)

    def depart_term(self, node):
        #ipshell('At depart_term')
        self.set_to_parent()
        self.set_to_parent()

    def visit_classifier(self, node):
        #ipshell('At visit_classifier')
        els = self.current_element.getchildren()
        if len(els) > 0:
            el = els[-1]
            el1 = SubElement(el, 'text:span',
                attrib={'text:style-name': self.rststyle('emphasis')
                })
            el1.text = ' (%s)' % (node.astext(), )

    def depart_classifier(self, node):
        pass

    def visit_document(self, node):
        #ipshell('At visit_document')
        pass

    def depart_document(self, node):
        self.process_footnotes()

    def visit_docinfo(self, node):
        #self.trace_visit_node(node)
        self.section_level += 1
        self.section_count += 1
        if self.settings.create_sections:
            el = self.append_child('text:section', attrib={
                    'text:name': 'Section%d' % self.section_count,
                    'text:style-name': 'Sect%d' % self.section_level,
                    })
            self.set_current_element(el)

    def depart_docinfo(self, node):
        #self.trace_depart_node(node)
        self.section_level -= 1
        if self.settings.create_sections:
            self.set_to_parent()

    def visit_emphasis(self, node):
        el = SubElement(self.current_element, 'text:span',
            attrib={'text:style-name': self.rststyle('emphasis')})
        self.set_current_element(el)

    def depart_emphasis(self, node):
        self.set_to_parent()

    def visit_enumerated_list(self, node):
        el1 = self.current_element
        if self.blockstyle == self.rststyle('blockquote'):
            el2 = SubElement(el1, 'text:list', attrib={
                'text:style-name': self.rststyle('blockquote-enumlist'),
                })
            self.list_style_stack.append(self.rststyle('blockquote-enumitem'))
        elif self.blockstyle == self.rststyle('highlights'):
            el2 = SubElement(el1, 'text:list', attrib={
                'text:style-name': self.rststyle('highlights-enumlist'),
                })
            self.list_style_stack.append(self.rststyle('highlights-enumitem'))
        elif self.blockstyle == self.rststyle('epigraph'):
            el2 = SubElement(el1, 'text:list', attrib={
                'text:style-name': self.rststyle('epigraph-enumlist'),
                })
            self.list_style_stack.append(self.rststyle('epigraph-enumitem'))
        else:
            el2 = SubElement(el1, 'text:list', attrib={
                'text:style-name': self.rststyle('enumlist'),
                })
            self.list_style_stack.append(self.rststyle('enumitem'))
        self.set_current_element(el2)

    def depart_enumerated_list(self, node):
        self.set_to_parent()
        self.list_style_stack.pop()

    def visit_list_item(self, node):
        #ipshell('At visit_list_item')
        el1 = self.append_child('text:list-item')
        # If we are in a "bumped" list level, then wrap this
        #   list in an outer lists in order to increase the
        #   indentation level.
        el3 = el1
        if len(self.bumped_list_level_stack) > 0:
            level_obj = self.bumped_list_level_stack[-1]
            if level_obj.get_sibling():
                level_obj.set_nested(False)
                for level_obj1 in self.bumped_list_level_stack:
                    for idx in range(level_obj1.get_level()):
                        el2 = self.append_child('text:list', parent=el3)
                        el3 = self.append_child('text:list-item', parent=el2)
        self.paragraph_style_stack.append(self.list_style_stack[-1])
        self.set_current_element(el3)

    def depart_list_item(self, node):
        if len(self.bumped_list_level_stack) > 0:
            level_obj = self.bumped_list_level_stack[-1]
            if level_obj.get_sibling():
                level_obj.set_nested(True)
                for level_obj1 in self.bumped_list_level_stack:
                    for idx in range(level_obj1.get_level()):
                        self.set_to_parent()
                        self.set_to_parent()
        self.paragraph_style_stack.pop()
        self.set_to_parent()

    def visit_header(self, node):
        #ipshell('At visit_header')
        self.in_header = True

    def depart_header(self, node):
        #ipshell('At depart_header')
        self.in_header = False

    def visit_footer(self, node):
        #ipshell('At visit_footer')
        self.in_footer = True

    def depart_footer(self, node):
        #ipshell('At depart_footer')
        self.in_footer = False

    def visit_field(self, node):
        pass

    def depart_field(self, node):
        pass

    def visit_field_list(self, node):
        #ipshell('At visit_field_list')
        pass

    def depart_field_list(self, node):
        #ipshell('At depart_field_list')
        pass

    def visit_field_name(self, node):
        #ipshell('At visit_field_name')
        #self.trace_visit_node(node)
        el = self.append_p('textbody')
        el1 = SubElement(el, 'text:span',
            attrib={'text:style-name': self.rststyle('strong')})
        el1.text = node.astext()

    def depart_field_name(self, node):
        #self.trace_depart_node(node)
        pass

    def visit_field_body(self, node):
        #ipshell('At visit_field_body')
        #self.trace_visit_node(node)
        self.paragraph_style_stack.append(self.rststyle('blockindent'))

    def depart_field_body(self, node):
        #self.trace_depart_node(node)
        self.paragraph_style_stack.pop()

    def visit_figure(self, node):
        #ipshell('At visit_figure')
        #self.trace_visit_node(node)
        pass

    def depart_figure(self, node):
        #self.trace_depart_node(node)
        pass

    def visit_footnote(self, node):
        #ipshell('At visit_footnote')
        self.footnote_level += 1
        self.save_footnote_current = self.current_element
        el1 = Element('text:note-body')
        self.current_element = el1
        self.footnote_list.append((node, el1))
        if isinstance(node, docutils.nodes.citation):
            self.paragraph_style_stack.append(self.rststyle('citation'))
        else:
            self.paragraph_style_stack.append(self.rststyle('footnote'))

    def depart_footnote(self, node):
        #ipshell('At depart_footnote')
        self.paragraph_style_stack.pop()
        self.current_element = self.save_footnote_current
        self.footnote_level -= 1

    footnote_chars = [
        '*', '**', '***',
        '++', '+++',
        '##', '###',
        '@@', '@@@',
        ]

    def visit_footnote_reference(self, node):
        #ipshell('At visit_footnote_reference')
        if self.footnote_level <= 0:
            id = node.attributes['ids'][0]
            refid = node.attributes.get('refid')
            if refid is None:
                refid = ''
            if self.settings.endnotes_end_doc:
                note_class = 'endnote'
            else:
                note_class = 'footnote'
            el1 = self.append_child('text:note', attrib={
                'text:id': '%s' % (refid, ),
                'text:note-class': note_class,
                })
            note_auto = str(node.attributes.get('auto', 1))
            if isinstance(node, docutils.nodes.citation_reference):
                citation = '[%s]' % node.astext()
                el2 = SubElement(el1, 'text:note-citation', attrib={
                    'text:label': citation,
                    })
                el2.text = citation
            elif note_auto == '1':
                el2 = SubElement(el1, 'text:note-citation', attrib={
                    'text:label': node.astext(),
                    })
                el2.text = node.astext()
            elif note_auto == '*':
                if self.footnote_chars_idx >= len(
                    ODFTranslator.footnote_chars):
                    self.footnote_chars_idx = 0
                footnote_char = ODFTranslator.footnote_chars[
                    self.footnote_chars_idx]
                self.footnote_chars_idx += 1
                el2 = SubElement(el1, 'text:note-citation', attrib={
                    'text:label': footnote_char,
                    })
                el2.text = footnote_char
            self.footnote_ref_dict[id] = el1
        raise nodes.SkipChildren()

    def depart_footnote_reference(self, node):
        #ipshell('At depart_footnote_reference')
        pass

    def visit_citation(self, node):
        #ipshell('At visit_citation')
        for id in node.attributes['ids']:
            self.citation_id = id
            break
        self.paragraph_style_stack.append(self.rststyle('blockindent'))
        self.bumped_list_level_stack.append(ListLevel(1))

    def depart_citation(self, node):
        #ipshell('At depart_citation')
        self.citation_id = None
        self.paragraph_style_stack.pop()
        self.bumped_list_level_stack.pop()

    def visit_citation_reference(self, node):
        #ipshell('At visit_citation_reference')
        if self.settings.create_links:
            id = node.attributes['refid']
            el = self.append_child('text:reference-ref', attrib={
                'text:ref-name': '%s' % (id, ),
                'text:reference-format': 'text',
                })
            el.text = '['
            self.set_current_element(el)
        elif self.current_element.text is None:
            self.current_element.text = '['
        else:
            self.current_element.text += '['

    def depart_citation_reference(self, node):
        #ipshell('At depart_citation_reference')
        self.current_element.text += ']'
        if self.settings.create_links:
            self.set_to_parent()

#     visit_citation = visit_footnote
#     depart_citation = depart_footnote
#     visit_citation_reference = visit_footnote_reference
#     depart_citation_reference = depart_footnote_reference

    def visit_label(self, node):
        #ipshell('At visit_label')
        if isinstance(node.parent, docutils.nodes.footnote):
            raise nodes.SkipChildren()
        elif self.citation_id is not None:
            el = self.append_p('textbody')
            self.set_current_element(el)
            el.text = '['
            if self.settings.create_links:
                el1 = self.append_child('text:reference-mark-start', attrib={
                        'text:name': '%s' % (self.citation_id, ),
                        })

    def depart_label(self, node):
        #ipshell('At depart_label')
        if isinstance(node.parent, docutils.nodes.footnote):
            pass
        elif self.citation_id is not None:
            self.current_element.text += ']'
            if self.settings.create_links:
                el = self.append_child('text:reference-mark-end', attrib={
                        'text:name': '%s' % (self.citation_id, ),
                        })
            self.set_to_parent()

    def visit_generated(self, node):
        pass

    def depart_generated(self, node):
        pass

    def check_file_exists(self, path):
        if os.path.exists(path):
            return 1
        else:
            return 0

    def visit_image(self, node):
        #ipshell('At visit_image')
        #self.trace_visit_node(node)
        # Capture the image file.
        if 'uri' in node.attributes:
            source = node.attributes['uri']
            if not self.check_file_exists(source):
                print 'Error: Cannot find image file %s.' % (source, )
                return
        else:
            return
        if source in self.image_dict:
            filename, destination = self.image_dict[source]
        else:
            self.image_count += 1
            filename = os.path.split(source)[1]
            destination = 'Pictures/1%08x%s' % (self.image_count, filename, )
            spec = (os.path.abspath(source), destination,)
            
            self.embedded_file_list.append(spec)
            self.image_dict[source] = (source, destination,)
        # Is this a figure (containing an image) or just a plain image?
        if self.in_paragraph:
            el1 = self.current_element
        else:
            el1 = SubElement(self.current_element, 'text:p',
                attrib={'text:style-name': self.rststyle('textbody')})
        el2 = el1
        if isinstance(node.parent, docutils.nodes.figure):
            el3, el4, caption = self.generate_figure(node, source,
                destination, el2)
            attrib = {
                'draw:blue': '0%',
                'draw:color-inversion': 'false',
                'draw:color-mode': 'standard',
                'draw:contrast': '0%',
                'draw:gamma': '100%',
                'draw:green': '0%',
                'draw:image-opacity': '100%',
                'draw:luminance': '0%',
                'draw:red': '0%',
                'fo:border': 'none',
                'fo:clip': 'rect(0in 0in 0in 0in)',
                'fo:margin-bottom': '0in',
                'fo:margin-left': '0in',
                'fo:margin-right': '0in',
                'fo:margin-top': '0in',
                'fo:padding': '0in',
                'style:horizontal-pos': 'from-left',
                'style:horizontal-rel': 'paragraph-content',
                'style:mirror': 'none',
                'style:run-through': 'foreground',
                'style:shadow': 'none',
                'style:vertical-pos': 'from-top',
                'style:vertical-rel': 'paragraph-content',
                'style:wrap': 'none',
                 }
            el5, width = self.generate_image(node, source, destination,
                el4, attrib)
            if caption is not None:
                el5.tail = caption
        else:   #if isinstance(node.parent, docutils.nodes.image):
            el3 = self.generate_image(node, source, destination, el2)

    def depart_image(self, node):
        pass

    def get_image_width_height(self, node, attr):
        size = None
        if attr in node.attributes:
            size = node.attributes[attr]
            unit = size[-2:]
            if unit.isalpha():
                size = size[:-2]
            else:
                unit = 'px'
            try:
                size = float(size)
            except ValueError, e:
                print 'Error: Invalid %s for image: "%s"' % (
                    attr, node.attributes[attr])
            size = [size, unit]
        return size

    def get_image_scale(self, node):
        if 'scale' in node.attributes:
            try:
                scale = int(node.attributes['scale'])
                if scale < 1: # or scale > 100:
                    raise ValueError
                scale = scale * 0.01
            except ValueError, e:
                print 'Error: Invalid scale for image: "%s"' % (
                    node.attributes['scale'], )
        else:
            scale = 1.0
        return scale

    def get_image_scaled_width_height(self, node, source):
        scale = self.get_image_scale(node)
        width = self.get_image_width_height(node, 'width')
        height = self.get_image_width_height(node, 'height')

        dpi = (72, 72)
        if Image is not None and source in self.image_dict:
            filename, destination = self.image_dict[source]
            imageobj = Image.open(filename, 'r')
            dpi = imageobj.info.get('dpi', dpi)
            # dpi information can be (xdpi, ydpi) or xydpi
            try: iter(dpi)
            except: dpi = (dpi, dpi)
        else:
            imageobj = None

        if width is None or height is None:
            if imageobj is None:
                raise RuntimeError, 'image size not fully specified and PIL not installed'
            if width is None: width = [imageobj.size[0], 'px']
            if height is None: height = [imageobj.size[1], 'px']

        width[0] *= scale
        height[0] *= scale
        if width[1] == 'px': width = [width[0] / dpi[0], 'in']
        if height[1] == 'px': height = [height[0] / dpi[1], 'in']

        width[0] = str(width[0])
        height[0] = str(height[0])
        return ''.join(width), ''.join(height)

    def generate_figure(self, node, source, destination, current_element):
        #ipshell('At generate_figure')
        caption = None
        width, height = self.get_image_scaled_width_height(node, source)
        for node1 in node.parent.children:
            if node1.tagname == 'caption':
                caption = node1.astext()
        self.image_style_count += 1
        #
        # Add the style for the caption.
        if caption is not None:
            attrib = {
                'style:class': 'extra',
                'style:family': 'paragraph',
                'style:name': 'Caption',
                'style:parent-style-name': 'Standard',
                }
            el1 = SubElement(self.automatic_styles, 'style:style',
                attrib=attrib, nsdict=SNSD)
            attrib = {
                'fo:margin-bottom': '0.0835in',
                'fo:margin-top': '0.0835in',
                'text:line-number': '0',
                'text:number-lines': 'false',
                }
            el2 = SubElement(el1, 'style:paragraph-properties', 
                attrib=attrib, nsdict=SNSD)
            attrib = {
                'fo:font-size': '12pt',
                'fo:font-style': 'italic',
                'style:font-name': 'Times',
                'style:font-name-complex': 'Lucidasans1',
                'style:font-size-asian': '12pt',
                'style:font-size-complex': '12pt',
                'style:font-style-asian': 'italic',
                'style:font-style-complex': 'italic',
                }
            el2 = SubElement(el1, 'style:text-properties', 
                attrib=attrib, nsdict=SNSD)
        style_name = 'rstframestyle%d' % self.image_style_count
        # Add the styles
        attrib = {
            'style:name': style_name,
            'style:family': 'graphic',
            'style:parent-style-name': 'Frame',
            }
        el1 = SubElement(self.automatic_styles, 
            'style:style', attrib=attrib, nsdict=SNSD)
        halign = 'center'
        valign = 'top'
        if 'align' in node.attributes:
            align = node.attributes['align'].split()
            for val in align:
                if val in ('left', 'center', 'right'):
                    halign = val
                elif val in ('top', 'middle', 'bottom'):
                    valign = val
        attrib = {
            'fo:margin-left': '0cm',
            'fo:margin-right': '0cm',
            'fo:margin-top': '0cm',
            'fo:margin-bottom': '0cm',
            'style:wrap': 'dynamic',
            'style:number-wrapped-paragraphs': 'no-limit',
            'style:vertical-pos': valign,
            'style:vertical-rel': 'paragraph',
            'style:horizontal-pos': halign,
            'style:horizontal-rel': 'paragraph',
            'fo:padding': '0cm',
            'fo:border': 'none',
            }
        el2 = SubElement(el1,
            'style:graphic-properties', attrib=attrib, nsdict=SNSD)
        attrib = {
            'draw:style-name': style_name,
            'draw:name': 'Frame1',
            'text:anchor-type': 'paragraph',
            'draw:z-index': '1',
            }
        attrib['svg:width'] = width
        # dbg
        #attrib['svg:height'] = height
        el3 = SubElement(current_element, 'draw:frame', attrib=attrib)
        attrib = {}
        el4 = SubElement(el3, 'draw:text-box', attrib=attrib)
        attrib = {
            'text:style-name': self.rststyle('caption'),
            }
        el5 = SubElement(el4, 'text:p', attrib=attrib)
        return el3, el5, caption

    def generate_image(self, node, source, destination, current_element,
        #ipshell('At generate_image')
        frame_attrs=None):
        width, height = self.get_image_scaled_width_height(node, source)
        self.image_style_count += 1
        style_name = 'rstframestyle%d' % self.image_style_count
        # Add the style.
        attrib = {
            'style:name': style_name,
            'style:family': 'graphic',
            'style:parent-style-name': 'Graphics',
            }
        el1 = SubElement(self.automatic_styles, 
            'style:style', attrib=attrib, nsdict=SNSD)
        halign = None
        valign = None
        if 'align' in node.attributes:
            align = node.attributes['align'].split()
            for val in align:
                if val in ('left', 'center', 'right'):
                    halign = val
                elif val in ('top', 'middle', 'bottom'):
                    valign = val
        if frame_attrs is None:
            attrib = {
                'style:vertical-pos': 'top',
                'style:vertical-rel': 'paragraph',
                #'style:horizontal-pos': halign,
                #'style:vertical-pos': valign,
                'style:horizontal-rel': 'paragraph',
                'style:mirror': 'none',
                'fo:clip': 'rect(0cm 0cm 0cm 0cm)',
                'draw:luminance': '0%',
                'draw:contrast': '0%',
                'draw:red': '0%',
                'draw:green': '0%',
                'draw:blue': '0%',
                'draw:gamma': '100%',
                'draw:color-inversion': 'false',
                'draw:image-opacity': '100%',
                'draw:color-mode': 'standard',
                }
        else:
            attrib = frame_attrs
        if halign is not None:
            attrib['style:horizontal-pos'] = halign
        if valign is not None:
            attrib['style:vertical-pos'] = valign
        #ipshell('At generate_image')
        # If we are inside a table, add a no-wrap style.
        if self.is_in_table(node):
            attrib['style:wrap'] = 'none'
        el2 = SubElement(el1,
            'style:graphic-properties', attrib=attrib, nsdict=SNSD)
        # Add the content.
        #el = SubElement(current_element, 'text:p',
        #    attrib={'text:style-name': self.rststyle('textbody')})
        attrib={
            'draw:style-name': style_name,
            'draw:name': 'graphics2',
            #'text:anchor-type': 'paragraph',
            #'svg:width': '%fcm' % (width, ),
            #'svg:height': '%fcm' % (height, ),
            'draw:z-index': '1',
            }
        if isinstance(node.parent, nodes.TextElement):
            attrib['text:anchor-type'] = 'char'
        else:
            attrib['text:anchor-type'] = 'paragraph'
        attrib['svg:width'] = width
        attrib['svg:height'] = height
        el1 = SubElement(current_element, 'draw:frame', attrib=attrib)
        el2 = SubElement(el1, 'draw:image', attrib={
            'xlink:href': '%s' % (destination, ),
            'xlink:type': 'simple',
            'xlink:show': 'embed',
            'xlink:actuate': 'onLoad',
            })
        return el1, width

    def is_in_table(self, node):
        node1 = node.parent
        while node1:
            if isinstance(node1, docutils.nodes.entry):
                return True
            node1 = node1.parent
        return False

    def visit_legend(self, node):
        # Currently, the legend receives *no* special treatment.
        #ipshell('At visit_legend')
        pass

    def depart_legend(self, node):
        pass

    def visit_line_block(self, node):
        #ipshell('At visit_line_block')
        self.line_indent_level += 1
        self.line_block_level += 1

    def depart_line_block(self, node):
        #ipshell('At depart_line_block')
        if self.line_block_level <= 1:
            el1 = SubElement(self.current_element, 'text:p', attrib={
                    'text:style-name': self.rststyle('lineblock1'),
                    })
        self.line_indent_level -= 1
        self.line_block_level -= 1

    def visit_line(self, node):
        #ipshell('At visit_line')
        style = 'lineblock%d' % self.line_indent_level
        el1 = SubElement(self.current_element, 'text:p', attrib={
                'text:style-name': self.rststyle(style),
                })
        self.current_element = el1

    def depart_line(self, node):
        #ipshell('At depart_line')
        self.set_to_parent()

    def visit_literal(self, node):
        #ipshell('At visit_literal')
        el = SubElement(self.current_element, 'text:span',
            attrib={'text:style-name': self.rststyle('inlineliteral')})
        self.set_current_element(el)

    def depart_literal(self, node):
        self.set_to_parent()

    def _calculate_code_block_padding(self, line):
        count = 0
        matchobj = SPACES_PATTERN.match(line)
        if matchobj:
            pad = matchobj.group()
            count = len(pad)
        else:
            matchobj = TABS_PATTERN.match(line)
            if matchobj:
                pad = matchobj.group()
                count = len(pad) * 8
        return count

    def _add_syntax_highlighting(self, insource, language):
        lexer = pygments.lexers.get_lexer_by_name(language, stripall=True)
        if language in ('latex', 'tex'):
            fmtr = OdtPygmentsLaTeXFormatter(lambda name, parameters=():
                self.rststyle(name, parameters))
        else:
            fmtr = OdtPygmentsProgFormatter(lambda name, parameters=():
                self.rststyle(name, parameters))
        outsource = pygments.highlight(insource, lexer, fmtr)
        return outsource

    def fill_line(self, line):
        line = FILL_PAT1.sub(self.fill_func1, line)
        line = FILL_PAT2.sub(self.fill_func2, line)
        return line

    def fill_func1(self, matchobj):
        spaces = matchobj.group(0)
        repl = '<text:s text:c="%d"/>' % (len(spaces), )
        return repl

    def fill_func2(self, matchobj):
        spaces = matchobj.group(0)
        repl = ' <text:s text:c="%d"/>' % (len(spaces) - 1, )
        return repl

    def visit_literal_block(self, node):
        #ipshell('At visit_literal_block')
        wrapper1 = '<text:p text:style-name="%s">%%s</text:p>' % (
            self.rststyle('codeblock'), )
        source = node.astext()
        if (pygments and 
            self.settings.add_syntax_highlighting and
            node.get('hilight', False)):
            language = node.get('language', 'python')
            source = self._add_syntax_highlighting(source, language)
        else:
            source = escape_cdata(source)
        lines = source.split('\n')
        lines1 = ['<wrappertag1 xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">']

        my_lines = []
        for my_line in lines:
            my_line = self.fill_line(my_line)
            my_line = my_line.replace("&#10;", "\n")
            my_lines.append(my_line)
        my_lines_str = '<text:line-break/>'.join(my_lines)
        my_lines_str2 = wrapper1 % (my_lines_str, )
        lines1.append(my_lines_str2)
        lines1.append('</wrappertag1>')
        s1 = ''.join(lines1)
        if WhichElementTree != "lxml":
            s1 = s1.encode("utf-8")
        el1 = etree.fromstring(s1)
        children = el1.getchildren()
        for child in children:
            self.current_element.append(child)

    def depart_literal_block(self, node):
        pass

    visit_doctest_block = visit_literal_block
    depart_doctest_block = depart_literal_block

    def visit_meta(self, node):
        #ipshell('At visit_meta')
        name = node.attributes.get('name')
        content = node.attributes.get('content')
        if name is not None and content is not None:
            self.meta_dict[name] = content

    def depart_meta(self, node):
        pass

    def visit_option_list(self, node):
        table_name = 'tableoption'
        #
        # Generate automatic styles
        if not self.optiontablestyles_generated:
            self.optiontablestyles_generated = True
            el = SubElement(self.automatic_styles, 'style:style', attrib={
                'style:name': self.rststyle(table_name),
                'style:family': 'table'}, nsdict=SNSD)
            el1 = SubElement(el, 'style:table-properties', attrib={
                'style:width': '17.59cm',
                'table:align': 'left',
                'style:shadow': 'none'}, nsdict=SNSD)
            el = SubElement(self.automatic_styles, 'style:style', attrib={
                'style:name': self.rststyle('%s.%%c' % table_name, ( 'A', )),
                'style:family': 'table-column'}, nsdict=SNSD)
            el1 = SubElement(el, 'style:table-column-properties', attrib={
                'style:column-width': '4.999cm'}, nsdict=SNSD)
            el = SubElement(self.automatic_styles, 'style:style', attrib={
                'style:name': self.rststyle('%s.%%c' % table_name, ( 'B', )),
                'style:family': 'table-column'}, nsdict=SNSD)
            el1 = SubElement(el, 'style:table-column-properties', attrib={
                'style:column-width': '12.587cm'}, nsdict=SNSD)
            el = SubElement(self.automatic_styles, 'style:style', attrib={
                'style:name': self.rststyle('%s.%%c%%d' % table_name, ( 'A', 1, )),
                'style:family': 'table-cell'}, nsdict=SNSD)
            el1 = SubElement(el, 'style:table-cell-properties', attrib={
                'fo:background-color': 'transparent',
                'fo:padding': '0.097cm',
                'fo:border-left': '0.035cm solid #000000',
                'fo:border-right': 'none',
                'fo:border-top': '0.035cm solid #000000',
                'fo:border-bottom': '0.035cm solid #000000'}, nsdict=SNSD)
            el2 = SubElement(el1, 'style:background-image', nsdict=SNSD)
            el = SubElement(self.automatic_styles, 'style:style', attrib={
                'style:name': self.rststyle('%s.%%c%%d' % table_name, ( 'B', 1, )),
                'style:family': 'table-cell'}, nsdict=SNSD)
            el1 = SubElement(el, 'style:table-cell-properties', attrib={
                'fo:padding': '0.097cm',
                'fo:border': '0.035cm solid #000000'}, nsdict=SNSD)
            el = SubElement(self.automatic_styles, 'style:style', attrib={
                'style:name': self.rststyle('%s.%%c%%d' % table_name, ( 'A', 2, )),
                'style:family': 'table-cell'}, nsdict=SNSD)
            el1 = SubElement(el, 'style:table-cell-properties', attrib={
                'fo:padding': '0.097cm',
                'fo:border-left': '0.035cm solid #000000',
                'fo:border-right': 'none',
                'fo:border-top': 'none',
                'fo:border-bottom': '0.035cm solid #000000'}, nsdict=SNSD)
            el = SubElement(self.automatic_styles, 'style:style', attrib={
                'style:name': self.rststyle('%s.%%c%%d' % table_name, ( 'B', 2, )),
                'style:family': 'table-cell'}, nsdict=SNSD)
            el1 = SubElement(el, 'style:table-cell-properties', attrib={
                'fo:padding': '0.097cm',
                'fo:border-left': '0.035cm solid #000000',
                'fo:border-right': '0.035cm solid #000000',
                'fo:border-top': 'none',
                'fo:border-bottom': '0.035cm solid #000000'}, nsdict=SNSD)
        #
        # Generate table data
        el = self.append_child('table:table', attrib={
            'table:name': self.rststyle(table_name),
            'table:style-name': self.rststyle(table_name),
            })
        el1 = SubElement(el, 'table:table-column', attrib={
            'table:style-name': self.rststyle('%s.%%c' % table_name, ( 'A', ))})
        el1 = SubElement(el, 'table:table-column', attrib={
            'table:style-name': self.rststyle('%s.%%c' % table_name, ( 'B', ))})
        el1 = SubElement(el, 'table:table-header-rows')
        el2 = SubElement(el1, 'table:table-row')
        el3 = SubElement(el2, 'table:table-cell', attrib={
            'table:style-name': self.rststyle('%s.%%c%%d' % table_name, ( 'A', 1, )),
            'office:value-type': 'string'})
        el4 = SubElement(el3, 'text:p', attrib={
            'text:style-name': 'Table_20_Heading'})
        el4.text= 'Option'
        el3 = SubElement(el2, 'table:table-cell', attrib={
            'table:style-name': self.rststyle('%s.%%c%%d' % table_name, ( 'B', 1, )),
            'office:value-type': 'string'})
        el4 = SubElement(el3, 'text:p', attrib={
            'text:style-name': 'Table_20_Heading'})
        el4.text= 'Description'
        self.set_current_element(el)

    def depart_option_list(self, node):
        self.set_to_parent()

    def visit_option_list_item(self, node):
        el = self.append_child('table:table-row')
        self.set_current_element(el)

    def depart_option_list_item(self, node):
        self.set_to_parent()

    def visit_option_group(self, node):
        el = self.append_child('table:table-cell', attrib={
            'table:style-name': 'Table%d.A2' % self.table_count,
            'office:value-type': 'string',
        })
        self.set_current_element(el)

    def depart_option_group(self, node):
        self.set_to_parent()

    def visit_option(self, node):
        el = self.append_child('text:p', attrib={
            'text:style-name': 'Table_20_Contents'})
        el.text = node.astext()

    def depart_option(self, node):
        pass

    def visit_option_string(self, node):
        pass

    def depart_option_string(self, node):
        pass

    def visit_option_argument(self, node):
        #ipshell('At visit_option_argument')
        pass

    def depart_option_argument(self, node):
        pass

    def visit_description(self, node):
        el = self.append_child('table:table-cell', attrib={
            'table:style-name': 'Table%d.B2' % self.table_count,
            'office:value-type': 'string',
        })
        el1 = SubElement(el, 'text:p', attrib={
            'text:style-name': 'Table_20_Contents'})
        el1.text = node.astext()
        raise nodes.SkipChildren()

    def depart_description(self, node):
        pass

    def visit_paragraph(self, node):
        #ipshell('At visit_paragraph')
        #self.trace_visit_node(node)
        self.in_paragraph = True
        if self.in_header:
            el = self.append_p('header')
        elif self.in_footer:
            el = self.append_p('footer')
        else:
            style_name = self.paragraph_style_stack[-1]
            el = self.append_child('text:p',
                attrib={'text:style-name': style_name})
            self.append_pending_ids(el)
        self.set_current_element(el)

    def depart_paragraph(self, node):
        #ipshell('At depart_paragraph')
        #self.trace_depart_node(node)
        self.in_paragraph = False
        self.set_to_parent()
        if self.in_header:
            self.header_content.append(self.current_element.getchildren()[-1])
            self.current_element.remove(self.current_element.getchildren()[-1])
        elif self.in_footer:
            self.footer_content.append(self.current_element.getchildren()[-1])
            self.current_element.remove(self.current_element.getchildren()[-1])

    def visit_problematic(self, node):
        #print '(visit_problematic) node: %s' % (node.astext(), )
        pass

    def depart_problematic(self, node):
        pass

    def visit_raw(self, node):
        #ipshell('At visit_raw')
        if 'format' in node.attributes:
            formats = node.attributes['format']
            formatlist = formats.split()
            if 'odt' in formatlist:
                rawstr = node.astext()
                attrstr = ' '.join(['%s="%s"' % (k, v, )
                    for k,v in CONTENT_NAMESPACE_ATTRIB.items()])
                contentstr = '<stuff %s>%s</stuff>' % (attrstr, rawstr, )
                if WhichElementTree != "lxml":
                    contentstr = contentstr.encode("utf-8")
                content = etree.fromstring(contentstr)
                elements = content.getchildren()
                if len(elements) > 0:
                    el1 = elements[0]
                    if self.in_header:
                        pass
                    elif self.in_footer:
                        pass
                    else:
                        self.current_element.append(el1)
        raise nodes.SkipChildren()

    def depart_raw(self, node):
        if self.in_header:
            pass
        elif self.in_footer:
            pass
        else:
            pass

    def visit_reference(self, node):
        #self.trace_visit_node(node)
        text = node.astext()
        if self.settings.create_links:
            if node.has_key('refuri'):
                    href = node['refuri']
                    if ( self.settings.cloak_email_addresses
                         and href.startswith('mailto:')):
                        href = self.cloak_mailto(href)
                    el = self.append_child('text:a', attrib={
                        'xlink:href': '%s' % href,
                        'xlink:type': 'simple',
                        })
                    self.set_current_element(el)
            elif node.has_key('refid'):
                if self.settings.create_links:
                    href = node['refid']
                    el = self.append_child('text:reference-ref', attrib={
                        'text:ref-name': '%s' % href,
                        'text:reference-format': 'text',
                        })
            else:
                raise RuntimeError, 'References must have "refuri" or "refid" attribute.'
        if (self.in_table_of_contents and
            len(node.children) >= 1 and
            isinstance(node.children[0], docutils.nodes.generated)):
            node.remove(node.children[0])

    def depart_reference(self, node):
        #self.trace_depart_node(node)
        if self.settings.create_links:
            if node.has_key('refuri'):
                self.set_to_parent()

    def visit_rubric(self, node):
        style_name = self.rststyle('rubric')
        classes = node.get('classes')
        if classes:
            class1 = classes[0]
            if class1:
                style_name = class1
        el = SubElement(self.current_element, 'text:h', attrib = {
            #'text:outline-level': '%d' % section_level,
            #'text:style-name': 'Heading_20_%d' % section_level,
            'text:style-name': style_name,
            })
        text = node.astext()
        el.text = self.encode(text)

    def depart_rubric(self, node):
        pass

    def visit_section(self, node, move_ids=1):
        #ipshell('At visit_section')
        self.section_level += 1
        self.section_count += 1
        if self.settings.create_sections:
            el = self.append_child('text:section', attrib={
                'text:name': 'Section%d' % self.section_count,
                'text:style-name': 'Sect%d' % self.section_level,
                })
            self.set_current_element(el)

    def depart_section(self, node):
        self.section_level -= 1
        if self.settings.create_sections:
            self.set_to_parent()

    def visit_strong(self, node):
        #ipshell('At visit_strong')
        el = SubElement(self.current_element, 'text:span',
            attrib={'text:style-name': self.rststyle('strong')})
        self.set_current_element(el)

    def depart_strong(self, node):
        self.set_to_parent()

    def visit_substitution_definition(self, node):
        #ipshell('At visit_substitution_definition')
        raise nodes.SkipChildren()

    def depart_substitution_definition(self, node):
        #ipshell('At depart_substitution_definition')
        pass

    def visit_system_message(self, node):
        #print '(visit_system_message) node: %s' % (node.astext(), )
        pass

    def depart_system_message(self, node):
        pass

    def visit_table(self, node):
        #self.trace_visit_node(node)
        #ipshell('At visit_table')
        self.table_count += 1
        table_name = '%s%%d' % TableStylePrefix
        el1 = SubElement(self.automatic_styles, 'style:style', attrib={
            'style:name': self.rststyle('%s' % table_name, ( self.table_count, )),
            'style:family': 'table',
            }, nsdict=SNSD)
        el1_1 = SubElement(el1, 'style:table-properties', attrib={
            #'style:width': '17.59cm',
            'table:align': 'margins',
            'fo:margin-top': '0in',
            'fo:margin-bottom': '0.10in',
            }, nsdict=SNSD)
        # We use a single cell style for all cells in this table.
        # That's probably not correct, but seems to work.
        el2 = SubElement(self.automatic_styles, 'style:style', attrib={
            'style:name': self.rststyle('%s.%%c%%d' % table_name, ( self.table_count, 'A', 1, )),
            'style:family': 'table-cell',
            }, nsdict=SNSD)
        line_style1 = '0.%03dcm solid #000000' % self.settings.table_border_thickness
        el2_1 = SubElement(el2, 'style:table-cell-properties', attrib={
            'fo:padding': '0.049cm',
            'fo:border-left': line_style1,
            'fo:border-right': line_style1,
            'fo:border-top': line_style1,
            'fo:border-bottom': line_style1,
            }, nsdict=SNSD)
        title = None
        for child in node.children:
            if child.tagname == 'title':
                title = child.astext()
                break
        if title is not None:
            el3 = self.append_p('table-title', title)
        else:
            #print 'no table title'
            pass
        el4 = SubElement(self.current_element, 'table:table', attrib={
            'table:name': self.rststyle('%s' % table_name, ( self.table_count, )),
            'table:style-name': self.rststyle('%s' % table_name, ( self.table_count, )),
            })
        self.set_current_element(el4)
        self.current_table_style = el1
        self.table_width = 0

    def depart_table(self, node):
        #self.trace_depart_node(node)
        #ipshell('At depart_table')
        attribkey = add_ns('style:width', nsdict=SNSD)
        attribval = '%dcm' % self.table_width
        self.current_table_style.attrib[attribkey] = attribval
        self.set_to_parent()

    def visit_tgroup(self, node):
        #self.trace_visit_node(node)
        #ipshell('At visit_tgroup')
        self.column_count = ord('A') - 1

    def depart_tgroup(self, node):
        #self.trace_depart_node(node)
        pass

    def visit_colspec(self, node):
        #self.trace_visit_node(node)
        #ipshell('At visit_colspec')
        self.column_count += 1
        colspec_name = self.rststyle('%s%%d.%%s' % TableStylePrefix, ( self.table_count, chr(self.column_count), ))
        colwidth = node['colwidth']
        el1 = SubElement(self.automatic_styles, 'style:style', attrib={
            'style:name': colspec_name,
            'style:family': 'table-column',
            }, nsdict=SNSD)
        el1_1 = SubElement(el1, 'style:table-column-properties', attrib={
            'style:column-width': '%dcm' % colwidth }, nsdict=SNSD)
        el2 = self.append_child('table:table-column', attrib={
            'table:style-name': colspec_name,
            })
        self.table_width += colwidth

    def depart_colspec(self, node):
        #self.trace_depart_node(node)
        pass

    def visit_thead(self, node):
        #self.trace_visit_node(node)
        #ipshell('At visit_thead')
        el = self.append_child('table:table-header-rows')
        self.set_current_element(el)
        self.in_thead = True
        self.paragraph_style_stack.append('Table_20_Heading')

    def depart_thead(self, node):
        #self.trace_depart_node(node)
        self.set_to_parent()
        self.in_thead = False
        self.paragraph_style_stack.pop()

    def visit_row(self, node):
        #self.trace_visit_node(node)
        #ipshell('At visit_row')
        self.column_count = ord('A') - 1
        el = self.append_child('table:table-row')
        self.set_current_element(el)

    def depart_row(self, node):
        #self.trace_depart_node(node)
        self.set_to_parent()

    def visit_entry(self, node):
        #self.trace_visit_node(node)
        #ipshell('At visit_entry')
        self.column_count += 1
        cellspec_name = self.rststyle('%s%%d.%%c%%d' % TableStylePrefix, ( self.table_count, 'A', 1, ))
        attrib={
            'table:style-name': cellspec_name,
            'office:value-type': 'string',
            }
        morecols = node.get('morecols', 0)
        if morecols > 0:
            attrib['table:number-columns-spanned'] = '%d' % (morecols + 1,)
            self.column_count += morecols
        morerows = node.get('morerows', 0)
        if morerows > 0:
            attrib['table:number-rows-spanned'] = '%d' % (morerows + 1,)
        el1 = self.append_child('table:table-cell', attrib=attrib)
        self.set_current_element(el1)

    def depart_entry(self, node):
        #self.trace_depart_node(node)
        self.set_to_parent()

    def visit_tbody(self, node):
        #self.trace_visit_node(node)
        #ipshell('At visit_')
        pass

    def depart_tbody(self, node):
        #self.trace_depart_node(node)
        pass

    def visit_target(self, node):
        #
        # I don't know how to implement targets in ODF.
        # How do we create a target in oowriter?  A cross-reference?
        if not (node.has_key('refuri') or node.has_key('refid')
                or node.has_key('refname')):
            pass
        else:
            pass

    def depart_target(self, node):
        pass

    def visit_title(self, node, move_ids=1, title_type='title'):
        #ipshell('At visit_title')
        if isinstance(node.parent, docutils.nodes.section):
            section_level = self.section_level
            if section_level > 7:
                print 'Warning: Heading/section levels greater than 7 not supported.'
                print '    Reducing to heading level 7 for heading:'
                print '    "%s"' % node.astext()
                section_level = 7
            el1 = self.append_child('text:h', attrib = {
                'text:outline-level': '%d' % section_level,
                #'text:style-name': 'Heading_20_%d' % section_level,
                'text:style-name': self.rststyle('heading%d', (section_level, )),
                })
            self.append_pending_ids(el1)
            self.set_current_element(el1)
        elif isinstance(node.parent, docutils.nodes.document):
            #    text = self.settings.title
            #else:
            #    text = node.astext()
            el1 = SubElement(self.current_element, 'text:p', attrib = {
                'text:style-name': self.rststyle(title_type),
                })
            self.append_pending_ids(el1)
            text = node.astext()
            self.title = text
            self.found_doc_title = True
            self.set_current_element(el1)

    def depart_title(self, node):
        if (isinstance(node.parent, docutils.nodes.section) or
            isinstance(node.parent, docutils.nodes.document)):
            self.set_to_parent()

    def visit_subtitle(self, node, move_ids=1):
        self.visit_title(node, move_ids, title_type='subtitle')

    def depart_subtitle(self, node):
        self.depart_title(node)
    
    def visit_title_reference(self, node):
        #ipshell('At visit_title_reference')
        el = self.append_child('text:span', attrib={
            'text:style-name': self.rststyle('quotation')})
        el.text = self.encode(node.astext())
        raise nodes.SkipChildren()

    def depart_title_reference(self, node):
        pass

    def visit_topic(self, node):
        #ipshell('At visit_topic')
        if 'classes' in node.attributes:
            if 'contents' in node.attributes['classes']:
                el = self.append_p('horizontalline')
                el = self.append_p('centeredtextbody')
                el1 = SubElement(el, 'text:span',
                    attrib={'text:style-name': self.rststyle('strong')})
                el1.text = 'Contents'
                self.in_table_of_contents = True
            elif 'abstract' in node.attributes['classes']:
                el = self.append_p('horizontalline')
                el = self.append_p('centeredtextbody')
                el1 = SubElement(el, 'text:span',
                    attrib={'text:style-name': self.rststyle('strong')})
                el1.text = 'Abstract'

    def depart_topic(self, node):
        #ipshell('At depart_topic')
        if 'classes' in node.attributes:
            if 'contents' in node.attributes['classes']:
                el = self.append_p('horizontalline')
                self.in_table_of_contents = False

    def visit_transition(self, node):
        el = self.append_p('horizontalline')

    def depart_transition(self, node):
        pass

    #
    # Admonitions
    #
    def visit_warning(self, node):
        self.generate_admonition(node, 'warning')

    def depart_warning(self, node):
        self.paragraph_style_stack.pop()

    def visit_attention(self, node):
        self.generate_admonition(node, 'attention')

    depart_attention = depart_warning

    def visit_caution(self, node):
        self.generate_admonition(node, 'caution')

    depart_caution = depart_warning

    def visit_danger(self, node):
        self.generate_admonition(node, 'danger')

    depart_danger = depart_warning

    def visit_error(self, node):
        self.generate_admonition(node, 'error')

    depart_error = depart_warning

    def visit_hint(self, node):
        self.generate_admonition(node, 'hint')

    depart_hint = depart_warning

    def visit_important(self, node):
        self.generate_admonition(node, 'important')

    depart_important = depart_warning

    def visit_note(self, node):
        self.generate_admonition(node, 'note')

    depart_note = depart_warning

    def visit_tip(self, node):
        self.generate_admonition(node, 'tip')

    depart_tip = depart_warning

    def visit_admonition(self, node):
        #import pdb; pdb.set_trace()
        title = None
        for child in node.children:
            if child.tagname == 'title':
                title = child.astext()
        if title is None:
            classes1 = node.get('classes')
            if classes1:
                title = classes1[0]
        self.generate_admonition(node, 'generic', title)

    depart_admonition = depart_warning

    def generate_admonition(self, node, label, title=None):
        el1 = SubElement(self.current_element, 'text:p', attrib = {
            'text:style-name': self.rststyle('admon-%s-hdr', ( label, )),
            })
        if title:
            el1.text = title
        else:
            el1.text = '%s!' % (label.capitalize(), )
        s1 = self.rststyle('admon-%s-body', ( label, ))
        self.paragraph_style_stack.append(s1)

    #
    # Roles (e.g. subscript, superscript, strong, ...
    #
    def visit_subscript(self, node):
        el = self.append_child('text:span', attrib={
            'text:style-name': 'rststyle-subscript',
            })
        self.set_current_element(el)

    def depart_subscript(self, node):
        self.set_to_parent()

    def visit_superscript(self, node):
        el = self.append_child('text:span', attrib={
            'text:style-name': 'rststyle-superscript',
            })
        self.set_current_element(el)

    def depart_superscript(self, node):
        self.set_to_parent()


# Use an own reader to modify transformations done.
class Reader(standalone.Reader):

    def get_transforms(self):
        default = standalone.Reader.get_transforms(self)
        if self.settings.create_links:
            return default
        return [ i
                 for i in default
                 if i is not references.DanglingReferences ]
