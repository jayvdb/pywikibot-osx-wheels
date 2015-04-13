#! /usr/bin/python
# -*- coding: utf-8 -*-
"""
Script to resolve double redirects, and to delete broken redirects.

Requires access to MediaWiki's maintenance pages or to a XML dump file.
Delete function requires adminship.

Syntax:

    python redirect.py action [-arguments ...]

where action can be one of these:

double         Fix redirects which point to other redirects.
do             Shortcut action command is "do".

broken         Tries to fix broken redirect to the last moved target of the
br             destination page. If this fails and -delete option is given
               it deletes redirects where targets don't exist if bot has
               admin rights otherwise it marks the page with a speedy deletion
               template if available. Shortcut action command is "br".

both           Both of the above. Retrieves redirect pages from live wiki,
               not from a special page.

and arguments can be:

-xml           Retrieve information from a local XML dump
               (https://download.wikimedia.org). Argument can also be given as
               "-xml:filename.xml". Cannot be used with -fullscan or -moves.

-fullscan      Retrieve redirect pages from live wiki, not from a special page
               Cannot be used with -xml.

-moves         Use the page move log to find double-redirect candidates. Only
               works with action "double", does not work with -xml.

               NOTE: You may use only one of these options above.
               If neither of -xml -fullscan -moves is given, info will be
               loaded from a special page of the live wiki.

-page:title    Work on a single page

-namespace:n   Namespace to process. Can be given multiple times, for several
               namespaces. If omitted, only the main (article) namespace is
               treated.

-offset:n      With -moves, the number of hours ago to start scanning moved
               pages. With -xml, the number of the redirect to restart with
               (see progress). Otherwise, ignored.

-start:title   The starting page title in each namespace. Page need not exist.

-until:title   The possible last page title in each namespace. Page needs not
               exist.

-step:n        The number of entries retrieved at oncevia API

-total:n       The maximum count of redirects to work upon. If omitted, there
               is no limit.

-delete        Enables deletion of broken redirects.

-always        Don't prompt you for each replacement.

"""
#
# (C) Daniel Herding, 2004
# (C) Purodha Blissenbach, 2009
# (C) xqt, 2009-2014
# (C) Pywikibot team, 2004-2014
#
# Distributed under the terms of the MIT license.
#
from __future__ import unicode_literals

__version__ = '$Id$'
#

import re
import datetime
import pywikibot
from pywikibot import i18n, xmlreader, Bot


def space_to_underscore(link):
    """Convert spaces to underscore."""
    # previous versions weren't expecting spaces but underscores
    return link.canonical_title().replace(' ', '_')


class RedirectGenerator:

    """Redirect generator."""

    def __init__(self, xmlFilename=None, namespaces=[], offset=-1,
                 use_move_log=False, use_api=False, start=None, until=None,
                 number=None, step=None, page_title=None):
        self.site = pywikibot.Site()
        self.xmlFilename = xmlFilename
        self.namespaces = namespaces
        if use_api and not self.namespaces:
            self.namespaces = [0]
        self.offset = offset
        self.use_move_log = use_move_log
        self.use_api = use_api
        self.api_start = start
        self.api_until = until
        self.api_number = number
        self.api_step = step
        self.page_title = page_title

    def get_redirects_from_dump(self, alsoGetPageTitles=False):
        """
        Extract redirects from dump.

        Load a local XML dump file, look at all pages which have the
        redirect flag set, and find out where they're pointing at. Return
        a dictionary where the redirect names are the keys and the redirect
        targets are the values.
        """
        xmlFilename = self.xmlFilename
        redict = {}
        # open xml dump and read page titles out of it
        dump = xmlreader.XmlDump(xmlFilename)
        redirR = self.site.redirectRegex()
        readPagesCount = 0
        if alsoGetPageTitles:
            pageTitles = set()
        for entry in dump.parse():
            readPagesCount += 1
            # always print status message after 10000 pages
            if readPagesCount % 10000 == 0:
                pywikibot.output(u'%i pages read...' % readPagesCount)
            if len(self.namespaces) > 0:
                if pywikibot.Page(self.site, entry.title).namespace() \
                        not in self.namespaces:
                    continue
            if alsoGetPageTitles:
                pageTitles.add(space_to_underscore(pywikibot.Link(entry.title, self.site)))

            m = redirR.match(entry.text)
            if m:
                target = m.group(1)
                # There might be redirects to another wiki. Ignore these.
                target_link = pywikibot.Link(target, self.site)
                try:
                    target_link.parse()
                except pywikibot.SiteDefinitionError as e:
                    pywikibot.log(e)
                    pywikibot.output(
                        u'NOTE: Ignoring {0} which is a redirect ({1}) to an '
                        u'unknown site.'.format(entry.title, target))
                    target_link = None
                else:
                    if target_link.site != self.site:
                        pywikibot.output(
                            u'NOTE: Ignoring {0} which is a redirect to '
                            u'another site {1}.'.format(entry.title, target_link.site))
                        target_link = None
                # if the redirect does not link to another wiki
                if target_link and target_link.title:
                    source = pywikibot.Link(entry.title, self.site)
                    if target_link.anchor:
                        pywikibot.output(
                            u'HINT: %s is a redirect with a pipelink.'
                            % entry.title)
                    redict[space_to_underscore(source)] = (
                        space_to_underscore(target_link))
        if alsoGetPageTitles:
            return redict, pageTitles
        else:
            return redict

    def get_redirect_pages_via_api(self):
        """Yield Pages that are redirects."""
        for ns in self.namespaces:
            done = False
            gen = self.site.allpages(start=self.api_start,
                                     namespace=ns,
                                     filterredir=True)
            if self.api_number:
                gen.set_maximum_items(self.api_number)
            if self.api_step:
                gen.set_query_increment(self.api_step)
            for p in gen:
                done = (self.api_until and
                        p.title(withNamespace=False) >= self.api_until)
                if done:
                    return
                yield p

    def _next_redirect_group(self):
        """Generator that yields batches of 500 redirects as a list."""
        apiQ = []
        for page in self.get_redirect_pages_via_api():
            apiQ.append(str(page._pageid))
            if len(apiQ) >= 500:
                yield apiQ
                apiQ = []
        if apiQ:
            yield apiQ

    def get_redirects_via_api(self, maxlen=8):
        """
        Return a generator that yields tuples of data about redirect Pages.

            0 - page title of a redirect page
            1 - type of redirect:
                         0 - broken redirect, target page title missing
                         1 - normal redirect, target page exists and is not a
                             redirect
                 2..maxlen - start of a redirect chain of that many redirects
                             (currently, the API seems not to return sufficient
                             data to make these return values possible, but
                             that may change)
                  maxlen+1 - start of an even longer chain, or a loop
                             (currently, the API seems not to return sufficient
                             data to allow this return values, but that may
                             change)
                      None - start of a redirect chain of unknown length, or
                             loop
            2 - target page title of the redirect, or chain (may not exist)
            3 - target page of the redirect, or end of chain, or page title
                where chain or loop detecton was halted, or None if unknown
        """
        for apiQ in self._next_redirect_group():
            gen = pywikibot.data.api.Request(action="query", redirects="",
                                             pageids=apiQ)
            data = gen.submit()
            if 'error' in data:
                raise RuntimeError("API query error: %s" % data)
            if data == [] or 'query' not in data:
                raise RuntimeError("No results given.")
            redirects = {}
            pages = {}
            redirects = dict((x['from'], x['to'])
                             for x in data['query']['redirects'])

            for pagetitle in data['query']['pages'].values():
                if 'missing' in pagetitle and 'pageid' not in pagetitle:
                    pages[pagetitle['title']] = False
                else:
                    pages[pagetitle['title']] = True
            for redirect in redirects:
                target = redirects[redirect]
                result = 0
                final = None
                try:
                    if pages[target]:
                        final = target
                        try:
                            while result <= maxlen:
                                result += 1
                                final = redirects[final]
                            # result = None
                        except KeyError:
                            pass
                except KeyError:
                    result = None
                    pass
                yield (redirect, result, target, final)

    def retrieve_broken_redirects(self):
        if self.use_api:
            count = 0
            for (pagetitle, type, target, final) \
                    in self.get_redirects_via_api(maxlen=2):
                if type == 0:
                    yield pagetitle
                    if self.api_number:
                        count += 1
                        if count >= self.api_number:
                            break
        elif self.xmlFilename:
            # retrieve information from XML dump
            pywikibot.output(
                u'Getting a list of all redirects and of all page titles...')
            redirs, pageTitles = self.get_redirects_from_dump(
                alsoGetPageTitles=True)
            for (key, value) in redirs.items():
                if value not in pageTitles:
                    yield key
        elif self.page_title:
            yield self.page_title
        else:
            # retrieve information from broken redirect special page
            pywikibot.output(u'Retrieving special page...')
            for redir_name in self.site.broken_redirects():
                yield redir_name.title()

    def retrieve_double_redirects(self):
        if self.use_move_log:
            gen = self.get_moved_pages_redirects()
            for redir_page in gen:
                yield redir_page.title()
        elif self.use_api:
            count = 0
            for (pagetitle, type, target, final) \
                    in self.get_redirects_via_api(maxlen=2):
                if type != 0 and type != 1:
                    yield pagetitle
                    if self.api_number:
                        count += 1
                        if count >= self.api_number:
                            break
        elif self.xmlFilename:
            redict = self.get_redirects_from_dump()
            num = 0
            for (key, value) in redict.items():
                num += 1
                # check if the value - that is, the redirect target - is a
                # redirect as well
                if num > self.offset and value in redict:
                    yield key
                    pywikibot.output(u'\nChecking redirect %i of %i...'
                                     % (num + 1, len(redict)))
        elif self.page_title:
            yield self.page_title
        else:
            # retrieve information from double redirect special page
            pywikibot.output(u'Retrieving special page...')
            for redir_name in self.site.double_redirects():
                yield redir_name.title()

    def get_moved_pages_redirects(self):
        """Generate redirects to recently-moved pages."""
        # this will run forever, until user interrupts it
        if self.offset <= 0:
            self.offset = 1
        start = (datetime.datetime.utcnow() -
                 datetime.timedelta(0, self.offset * 3600))
        # self.offset hours ago
        offset_time = start.strftime("%Y%m%d%H%M%S")
        pywikibot.output(u'Retrieving %s moved pages via API...'
                         % (str(self.api_number)
                            if self.api_number is not None else "all"))
        move_gen = self.site.logevents(logtype="move", start=offset_time)
        if self.api_number:
            move_gen.set_maximum_items(self.api_number)
        pywikibot.output('.', newline=False)
        for logentry in move_gen:
            moved_page = logentry.title()
            pywikibot.output('.', newline=False)
            try:
                if not moved_page.isRedirectPage():
                    continue
            except pywikibot.BadTitle:
                continue
            except pywikibot.ServerError:
                continue
            # moved_page is now a redirect, so any redirects pointing
            # to it need to be changed
            try:
                for page in moved_page.getReferences(follow_redirects=True,
                                                     redirectsOnly=True):
                    yield page
            except pywikibot.NoPage:
                # original title must have been deleted after move
                continue
            except pywikibot.CircularRedirect:
                continue
            except pywikibot.InterwikiRedirectPage:
                continue


class RedirectRobot(Bot):

    """Redirect bot."""

    def __init__(self, action, generator, **kwargs):
        self.availableOptions.update({
            'number': None,
            'delete': False,
        })
        super(RedirectRobot, self).__init__(**kwargs)
        self.site = pywikibot.Site()
        self.action = action
        self.generator = generator
        self.exiting = False
        self._valid_template = None

    def has_valid_template(self, twtitle):
        """
        Check whether a template from translatewiki.net exists on the wiki.

        We assume we are always working on self.site

        @param twtitle - a string which is the i18n key

        """
        if self._valid_template is None:
            self._valid_template = False
            if i18n.twhas_key(self.site, twtitle):
                template_msg = i18n.twtranslate(self.site, twtitle)
                template = re.findall(u'.*?{{(.*?)[|}]', template_msg)
                if template:
                    title = template[0]
                    page = pywikibot.Page(self.site, title, ns=10)
                    self._valid_template = page.exists()
        return self._valid_template

    def delete_broken_redirects(self):
        # get reason for deletion text
        for redir_name in self.generator.retrieve_broken_redirects():
            self.delete_1_broken_redirect(redir_name)

    def moved_page(self, source):
        gen = iter(self.site.logevents(logtype='move', page=source, total=1))
        try:
            lastmove = next(gen)
        except StopIteration:
            return None
        else:
            return lastmove.new_title()

    def delete_1_broken_redirect(self, redir_name):
        redir_page = pywikibot.Page(self.site, redir_name)
        # Show the title of the page we're working on.
        # Highlight the title in purple.
        pywikibot.output(u"\n\n>>> \03{lightpurple}%s\03{default} <<<"
                         % redir_page.title())
        try:
            targetPage = redir_page.getRedirectTarget()
        except pywikibot.IsNotRedirectPage:
            pywikibot.output(u'%s is not a redirect.' % redir_page.title())
        except pywikibot.NoPage:
            pywikibot.output(u'%s doesn\'t exist.' % redir_page.title())
        else:
            try:
                targetPage.get()
            except pywikibot.BadTitle as e:
                pywikibot.warning(
                    u'Redirect target %s is not a valid page title.'
                    % str(e)[10:])
                pass
            except pywikibot.InvalidTitle:
                pywikibot.exception()
                pass
            except pywikibot.NoPage:
                movedTarget = self.moved_page(targetPage)
                if movedTarget:
                    if not movedTarget.exists():
                        # FIXME: Test to another move
                        pywikibot.output(u'Target page %s does not exist'
                                         % (movedTarget))
                    elif redir_name == movedTarget.title():
                        pywikibot.output(u'Target page forms a redirect loop')
                    else:
                        pywikibot.output(u'%s has been moved to %s'
                                         % (redir_page, movedTarget))
                        reason = i18n.twtranslate(self.site,
                                                  'redirect-fix-broken-moved',
                                                  {'to': movedTarget.title(
                                                      asLink=True)})
                        content = redir_page.get(get_redirect=True)
                        redir_page.set_redirect_target(
                            movedTarget, keep_section=True)
                        pywikibot.showDiff(content, redir_page.text)
                        pywikibot.output(u'Summary - %s' % reason)
                        if self.user_confirm(
                                u'Redirect target %s has been moved to %s.\n'
                                u'Do you want to fix %s?'
                                % (targetPage, movedTarget, redir_page)):
                            try:
                                redir_page.save(reason)
                            except pywikibot.NoUsername:
                                pywikibot.output(u"Page [[%s]] not saved; "
                                                 u"sysop privileges required."
                                                 % redir_page.title())
                                pass
                            except pywikibot.LockedPage:
                                pywikibot.output(u'%s is locked.'
                                                 % redir_page.title())
                                pass
                elif self.getOption('delete') and self.user_confirm(
                        u'Redirect target %s does not exist.\n'
                        u'Do you want to delete %s?'
                        % (targetPage.title(asLink=True),
                           redir_page.title(asLink=True))):
                    reason = i18n.twtranslate(self.site,
                                              'redirect-remove-broken')
                    if self.site.logged_in(sysop=True):
                        redir_page.delete(reason, prompt=False)
                    else:
                        assert targetPage.site == self.site, (
                            u'target page is on different site %s'
                            % targetPage.site)
                        if self.has_valid_template(
                                'redirect-broken-redirect-template'):
                            pywikibot.output(u"No sysop in user-config.py, "
                                             u"put page to speedy deletion.")
                            content = redir_page.get(get_redirect=True)
                            # TODO: Add bot's signature if needed
                            #       Not supported via TW yet
                            content = i18n.twtranslate(
                                targetPage.site,
                                'redirect-broken-redirect-template'
                            ) + "\n" + content
                            try:
                                redir_page.put(content, reason)
                            except pywikibot.PageSaveRelatedError as e:
                                pywikibot.error(e)
                        else:
                            pywikibot.output(
                                u'No speedy deletion template available')
                else:
                    pywikibot.output(u'Cannot fix or delete the broken redirect')
            except pywikibot.IsRedirectPage:
                pywikibot.output(u"Redirect target %s is also a redirect! "
                                 u"Won't delete anything."
                                 % targetPage.title(asLink=True))
            else:
                # we successfully get the target page, meaning that
                # it exists and is not a redirect: no reason to touch it.
                pywikibot.output(
                    u'Redirect target %s does exist! Won\'t delete anything.'
                    % targetPage.title(asLink=True))

    def fix_double_redirects(self):
        for redir_name in self.generator.retrieve_double_redirects():
            self.fix_1_double_redirect(redir_name)

    def fix_1_double_redirect(self,  redir_name):
        redir = pywikibot.Page(self.site, redir_name)
        # Show the title of the page we're working on.
        # Highlight the title in purple.
        pywikibot.output(u"\n\n>>> \03{lightpurple}%s\03{default} <<<"
                         % redir.title())
        newRedir = redir
        redirList = []  # bookkeeping to detect loops
        while True:
            redirList.append(u'%s:%s' % (newRedir.site.lang,
                                         newRedir.title(withSection=False)))
            try:
                targetPage = newRedir.getRedirectTarget()
            except pywikibot.IsNotRedirectPage:
                if len(redirList) == 1:
                    pywikibot.output(u'Skipping: Page %s is not a redirect.'
                                     % redir.title(asLink=True))
                    break  # do nothing
                elif len(redirList) == 2:
                    pywikibot.output(
                        u'Skipping: Redirect target %s is not a redirect.'
                        % newRedir.title(asLink=True))
                    break  # do nothing
                else:
                    pass  # target found
            except pywikibot.SectionError:
                pywikibot.warning(
                    u"Redirect target section %s doesn't exist."
                    % newRedir.title(asLink=True))
            except (pywikibot.CircularRedirect,
                    pywikibot.InterwikiRedirectPage) as e:
                pywikibot.exception(e)
                pywikibot.output(u"Skipping %s." % newRedir)
                break
            except pywikibot.BadTitle as e:
                # str(e) is in the format 'BadTitle: [[Foo]]'
                pywikibot.warning(
                    u'Redirect target %s is not a valid page title.'
                    % str(e)[10:])
                break
            except pywikibot.NoPage:
                if len(redirList) == 1:
                    pywikibot.output(u'Skipping: Page %s does not exist.'
                                     % redir.title(asLink=True))
                    break
                else:
                    if self.getOption('always'):
                        pywikibot.output(
                            u"Skipping: Redirect target %s doesn't exist."
                            % newRedir.title(asLink=True))
                        break  # skip if automatic
                    else:
                        pywikibot.warning(
                            u"Redirect target %s doesn't exist."
                            % newRedir.title(asLink=True))
            except pywikibot.ServerError:
                pywikibot.output(u'Skipping due to server error: '
                                 u'No textarea found')
                break
            else:
                pywikibot.output(
                    u'   Links to: %s.'
                    % targetPage.title(asLink=True))
                try:
                    mw_msg = targetPage.site.mediawiki_message(
                        'wikieditor-toolbar-tool-redirect-example')
                except KeyError:
                    pass
                else:
                    if targetPage.title() == mw_msg:
                        pywikibot.output(
                            u"Skipping toolbar example: Redirect source is "
                            u"potentially vandalized.")
                        break
                # watch out for redirect loops
                if redirList.count(u'%s:%s'
                                   % (targetPage.site.lang,
                                      targetPage.title(withSection=False))):
                    pywikibot.warning(
                        u'Redirect target %s forms a redirect loop.'
                        % targetPage.title(asLink=True))
                    break  # FIXME: doesn't work. edits twice!
                    try:
                        content = targetPage.get(get_redirect=True)
                    except pywikibot.SectionError:
                        content_page = pywikibot.Page(
                            targetPage.site,
                            targetPage.title(withSection=False))
                        content = content_page.get(get_redirect=True)
                    if i18n.twhas_key(
                        targetPage.site.lang,
                        'redirect-broken-redirect-template') and \
                        i18n.twhas_key(targetPage.site.lang,
                                       'redirect-remove-loop'):
                        pywikibot.output(u"Tagging redirect for deletion")
                        # Delete the two redirects
                        content = i18n.twtranslate(
                            targetPage.site.lang,
                            'redirect-broken-redirect-template'
                        ) + "\n" + content
                        summ = i18n.twtranslate(targetPage.site.lang,
                                                'redirect-remove-loop')
                        targetPage.put(content, summ)
                        redir.put(content, summ)
                    break
                else:  # redirect target found
                    if targetPage.isStaticRedirect():
                        pywikibot.output(
                            u"   Redirect target is STATICREDIRECT.")
                        pass
                    else:
                        newRedir = targetPage
                        continue
            try:
                oldText = redir.get(get_redirect=True)
            except pywikibot.BadTitle:
                pywikibot.output(u"Bad Title Error")
                break
            redir.set_redirect_target(targetPage, keep_section=True)
            summary = i18n.twtranslate(self.site, 'redirect-fix-double',
                                       {'to': targetPage.title(asLink=True)}
                                       )
            pywikibot.showDiff(oldText, redir.text)
            if self.user_confirm(u'Do you want to accept the changes?'):
                try:
                    redir.save(summary)
                except pywikibot.LockedPage:
                    pywikibot.output(u'%s is locked.' % redir.title())
                except pywikibot.SpamfilterError as error:
                    pywikibot.output(
                        u"Saving page [[%s]] prevented by spam filter: %s"
                        % (redir.title(), error.url))
                except pywikibot.PageNotSaved as error:
                    pywikibot.output(u"Saving page [[%s]] failed: %s"
                                     % (redir.title(), error))
                except pywikibot.NoUsername:
                    pywikibot.output(
                        u"Page [[%s]] not saved; sysop privileges required."
                        % redir.title())
                except pywikibot.Error as error:
                    pywikibot.output(
                        u"Unexpected error occurred trying to save [[%s]]: %s"
                        % (redir.title(), error))
            break

    def fix_double_or_delete_broken_redirects(self):
        # TODO: part of this should be moved to generator, the rest merged into
        # self.run()
        count = 0
        for (redir_name, code, target, final)\
                in self.generator.get_redirects_via_api(maxlen=2):
            if code == 1:
                continue
            elif code == 0:
                self.delete_1_broken_redirect(redir_name)
                count += 1
            else:
                self.fix_1_double_redirect(redir_name)
                count += 1
            if self.getOption('number') and count >= self.getOption('number'):
                break

    def run(self):
        """Run the script method selected by 'action' parameter."""
        # TODO: make all generators return a redirect type indicator,
        #       thus make them usable with 'both'
        if self.action == 'double':
            self.fix_double_redirects()
        elif self.action == 'broken':
            self.delete_broken_redirects()
        elif self.action == 'both':
            self.fix_double_or_delete_broken_redirects()


def main(*args):
    """
    Process command line arguments and invoke bot.

    If args is an empty list, sys.argv is used.

    @param args: command line arguments
    @type args: list of unicode
    """
    options = {}
    # what the bot should do (either resolve double redirs, or delete broken
    # redirs)
    action = None
    # where the bot should get his infos from (either None to load the
    # maintenance special page from the live wiki, or the filename of a
    # local XML dump file)
    xmlFilename = None
    # Which namespace should be processed when using a XML dump
    # default to -1 which means all namespaces will be processed
    namespaces = []
    # at which redirect shall we start searching double redirects again
    # (only with dump); default to -1 which means all redirects are checked
    offset = -1
    moved_pages = False
    fullscan = False
    start = ''
    until = ''
    number = None
    step = None
    pagename = None

    for arg in pywikibot.handle_args(args):
        if arg == 'double' or arg == 'do':
            action = 'double'
        elif arg == 'broken' or arg == 'br':
            action = 'broken'
        elif arg == 'both':
            action = 'both'
        elif arg == '-fullscan':
            fullscan = True
        elif arg.startswith('-xml'):
            if len(arg) == 4:
                xmlFilename = i18n.input('pywikibot-enter-xml-filename')
            else:
                xmlFilename = arg[5:]
        elif arg.startswith('-moves'):
            moved_pages = True
        elif arg.startswith('-namespace:'):
            ns = arg[11:]
            if ns == '':
                # "-namespace:" does NOT yield -namespace:0 further down the road!
                ns = i18n.input('pywikibot-enter-namespace-number')
            # TODO: at least for some generators enter a namespace by its name
            # or number
            if ns == '':
                ns = '0'
            try:
                ns = int(ns)
            except ValueError:
                # -namespace:all Process all namespaces.
                # Only works with the API read interface.
                pass
            if ns not in namespaces:
                namespaces.append(ns)
        elif arg.startswith('-offset:'):
            offset = int(arg[8:])
        elif arg.startswith('-start:'):
            start = arg[7:]
        elif arg.startswith('-until:'):
            until = arg[7:]
        elif arg.startswith('-total:'):
            number = int(arg[7:])
        elif arg.startswith('-step:'):
            step = int(arg[6:])
        elif arg.startswith('-page:'):
            pagename = arg[6:]
        elif arg == '-always':
            options['always'] = True
        elif arg == '-delete':
            options['delete'] = True
        else:
            pywikibot.output(u'Unknown argument: %s' % arg)

    if (
        not action or
        xmlFilename and moved_pages or
        fullscan and xmlFilename
    ):
        pywikibot.showHelp()
    else:
        pywikibot.Site().login()
        gen = RedirectGenerator(xmlFilename, namespaces, offset, moved_pages,
                                fullscan, start, until, number, step, pagename)
        bot = RedirectRobot(action, gen, number=number, **options)
        bot.run()

if __name__ == '__main__':
    main()
