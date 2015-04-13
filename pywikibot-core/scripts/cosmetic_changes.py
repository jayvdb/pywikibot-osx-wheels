#!/usr/bin/python
# -*- coding: utf-8  -*-
"""
This module can do slight modifications to tidy a wiki page's source code.

The changes are not supposed to change the look of the rendered wiki page.

The following parameters are supported:

&params;

-always           Don't prompt you for each replacement. Warning (see below)
                  has not to be confirmed. ATTENTION: Use this with care!

-async            Put page on queue to be saved to wiki asynchronously.

-summary:XYZ      Set the summary message text for the edit to XYZ, bypassing
                  the predefined message texts with original and replacements
                  inserted.

-ignore:          Ignores if an error occured and either skips the page or
                  only that method. It can be set to 'page' or 'method'.

&warning;

For regular use, it is recommended to put this line into your user-config.py:

    cosmetic_changes = True

You may enable cosmetic changes for additional languages by adding the
dictionary cosmetic_changes_enable to your user-config.py. It should contain
a tuple of languages for each site where you wish to enable in addition to
your own langlanguage if cosmetic_changes_mylang_only is True (see below).
Please set your dictionary by adding such lines to your user-config.py:

    cosmetic_changes_enable['wikipedia'] = ('de', 'en', 'fr')

There is another config variable: You can set

    cosmetic_changes_mylang_only = False

if you're running a bot on multiple sites and want to do cosmetic changes on
all of them, but be careful if you do.

You may disable cosmetic changes by adding the all unwanted languages to the
dictionary cosmetic_changes_disable in your user-config.py. It should contain
a tuple of languages for each site where you wish to disable cosmetic changes.
You may use it with cosmetic_changes_mylang_only is False, but you can also
disable your own language. This also overrides the settings in the dictionary
cosmetic_changes_enable. Please set this dictionary by adding such lines to
your user-config.py:

    cosmetic_changes_disable['wikipedia'] = ('de', 'en', 'fr')

You may disable cosmetic changes for a given script by appending the all
unwanted scripts to the list cosmetic_changes_deny_script in your
user-config.py. By default it contains cosmetic_changes.py itself and touch.py.
This overrides all other enabling settings for cosmetic changes. Please modify
the given list by adding such lines to your user-config.py:

    cosmetic_changes_deny_script.append('your_script_name_1')

or by adding a list to the given one:

    cosmetic_changes_deny_script += ['your_script_name_1', 'your_script_name_2']
"""
#
# (C) xqt, 2009-2013
# (C) Pywikibot team, 2006-2014
#
# Distributed under the terms of the MIT license.
#
from __future__ import unicode_literals

__version__ = '$Id$'
#

import re
from pywikibot.tools import MediaWikiVersion
import pywikibot
import isbn
from pywikibot import config, i18n, textlib, pagegenerators
from pywikibot.bot import ExistingPageBot, NoRedirectPageBot
from pywikibot.page import url2unicode
from pywikibot.tools import deprecate_arg

warning = """
ATTENTION: You can run this script as a stand-alone for testing purposes.
However, the changes that are made are only minor, and other users
might get angry if you fill the version histories and watchlists with such
irrelevant changes. Some wikis prohibit stand-alone running."""

docuReplacements = {
    '&params;': pagegenerators.parameterHelp,
    '&warning;': warning,
}

# This is from interwiki.py;
# move it to family file and implement global instances
moved_links = {
    'ca': (u'ús de la plantilla', u'/ús'),
    'cs': (u'dokumentace', u'/doc'),
    'de': (u'dokumentation', u'/Meta'),
    'en': ([u'documentation',
            u'template documentation',
            u'template doc',
            u'doc',
            u'documentation, template'], u'/doc'),
    'es': ([u'documentación', u'documentación de plantilla'], u'/doc'),
    'fa': ([u'documentation', u'توضیحات', u'توضیحات الگو',
            u'doc'], u'/توضیحات'),
    'fr': (u'/documentation', u'/Documentation'),
    'hu': (u'sablondokumentáció', u'/doc'),
    'id': (u'template doc', u'/doc'),
    'ja': (u'documentation', u'/doc'),
    'ka': (u'თარგის ინფო', u'/ინფო'),
    'ko': (u'documentation', u'/설명문서'),
    'ms': (u'documentation', u'/doc'),
    'pl': (u'dokumentacja', u'/opis'),
    'pt': ([u'documentação', u'/doc'], u'/doc'),
    'ro': (u'documentaţie', u'/doc'),
    'ru': (u'doc', u'/doc'),
    'sv': (u'dokumentation', u'/dok'),
    'vi': (u'documentation', u'/doc'),
    'zh': ([u'documentation', u'doc'], u'/doc'),
}

# Template which should be replaced or removed.
# Use a list with two entries. The first entry will be replaced by the second.
# Examples:
# For removing {{Foo}}, the list must be:
#           (u'Foo', None),
#
# The following also works:
#           (u'Foo', ''),
#
# For replacing {{Foo}} with {{Bar}} the list must be:
#           (u'Foo', u'Bar'),
#
# This also removes all template parameters of {{Foo}}
# For replacing {{Foo}} with {{Bar}} but keep the template
# parameters in its original order, please use:
#           (u'Foo', u'Bar\g<parameters>'),

deprecatedTemplates = {
    'wikipedia': {
        'de': [
            (u'Belege', u'Belege fehlen\\g<parameters>'),
            (u'Quelle', u'Belege fehlen\\g<parameters>'),
            (u'Quellen', u'Belege fehlen\\g<parameters>'),
            (u'Quellen fehlen', u'Belege fehlen\\g<parameters>'),
        ],
    }
}


CANCEL_ALL = False
CANCEL_PAGE = 1
CANCEL_METHOD = 2


class CosmeticChangesToolkit:

    """Cosmetic changes toolkit."""

    @deprecate_arg('debug', 'diff')
    def __init__(self, site, diff=False, redirect=False, namespace=None,
                 pageTitle=None, ignore=CANCEL_ALL):
        self.site = site
        self.diff = diff
        self.redirect = redirect
        self.namespace = namespace
        self.template = (self.namespace == 10)
        self.talkpage = self.namespace >= 0 and self.namespace % 2 == 1
        self.title = pageTitle
        self.ignore = ignore

        self.common_methods = (
            self.commonsfiledesc,
            self.fixSelfInterwiki,
            self.standardizePageFooter,
            self.fixSyntaxSave,
            self.cleanUpLinks,
            self.cleanUpSectionHeaders,
            self.putSpacesInLists,
            self.translateAndCapitalizeNamespaces,
# FIXME:    self.translateMagicWords,
            self.replaceDeprecatedTemplates,
# FIXME:    self.resolveHtmlEntities,
            self.removeUselessSpaces,
            self.removeNonBreakingSpaceBeforePercent,

            self.fixHtml,
            self.fixReferences,
            self.fixStyle,
            self.fixTypo,

            self.fixArabicLetters,
        )

    @classmethod
    def from_page(cls, page, diff, ignore):
        """Create toolkit based on the page."""
        return cls(page.site, diff=diff, namespace=page.namespace(),
                   pageTitle=page.title(), ignore=ignore)

    def safe_execute(self, method, text):
        """Execute the method and catch exceptions if enabled."""
        result = None
        try:
            result = method(text)
        except Exception as e:
            if self.ignore == CANCEL_METHOD:
                pywikibot.warning(u'Unable to perform "{0}" on "{1}"!'.format(
                    method.__name__, self.title))
                pywikibot.exception(e)
            else:
                raise
        return text if result is None else result

    @staticmethod
    def isbn_execute(text):
        """Hyphenate ISBN numbers and catch 'InvalidIsbnException'."""
        try:
            return isbn.hyphenateIsbnNumbers(text)
        except isbn.InvalidIsbnException as error:
            pywikibot.log(u"ISBN error: %s" % error)
            return None

    def _change(self, text):
        """Execute all clean up methods."""
        for method in self.common_methods:
            text = self.safe_execute(method, text)
        text = self.safe_execute(CosmeticChangesToolkit.isbn_execute, text)
        return text

    def change(self, text):
        """Execute all clean up methods and catch errors if activated."""
        try:
            new_text = self._change(text)
        except Exception as e:
            if self.ignore == CANCEL_PAGE:
                pywikibot.warning(u'Skipped "{0}", because an error occured.'.format(self.title))
                pywikibot.exception(e)
                return False
            else:
                raise
        else:
            if self.diff:
                pywikibot.showDiff(text, new_text)
            return new_text

    def fixSelfInterwiki(self, text):
        """
        Interwiki links to the site itself are displayed like local links.

        Remove their language code prefix.
        """
        if not self.talkpage and pywikibot.calledModuleName() != 'interwiki':
            interwikiR = re.compile(r'\[\[%s\s?:([^\[\]\n]*)\]\]'
                                    % self.site.code)
            text = interwikiR.sub(r'[[\1]]', text)
        return text

    def standardizePageFooter(self, text):
        """
        Standardize page footer.

        Makes sure that interwiki links, categories and star templates are
        put to the correct position and into the right order. This combines the
        old instances standardizeInterwiki and standardizeCategories
        The page footer has the following section in that sequence:
        1. categories
        2. ## TODO: template beyond categories ##
        3. additional information depending on local site policy
        4. stars templates for featured and good articles
        5. interwiki links

        """
        starsList = [
            u'bueno',
            u'bom interwiki',
            u'cyswllt[ _]erthygl[ _]ddethol', u'dolen[ _]ed',
            u'destacado', u'destaca[tu]',
            u'enllaç[ _]ad',
            u'enllaz[ _]ad',
            u'leam[ _]vdc',
            u'legătură[ _]a[bcf]',
            u'liamm[ _]pub',
            u'lien[ _]adq',
            u'lien[ _]ba',
            u'liên[ _]kết[ _]bài[ _]chất[ _]lượng[ _]tốt',
            u'liên[ _]kết[ _]chọn[ _]lọc',
            u'ligam[ _]adq',
            u'ligazón[ _]a[bd]',
            u'ligoelstara',
            u'ligoleginda',
            u'link[ _][afgu]a', u'link[ _]adq', u'link[ _]f[lm]', u'link[ _]km',
            u'link[ _]sm', u'linkfa',
            u'na[ _]lotura',
            u'nasc[ _]ar',
            u'tengill[ _][úg]g',
            u'ua',
            u'yüm yg',
            u'רא',
            u'وصلة مقالة جيدة',
            u'وصلة مقالة مختارة',
        ]

        categories = None
        interwikiLinks = None
        allstars = []

        # The PyWikipediaBot is no longer allowed to touch categories on the
        # German Wikipedia. See
        # https://de.wikipedia.org/wiki/Hilfe_Diskussion:Personendaten/Archiv/1#Position_der_Personendaten_am_.22Artikelende.22
        # ignoring nn-wiki of cause of the comment line above iw section
        if not self.template and '{{Personendaten' not in text and \
           '{{SORTIERUNG' not in text and '{{DEFAULTSORT' not in text and \
           self.site.code not in ('et', 'it', 'bg', 'ru'):
            categories = textlib.getCategoryLinks(text, site=self.site)

        if not self.talkpage:  # and pywikibot.calledModuleName() <> 'interwiki':
            subpage = False
            if self.template:
                loc = None
                try:
                    tmpl, loc = moved_links[self.site.code]
                    del tmpl
                except KeyError:
                    pass
                if loc is not None and loc in self.title:
                    subpage = True
            interwikiLinks = textlib.getLanguageLinks(
                text, insite=self.site, template_subpage=subpage)

            # Removing the interwiki
            text = textlib.removeLanguageLinks(text, site=self.site)
            # Removing the stars' issue
            starstext = textlib.removeDisabledParts(text)
            for star in starsList:
                regex = re.compile(r'(\{\{(?:template:|)%s\|.*?\}\}[\s]*)'
                                   % star, re.I)
                found = regex.findall(starstext)
                if found != []:
                    text = regex.sub('', text)
                    allstars += found

        # Adding categories
        if categories:
            # TODO: Sorting categories in alphabetic order.
            # e.g. using categories.sort()

            # TODO: Taking main cats to top
            #   for name in categories:
            #       if re.search(u"(.+?)\|(.{,1}?)",name.title()) or name.title()==name.title().split(":")[0]+title:
            #            categories.remove(name)
            #            categories.insert(0, name)
            text = textlib.replaceCategoryLinks(text, categories,
                                                site=self.site)
        # Adding stars templates
        if allstars:
            text = text.strip() + self.site.family.interwiki_text_separator
            allstars.sort()
            for element in allstars:
                text += '%s%s' % (element.strip(), config.line_separator)
                pywikibot.log(u'%s' % element.strip())
        # Adding the interwiki
        if interwikiLinks:
            text = textlib.replaceLanguageLinks(text, interwikiLinks,
                                                site=self.site,
                                                template=self.template,
                                                template_subpage=subpage)
        return text

    def translateAndCapitalizeNamespaces(self, text):
        """Use localized namespace names."""
        # arz uses english stylish codes
        if self.site.sitename() == 'wikipedia:arz':
            return text
        family = self.site.family
        # wiki links aren't parsed here.
        exceptions = ['nowiki', 'comment', 'math', 'pre']

        for nsNumber in self.site.namespaces():
            if nsNumber in (0, 2, 3):
                # skip main (article) namespace
                # skip user namespace, maybe gender is used
                continue
            # a clone is needed. Won't change the namespace dict
            namespaces = list(self.site.namespace(nsNumber, all=True))
            thisNs = namespaces.pop(0)
            if nsNumber == 6 and family.name == 'wikipedia':
                if self.site.code in ('en', 'fr') and \
                   MediaWikiVersion(self.site.version()) >= MediaWikiVersion('1.14'):
                    # do not change "Image" on en-wiki and fr-wiki
                    assert u'Image' in namespaces
                    namespaces.remove(u'Image')
                if self.site.code == 'hu':
                    # do not change "Kép" on hu-wiki
                    assert u'Kép' in namespaces
                    namespaces.remove(u'Kép')
                elif self.site.code == 'pt':
                    # bug 55242 should be implemented
                    continue
            # lowerspaced and underscored namespaces
            for i in range(len(namespaces)):
                item = namespaces[i].replace(' ', '[ _]')
                item = u'[%s%s]' % (item[0], item[0].lower()) + item[1:]
                namespaces[i] = item
            namespaces.append(thisNs[0].lower() + thisNs[1:])
            if thisNs and namespaces:
                text = textlib.replaceExcept(
                    text,
                    r'\[\[\s*(%s) *:(?P<nameAndLabel>.*?)\]\]'
                    % '|'.join(namespaces),
                    r'[[%s:\g<nameAndLabel>]]' % thisNs,
                    exceptions)
        return text

    def translateMagicWords(self, text):
        """Use localized magic words."""
        # not wanted at ru
        # arz uses english stylish codes
        if self.site.code not in ['arz', 'ru']:
            exceptions = ['nowiki', 'comment', 'math', 'pre']
            for magicWord in ['img_thumbnail', 'img_left', 'img_center',
                              'img_right', 'img_none', 'img_framed',
                              'img_frameless', 'img_border', 'img_upright', ]:
                aliases = self.site.getmagicwords(magicWord)
                if not aliases:
                    continue
                text = textlib.replaceExcept(
                    text,
                    r'\[\[(?P<left>.+?:.+?\..+?\|) *(' + '|'.join(aliases) +
                    r') *(?P<right>(\|.*?)?\]\])',
                    r'[[\g<left>' + aliases[0] + r'\g<right>', exceptions)
        return text

    def cleanUpLinks(self, text):
        # helper function which works on one link and either returns it
        # unmodified, or returns a replacement.
        def handleOneLink(match):
            titleWithSection = match.group('titleWithSection')
            label = match.group('label')
            trailingChars = match.group('linktrail')
            newline = match.group('newline')

            if not self.site.isInterwikiLink(titleWithSection):
                # The link looks like this:
                # [[page_title|link_text]]trailing_chars
                # We only work on namespace 0 because pipes and linktrails work
                # differently for images and categories.
                page = pywikibot.Page(pywikibot.Link(titleWithSection,
                                                     self.site))
                try:
                    namespace = page.namespace()
                except pywikibot.InvalidTitle:
                    return match.group()
                if namespace == 0:
                    # Replace underlines by spaces, also multiple underlines
                    titleWithSection = re.sub('_+', ' ', titleWithSection)
                    # Remove double spaces
                    titleWithSection = re.sub('  +', ' ', titleWithSection)
                    # Remove unnecessary leading spaces from title,
                    # but remember if we did this because we eventually want
                    # to re-add it outside of the link later.
                    titleLength = len(titleWithSection)
                    titleWithSection = titleWithSection.lstrip()
                    hadLeadingSpaces = (len(titleWithSection) != titleLength)
                    hadTrailingSpaces = False
                    # Remove unnecessary trailing spaces from title,
                    # but remember if we did this because it may affect
                    # the linktrail and because we eventually want to
                    # re-add it outside of the link later.
                    if not trailingChars:
                        titleLength = len(titleWithSection)
                        titleWithSection = titleWithSection.rstrip()
                        hadTrailingSpaces = (len(titleWithSection) !=
                                             titleLength)

                    # Convert URL-encoded characters to unicode
                    titleWithSection = url2unicode(titleWithSection,
                                                   encodings=self.site)

                    if titleWithSection == '':
                        # just skip empty links.
                        return match.group()

                    # Remove unnecessary initial and final spaces from label.
                    # Please note that some editors prefer spaces around pipes.
                    # (See [[en:Wikipedia:Semi-bots]]). We remove them anyway.
                    if label is not None:
                        # Remove unnecessary leading spaces from label,
                        # but remember if we did this because we want
                        # to re-add it outside of the link later.
                        labelLength = len(label)
                        label = label.lstrip()
                        hadLeadingSpaces = (len(label) != labelLength)
                        # Remove unnecessary trailing spaces from label,
                        # but remember if we did this because it affects
                        # the linktrail.
                        if not trailingChars:
                            labelLength = len(label)
                            label = label.rstrip()
                            hadTrailingSpaces = (len(label) != labelLength)
                    else:
                        label = titleWithSection
                    if trailingChars:
                        label += trailingChars

                    if titleWithSection == label or \
                       titleWithSection[0].lower() + \
                       titleWithSection[1:] == label:
                        newLink = "[[%s]]" % label
                    # Check if we can create a link with trailing characters
                    # instead of a pipelink
                    elif (len(titleWithSection) <= len(label) and
                          label[:len(titleWithSection)] == titleWithSection and
                          re.sub(trailR, '',
                                 label[len(titleWithSection):]) == ''):
                        newLink = "[[%s]]%s" % (label[:len(titleWithSection)],
                                                label[len(titleWithSection):])
                    else:
                        # Try to capitalize the first letter of the title.
                        # Not useful for languages that don't capitalize nouns.
                        # TODO: Add a configuration variable for each site,
                        # which determines if the link target is written in
                        # uppercase
                        if self.site.sitename() == 'wikipedia:de':
                            titleWithSection = (titleWithSection[0].upper() +
                                                titleWithSection[1:])
                        newLink = "[[%s|%s]]" % (titleWithSection, label)
                    # re-add spaces that were pulled out of the link.
                    # Examples:
                    #   text[[ title ]]text        -> text [[title]] text
                    #   text[[ title | name ]]text -> text [[title|name]] text
                    #   text[[ title |name]]text   -> text[[title|name]]text
                    #   text[[title| name]]text    -> text [[title|name]]text
                    if hadLeadingSpaces and not newline:
                        newLink = ' ' + newLink
                    if hadTrailingSpaces:
                        newLink = newLink + ' '
                    if newline:
                        newLink = newline + newLink
                    return newLink
            # don't change anything
            return match.group()

        trailR = re.compile(self.site.linktrail())
    # The regular expression which finds links. Results consist of four groups:
    # group <newline> depends whether the links starts with a new line.
    # group <titleWithSection> is the page title and section, that is,
    # everything before | or ]. It'll include the # to make life easier for us.
    # group <label> is the alternative link title between | and ].
    # group <linktrail> is the link trail after ]] which are part of the word.
    # note that the definition of 'letter' varies from language to language.
        linkR = re.compile(
            r'(?P<newline>[\n]*)\[\[(?P<titleWithSection>[^\]\|]+)(\|(?P<label>[^\]\|]*))?\]\](?P<linktrail>' +
            self.site.linktrail() + ')')

        text = textlib.replaceExcept(text, linkR, handleOneLink,
                                     ['comment', 'math', 'nowiki', 'pre',
                                      'startspace'])
        return text

    def resolveHtmlEntities(self, text):
        ignore = [
            38,     # Ampersand (&amp;)
            39,     # Single quotation mark (&quot;) - Bugzilla 24093
            60,     # Less than (&lt;)
            62,     # Great than (&gt;)
            91,     # Opening square bracket ([)
                    # - sometimes used intentionally inside links
            93,     # Closing square bracket (])
                    # - used intentionally inside links
            124,    # Vertical bar (|)
                    # - used intentionally in navigation bar templates on w:de
            160,    # Non-breaking space (&nbsp;)
                    # - not supported by Firefox textareas
            173,    # Soft-hypen (&shy;) - enable editing
            8206,   # Left-to-right mark (&ltr;)
            8207,   # Right-to-left mark (&rtl;)
        ]
        if self.template:
            ignore += [58]
        text = pywikibot.html2unicode(text, ignore=ignore)
        return text

    def removeUselessSpaces(self, text):
        multipleSpacesR = re.compile('  +')
        spaceAtLineEndR = re.compile(' $')
        exceptions = ['comment', 'math', 'nowiki', 'pre', 'startspace', 'table',
                      'template']
        text = textlib.replaceExcept(text, multipleSpacesR, ' ', exceptions)
        text = textlib.replaceExcept(text, spaceAtLineEndR, '', exceptions)
        return text

    def removeNonBreakingSpaceBeforePercent(self, text):
        """
        Remove a non-breaking space between number and percent sign.

        Newer MediaWiki versions automatically place a non-breaking space in
        front of a percent sign, so it is no longer required to place it
        manually.

        FIXME: which version should this be run on?
        """
        text = textlib.replaceExcept(text, r'(\d)&nbsp;%', r'\1 %',
                                     ['timeline'])
        return text

    def cleanUpSectionHeaders(self, text):
        """
        Add a space between the equal signs and the section title.

        Example: ==Section title== becomes == Section title ==

        NOTE: This space is recommended in the syntax help on the English and
        German Wikipedia. It might be that it is not wanted on other wikis.
        If there are any complaints, please file a bug report.
        """
        return textlib.replaceExcept(
            text,
            r'(?m)^(={1,7}) *(?P<title>[^=]+?) *\1 *\r?\n',
            r'\1 \g<title> \1%s' % config.LS,
            ['comment', 'math', 'nowiki', 'pre'])

    def putSpacesInLists(self, text):
        """
        Add a space between the * or # and the text.

        NOTE: This space is recommended in the syntax help on the English,
        German, and French Wikipedia. It might be that it is not wanted on other
        wikis. If there are any complaints, please file a bug report.
        """
        if not self.template:
            exceptions = ['comment', 'math', 'nowiki', 'pre', 'source', 'template',
                          'timeline', self.site.redirectRegex()]
            text = textlib.replaceExcept(
                text,
                r'(?m)^(?P<bullet>[:;]*(\*+|#+)[:;\*#]*)(?P<char>[^\s\*#:;].+?)',
                r'\g<bullet> \g<char>',
                exceptions)
        return text

    def replaceDeprecatedTemplates(self, text):
        exceptions = ['comment', 'math', 'nowiki', 'pre']
        if self.site.family.name in deprecatedTemplates and \
           self.site.code in deprecatedTemplates[self.site.family.name]:
            for template in deprecatedTemplates[
                    self.site.family.name][self.site.code]:
                old = template[0]
                new = template[1]
                if new is None:
                    new = ''
                else:
                    new = '{{%s}}' % new
                if self.site.namespaces[10].case == 'first-letter':
                    old = '[' + old[0].upper() + old[0].lower() + ']' + old[1:]
                text = textlib.replaceExcept(
                    text,
                    r'\{\{([mM][sS][gG]:)?%s(?P<parameters>\|[^}]+|)}}' % old,
                    new, exceptions)
        return text

    # from fixes.py
    def fixSyntaxSave(self, text):
        exceptions = ['nowiki', 'comment', 'math', 'pre', 'source',
                      'startspace']
        # link to the wiki working on
        # TODO: disable this for difflinks and titled links,
        # to prevent edits like this:
        # https://de.wikipedia.org/w/index.php?title=Wikipedia%3aVandalismusmeldung&diff=103109563&oldid=103109271
#        text = textlib.replaceExcept(text,
#                                     r'\[https?://%s\.%s\.org/wiki/(?P<link>\S+)\s+(?P<title>.+?)\s?\]'
#                                     % (self.site.code, self.site.family.name),
#                                     r'[[\g<link>|\g<title>]]', exceptions)
        # external link in double brackets
        text = textlib.replaceExcept(
            text,
            r'\[\[(?P<url>https?://[^\]]+?)\]\]',
            r'[\g<url>]', exceptions)
        # external link starting with double bracket
        text = textlib.replaceExcept(text,
                                     r'\[\[(?P<url>https?://.+?)\]',
                                     r'[\g<url>]', exceptions)
        # external link and description separated by a dash, with
        # whitespace in front of the dash, so that it is clear that
        # the dash is not a legitimate part of the URL.
        text = textlib.replaceExcept(
            text,
            r'\[(?P<url>https?://[^\|\] \r\n]+?) +\| *(?P<label>[^\|\]]+?)\]',
            r'[\g<url> \g<label>]', exceptions)
        # dash in external link, where the correct end of the URL can
        # be detected from the file extension. It is very unlikely that
        # this will cause mistakes.
        text = textlib.replaceExcept(
            text,
            r'\[(?P<url>https?://[^\|\] ]+?(\.pdf|\.html|\.htm|\.php|\.asp|\.aspx|\.jsp)) *\| *(?P<label>[^\|\]]+?)\]',
            r'[\g<url> \g<label>]', exceptions)
        return text

    def fixHtml(self, text):
        # Everything case-insensitive (?i)
        # Keep in mind that MediaWiki automatically converts <br> to <br />
        exceptions = ['nowiki', 'comment', 'math', 'pre', 'source',
                      'startspace']
        text = textlib.replaceExcept(text, r'(?i)<b>(.*?)</b>', r"'''\1'''",
                                     exceptions)
        text = textlib.replaceExcept(text, r'(?i)<strong>(.*?)</strong>',
                                     r"'''\1'''", exceptions)
        text = textlib.replaceExcept(text, r'(?i)<i>(.*?)</i>', r"''\1''",
                                     exceptions)
        text = textlib.replaceExcept(text, r'(?i)<em>(.*?)</em>', r"''\1''",
                                     exceptions)
        # horizontal line without attributes in a single line
        text = textlib.replaceExcept(text, r'(?i)([\r\n])<hr[ /]*>([\r\n])',
                                     r'\1----\2', exceptions)
        # horizontal line with attributes; can't be done with wiki syntax
        # so we only make it XHTML compliant
        text = textlib.replaceExcept(text, r'(?i)<hr ([^>/]+?)>',
                                     r'<hr \1 />',
                                     exceptions)
        # a header where only spaces are in the same line
        for level in range(1, 7):
            equals = '\\1%s \\2 %s\\3' % ("=" * level, "=" * level)
            text = textlib.replaceExcept(
                text,
                r'(?i)([\r\n]) *<h%d> *([^<]+?) *</h%d> *([\r\n])'
                % (level, level),
                r'%s' % equals,
                exceptions)
        # TODO: maybe we can make the bot replace <p> tags with \r\n's.
        return text

    def fixReferences(self, text):
        # See also https://en.wikipedia.org/wiki/User:AnomieBOT/source/tasks/OrphanReferenceFixer.pm
        exceptions = ['nowiki', 'comment', 'math', 'pre', 'source',
                      'startspace']

        # it should be name = " or name=" NOT name   ="
        text = re.sub(r'(?i)<ref +name(= *| *=)"', r'<ref name="', text)
        # remove empty <ref/>-tag
        text = textlib.replaceExcept(text,
                                     r'(?i)(<ref\s*/>|<ref *>\s*</ref>)',
                                     r'', exceptions)
        text = textlib.replaceExcept(text,
                                     r'(?i)<ref\s+([^>]+?)\s*>\s*</ref>',
                                     r'<ref \1/>', exceptions)
        return text

    def fixStyle(self, text):
        exceptions = ['nowiki', 'comment', 'math', 'pre', 'source',
                      'startspace']
        # convert prettytable to wikitable class
        if self.site.code in ('de', 'en'):
            text = textlib.replaceExcept(text,
                                         r'(class="[^"]*)prettytable([^"]*")',
                                         r'\1wikitable\2', exceptions)
        return text

    def fixTypo(self, text):
        exceptions = ['nowiki', 'comment', 'math', 'pre', 'source',
                      'startspace', 'gallery', 'hyperlink', 'interwiki', 'link']
        # change <number> ccm -> <number> cm³
        text = textlib.replaceExcept(text, r'(\d)\s*&nbsp;ccm',
                                     r'\1&nbsp;' + u'cm³', exceptions)
        text = textlib.replaceExcept(text,
                                     r'(\d)\s*ccm', r'\1&nbsp;' + u'cm³',
                                     exceptions)
        # Solve wrong Nº sign with °C or °F
        # additional exception requested on fr-wiki for this stuff
        pattern = re.compile(u'«.*?»', re.UNICODE)
        exceptions.append(pattern)
        text = textlib.replaceExcept(text, r'(\d)\s*&nbsp;' + u'[º°]([CF])',
                                     r'\1&nbsp;' + u'°' + r'\2', exceptions)
        text = textlib.replaceExcept(text, r'(\d)\s*' + u'[º°]([CF])',
                                     r'\1&nbsp;' + u'°' + r'\2', exceptions)
        text = textlib.replaceExcept(text, u'º([CF])', u'°' + r'\1',
                                     exceptions)
        return text

    def fixArabicLetters(self, text):
        if self.site.code not in ['ckb', 'fa']:
            return
        exceptions = [
            'gallery',
            'hyperlink',
            'interwiki',
            # FIXME: but changes letters inside wikilinks
            # 'link',
            'math',
            'pre',
            'template',
            'timeline',
            'ref',
            'source',
            'startspace',
            'inputbox',
        ]
        # FIXME: use textlib.NON_LATIN_DIGITS
        # valid digits
        digits = {
            'ckb': u'٠١٢٣٤٥٦٧٨٩',
            'fa': u'۰۱۲۳۴۵۶۷۸۹',
        }
        faChrs = u'ءاآأإئؤبپتثجچحخدذرزژسشصضطظعغفقکگلمنوهیةيك' + digits['fa']
        new = digits.pop(self.site.code)
        # This only works if there are only two items in digits dict
        old = digits[digits.keys()[0]]
        # do not change inside file links
        namespaces = list(self.site.namespace(6, all=True))
        pattern = re.compile(
            u'\\[\\[(%s):.+?\\.\\w+? *(\\|((\\[\\[.*?\\]\\])|.)*)?\\]\\]'
            % u'|'.join(namespaces),
            re.UNICODE)
        # not to let bot edits in latin content
        exceptions.append(re.compile(u"[^%(fa)s] *?\"*? *?, *?[^%(fa)s]"
                                     % {'fa': faChrs}))
        exceptions.append(pattern)
        text = textlib.replaceExcept(text, u',', u'،', exceptions)
        if self.site.code == 'ckb':
            text = textlib.replaceExcept(text,
                                         u'\u0647([.\u060c_<\\]\\s])',
                                         u'\u06d5\\1', exceptions)
            text = textlib.replaceExcept(text, u'ه‌', u'ە', exceptions)
            text = textlib.replaceExcept(text, u'ه', u'ھ', exceptions)
        text = textlib.replaceExcept(text, u'ك', u'ک', exceptions)
        text = textlib.replaceExcept(text, u'[ىي]', u'ی', exceptions)

        return text

        # FIXME: split this function into two.
        # replace persian/arabic digits
        # deactivated due to bug 55185
        for i in range(0, 10):
            text = textlib.replaceExcept(text, old[i], new[i], exceptions)
        # do not change digits in class, style and table params
        pattern = re.compile(r'\w+=(".+?"|\d+)', re.UNICODE)
        exceptions.append(pattern)
        # do not change digits inside html-tags
        pattern = re.compile(u'<[/]*?[^</]+?[/]*?>', re.UNICODE)
        exceptions.append(pattern)
        exceptions.append('table')  # exclude tables for now
        # replace digits
        for i in range(0, 10):
            text = textlib.replaceExcept(text, str(i), new[i], exceptions)
        return text

    # Retrieved from "https://commons.wikimedia.org/wiki/Commons:Tools/pywiki_file_description_cleanup"
    def commonsfiledesc(self, text):
        if self.site.sitename() != u'commons:commons' or self.namespace == 6:
            return
        # section headers to {{int:}} versions
        exceptions = ['comment', 'includeonly', 'math', 'noinclude', 'nowiki',
                      'pre', 'source', 'ref', 'timeline']
        text = textlib.replaceExcept(text,
                                     r"([\r\n]|^)\=\= *Summary *\=\=",
                                     r"\1== {{int:filedesc}} ==",
                                     exceptions, True)
        text = textlib.replaceExcept(
            text,
            r"([\r\n])\=\= *\[\[Commons:Copyright tags\|Licensing\]\]: *\=\=",
            r"\1== {{int:license-header}} ==", exceptions, True)
        text = textlib.replaceExcept(
            text,
            r"([\r\n])\=\= *(Licensing|License information|{{int:license}}) *\=\=",
            r"\1== {{int:license-header}} ==", exceptions, True)

        # frequent field values to {{int:}} versions
        text = textlib.replaceExcept(
            text,
            r'([\r\n]\|[Ss]ource *\= *)(?:[Oo]wn work by uploader|[Oo]wn work|[Ee]igene [Aa]rbeit) *([\r\n])',
            r'\1{{own}}\2', exceptions, True)
        text = textlib.replaceExcept(
            text,
            r'(\| *Permission *\=) *(?:[Ss]ee below|[Ss]iehe unten) *([\r\n])',
            r'\1\2', exceptions, True)

        # added to transwikied pages
        text = textlib.replaceExcept(text, r'__NOTOC__', '', exceptions, True)

        # tracker element for js upload form
        text = textlib.replaceExcept(
            text,
            r'<!-- *{{ImageUpload\|(?:full|basic)}} *-->',
            '', exceptions[1:], True)
        text = textlib.replaceExcept(text, r'{{ImageUpload\|(?:basic|full)}}',
                                     '', exceptions, True)

        # duplicated section headers
        text = textlib.replaceExcept(
            text,
            r'([\r\n]|^)\=\= *{{int:filedesc}} *\=\=(?:[\r\n ]*)\=\= *{{int:filedesc}} *\=\=',
            r'\1== {{int:filedesc}} ==', exceptions, True)
        text = textlib.replaceExcept(
            text,
            r'([\r\n]|^)\=\= *{{int:license-header}} *\=\=(?:[\r\n ]*)\=\= *{{int:license-header}} *\=\=',
            r'\1== {{int:license-header}} ==', exceptions, True)
        return text


class CosmeticChangesBot(ExistingPageBot, NoRedirectPageBot):

    """Cosmetic changes bot."""

    def __init__(self, generator, **kwargs):
        self.availableOptions.update({
            'async': False,
            'comment': u'Robot: Cosmetic changes',
            'ignore': CANCEL_ALL,
        })
        super(CosmeticChangesBot, self).__init__(**kwargs)

        self.generator = generator

    def treat_page(self):
        """Treat page with the cosmetic toolkit."""
        try:
            ccToolkit = CosmeticChangesToolkit.from_page(
                self.current_page, False, self.getOption('ignore'))
            changedText = ccToolkit.change(self.current_page.get())
            if changedText is not False:
                self.put_current(new_text=changedText,
                                 comment=self.getOption('comment'),
                                 async=self.getOption('async'))
        except pywikibot.LockedPage:
            pywikibot.output("Page %s is locked?!"
                             % self.current_page.title(asLink=True))
        except pywikibot.EditConflict:
            pywikibot.output("An edit conflict has occured at %s."
                             % self.current_page.title(asLink=True))


def main(*args):
    """
    Process command line arguments and invoke bot.

    If args is an empty list, sys.argv is used.

    @param args: command line arguments
    @type args: list of unicode
    """
    options = {}

    # Process global args and prepare generator args parser
    local_args = pywikibot.handle_args(args)
    genFactory = pagegenerators.GeneratorFactory()

    for arg in local_args:
        if arg.startswith('-summary:'):
            options['comment'] = arg[len('-summary:'):]
        elif arg == '-always':
            options['always'] = True
        elif arg == '-async':
            options['async'] = True
        elif arg.startswith('-ignore:'):
            ignore_mode = arg[len('-ignore:'):].lower()
            if ignore_mode == 'method':
                options['ignore'] = CANCEL_METHOD
            elif ignore_mode == 'page':
                options['ignore'] = CANCEL_PAGE
            else:
                raise ValueError('Unknown ignore mode "{0}"!'.format(ignore_mode))
        else:
            genFactory.handleArg(arg)

    site = pywikibot.Site()

    if 'comment' not in options or not options['comment']:
        # Load default summary message.
        options['comment'] = i18n.twtranslate(site,
                                              'cosmetic_changes-standalone')

    gen = genFactory.getCombinedGenerator()
    if gen:
        if options.get('always') or pywikibot.input_yn(
                warning + '\nDo you really want to continue?',
                default=False, automatic_quit=False):
            site.login()
            preloadingGen = pagegenerators.PreloadingGenerator(gen)
            bot = CosmeticChangesBot(preloadingGen, **options)
            bot.run()
    else:
        pywikibot.showHelp()

if __name__ == "__main__":
    main()
