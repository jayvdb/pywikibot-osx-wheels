# -*- coding: utf-8  -*-
"""API test module."""
#
# (C) Pywikibot team, 2007-2014
#
# Distributed under the terms of the MIT license.
#
from __future__ import unicode_literals

__version__ = '$Id$'

import datetime
import types

import pywikibot.data.api as api
import pywikibot.family
import pywikibot.site
from pywikibot.tools import MediaWikiVersion

from tests.aspects import (
    unittest,
    TestCase,
    DefaultSiteTestCase,
    DefaultDrySiteTestCase,
)
from tests.utils import allowed_failure


class TestApiFunctions(DefaultSiteTestCase):

    """API Request object test class."""

    def testObjectCreation(self):
        """Test api.Request() constructor with implicit site creation."""
        req = api.Request(action="test", foo="", bar="test")
        self.assertTrue(req)
        self.assertEqual(req.site, self.get_site())


class TestDryApiFunctions(DefaultDrySiteTestCase):

    """API Request object test class."""

    def testObjectCreation(self):
        """Test api.Request() constructor."""
        mysite = self.get_site()
        req = api.Request(site=mysite, action="test", foo="", bar="test")
        self.assertTrue(req)
        self.assertEqual(req.site, mysite)
        self.assertIn("foo", req._params)
        self.assertEqual(req["bar"], ["test"])
        # test item assignment
        req["one"] = "1"
        self.assertEqual(req._params['one'], ["1"])
        # test compliance with dict interface
        # req.keys() should contain "action", "foo", "bar", "one"
        self.assertEqual(len(req.keys()), 4)
        self.assertIn("test", req._encoded_items().values())
        for item in req.items():
            self.assertEqual(len(item), 2, item)


class TestParamInfo(DefaultSiteTestCase):

    """Test ParamInfo."""

    def test_init(self):
        site = self.get_site()
        pi = api.ParamInfo(site)
        self.assertEqual(len(pi), 0)
        pi._init()

        self.assertIn('main', pi._paraminfo)
        self.assertIn('paraminfo', pi._paraminfo)
        if MediaWikiVersion(self.site.version()) >= MediaWikiVersion("1.12"):
            self.assertEqual(len(pi),
                             len(pi.preloaded_modules))

        self.assertIn('info', pi._query_modules)
        self.assertIn('login', pi._action_modules)

    def test_init_pageset(self):
        site = self.get_site()
        self.assertNotIn('query', api.ParamInfo.init_modules)
        pi = api.ParamInfo(site, set(['pageset']))
        self.assertNotIn('query', api.ParamInfo.init_modules)
        self.assertEqual(len(pi), 0)
        pi._init()

        self.assertIn('main', pi._paraminfo)
        self.assertIn('paraminfo', pi._paraminfo)
        self.assertIn('pageset', pi._paraminfo)

        if MediaWikiVersion(self.site.version()) < MediaWikiVersion("1.12"):
            return

        if 'query' in pi.preloaded_modules:
            self.assertIn('query', pi._paraminfo)
            self.assertEqual(len(pi), 4)
        else:
            self.assertNotIn('query', pi._paraminfo)
            self.assertEqual(len(pi), 3)

        self.assertEqual(len(pi),
                         len(pi.preloaded_modules))

        if MediaWikiVersion(site.version()) >= MediaWikiVersion("1.21"):
            # 'generator' was added to 'pageset' in 1.21
            generators_param = pi.parameter('pageset', 'generator')
            self.assertGreater(len(generators_param['type']), 1)

    def test_generators(self):
        site = self.get_site()
        pi = api.ParamInfo(site, set(['pageset', 'query']))
        self.assertEqual(len(pi), 0)
        pi._init()

        self.assertIn('main', pi._paraminfo)
        self.assertIn('paraminfo', pi._paraminfo)
        self.assertIn('pageset', pi._paraminfo)
        self.assertIn('query', pi._paraminfo)

        if MediaWikiVersion(site.version()) >= MediaWikiVersion("1.21"):
            # 'generator' was added to 'pageset' in 1.21
            pageset_generators_param = pi.parameter('pageset', 'generator')
            query_generators_param = pi.parameter('query', 'generator')

            self.assertEqual(pageset_generators_param, query_generators_param)

    def test_with_module_info(self):
        site = self.get_site()
        pi = api.ParamInfo(site)
        self.assertEqual(len(pi), 0)
        pi.fetch(['info'])
        self.assertIn('query+info', pi._paraminfo)

        self.assertIn('main', pi._paraminfo)
        self.assertIn('paraminfo', pi._paraminfo)
        if MediaWikiVersion(self.site.version()) >= MediaWikiVersion("1.12"):
            self.assertEqual(len(pi),
                             1 + len(pi.preloaded_modules))

        self.assertEqual(pi['info']['prefix'], 'in')

        param = pi.parameter('info', 'prop')
        self.assertIsInstance(param, dict)

        self.assertEqual(param['name'], 'prop')
        self.assertNotIn('deprecated', param)

        self.assertIsInstance(param['type'], list)

        if MediaWikiVersion(self.site.version()) < MediaWikiVersion("1.12"):
            return

        self.assertIn('protection', param['type'])

    def test_with_module_revisions(self):
        site = self.get_site()
        pi = api.ParamInfo(site)
        self.assertEqual(len(pi), 0)
        pi.fetch(['revisions'])
        self.assertIn('query+revisions', pi._paraminfo)

        self.assertIn('main', pi._paraminfo)
        self.assertIn('paraminfo', pi._paraminfo)
        if MediaWikiVersion(self.site.version()) >= MediaWikiVersion("1.12"):
            self.assertEqual(len(pi),
                             1 + len(pi.preloaded_modules))

        self.assertEqual(pi['revisions']['prefix'], 'rv')

        param = pi.parameter('revisions', 'prop')
        self.assertIsInstance(param, dict)

        self.assertEqual(param['name'], 'prop')
        self.assertNotIn('deprecated', param)

        self.assertIsInstance(param['type'], list)

        if MediaWikiVersion(self.site.version()) < MediaWikiVersion("1.12"):
            return

        self.assertIn('user', param['type'])

    def test_multiple_modules(self):
        site = self.get_site()
        pi = api.ParamInfo(site)
        self.assertEqual(len(pi), 0)
        pi.fetch(['info', 'revisions'])
        self.assertIn('query+info', pi._paraminfo)
        self.assertIn('query+revisions', pi._paraminfo)

        self.assertIn('main', pi._paraminfo)
        self.assertIn('paraminfo', pi._paraminfo)

        if MediaWikiVersion(self.site.version()) < MediaWikiVersion("1.12"):
            return

        self.assertEqual(len(pi),
                         2 + len(pi.preloaded_modules))

    def test_with_invalid_module(self):
        site = self.get_site()
        pi = api.ParamInfo(site)
        self.assertEqual(len(pi), 0)
        pi.fetch('foobar')
        self.assertNotIn('foobar', pi._paraminfo)

        self.assertRaises(KeyError, pi.__getitem__, 'foobar')

        self.assertIn('main', pi._paraminfo)
        self.assertIn('paraminfo', pi._paraminfo)

        if MediaWikiVersion(self.site.version()) < MediaWikiVersion("1.12"):
            return

        self.assertEqual(len(pi),
                         len(pi.preloaded_modules))

    def test_query_modules_with_limits(self):
        site = self.get_site()
        pi = api.ParamInfo(site)
        self.assertIn('revisions', pi.query_modules_with_limits)
        self.assertNotIn('info', pi.query_modules_with_limits)

    def test_modules(self):
        """Test v1.8 modules exist."""
        site = self.get_site()
        pi = api.ParamInfo(site)
        self.assertIn('revisions', pi.modules)
        self.assertIn('help', pi.modules)
        self.assertIn('allpages', pi.modules)

    def test_prefixes(self):
        """Test v1.8 module prefixes exist."""
        site = self.get_site()
        pi = api.ParamInfo(site)
        self.assertIn('revisions', pi.prefixes)
        self.assertIn('login', pi.prefixes)
        self.assertIn('allpages', pi.prefixes)

    def test_old_mode(self):
        site = self.get_site()
        pi = api.ParamInfo(site, modules_only_mode=False)
        pi.fetch(['info'])
        self.assertIn('query+info', pi._paraminfo)

        self.assertIn('main', pi._paraminfo)
        self.assertIn('paraminfo', pi._paraminfo)

        if MediaWikiVersion(self.site.version()) >= MediaWikiVersion("1.12"):
            self.assertEqual(len(pi),
                             1 + len(pi.preloaded_modules))

        self.assertIn('revisions', pi.prefixes)

    def test_new_mode(self):
        site = self.get_site()
        if MediaWikiVersion(site.version()) < MediaWikiVersion('1.25wmf4'):
            raise unittest.SkipTest(
                "version %s doesn't support the new paraminfo api"
                % site.version())
        pi = api.ParamInfo(site, modules_only_mode=True)
        pi.fetch(['info'])
        self.assertIn('query+info', pi._paraminfo)

        self.assertIn('main', pi._paraminfo)
        self.assertIn('paraminfo', pi._paraminfo)

        self.assertEqual(len(pi),
                         1 + len(pi.preloaded_modules))

        self.assertIn('revisions', pi.prefixes)


class TestOptionSet(TestCase):

    """OptionSet class test class."""

    family = 'wikipedia'
    code = 'en'

    def test_non_lazy_load(self):
        """Test OptionSet with initialised site."""
        options = api.OptionSet(self.get_site(), 'recentchanges', 'show')
        self.assertRaises(KeyError, options.__setitem__, 'invalid_name', True)
        self.assertRaises(ValueError, options.__setitem__, 'anon', 'invalid_value')
        options['anon'] = True
        self.assertCountEqual(['anon'], options._enabled)
        self.assertEqual(set(), options._disabled)
        self.assertEqual(1, len(options))
        self.assertEqual(['anon'], list(options))
        self.assertEqual(['anon'], list(options.api_iter()))
        options['bot'] = False
        self.assertCountEqual(['anon'], options._enabled)
        self.assertCountEqual(['bot'], options._disabled)
        self.assertEqual(2, len(options))
        self.assertEqual(['anon', 'bot'], list(options))
        self.assertEqual(['anon', '!bot'], list(options.api_iter()))
        options.clear()
        self.assertEqual(set(), options._enabled)
        self.assertEqual(set(), options._disabled)
        self.assertEqual(0, len(options))
        self.assertEqual([], list(options))
        self.assertEqual([], list(options.api_iter()))

    def test_lazy_load(self):
        """Test OptionSet with delayed site initialisation."""
        options = api.OptionSet()
        options['invalid_name'] = True
        options['anon'] = True
        self.assertIn('invalid_name', options._enabled)
        self.assertEqual(2, len(options))
        self.assertRaises(KeyError, options._set_site, self.get_site(),
                          'recentchanges', 'show')
        self.assertEqual(2, len(options))
        options._set_site(self.get_site(), 'recentchanges', 'show', True)
        self.assertEqual(1, len(options))
        self.assertRaises(TypeError, options._set_site, self.get_site(),
                          'recentchanges', 'show')


class TestDryOptionSet(DefaultDrySiteTestCase):

    """OptionSet class test class."""

    def test_mutable_mapping(self):
        """Test keys, values and items from MutableMapping."""
        options = api.OptionSet()
        options['a'] = True
        options['b'] = False
        options['c'] = None
        self.assertCountEqual(['a', 'b'], list(options.keys()))
        self.assertCountEqual([True, False], list(options.values()))
        self.assertEqual(set(), set(options.values()) - set([True, False]))
        self.assertCountEqual([('a', True), ('b', False)], list(options.items()))


class TestDryPageGenerator(TestCase):

    """Dry API PageGenerator object test class."""

    family = 'wikipedia'
    code = 'en'

    dry = True

    # api.py sorts 'pages' using the string key, which is not a
    # numeric comparison.
    titles = ("Broadcaster (definition)", "Wiktionary", "Broadcaster.com",
              "Wikipedia:Disambiguation")

    def setUp(self):
        """Set up test case."""
        super(TestDryPageGenerator, self).setUp()
        mysite = self.get_site()
        self.gen = api.PageGenerator(site=mysite,
                                     generator="links",
                                     titles="User:R'n'B")
        # following test data is copied from an actual api.php response,
        # but that query no longer matches this dataset.
        # http://en.wikipedia.org/w/api.php?action=query&generator=links&titles=User:R%27n%27B
        self.gen.request.submit = types.MethodType(lambda self: {
            "query": {"pages": {"296589": {"pageid": 296589,
                                           "ns": 0,
                                           "title": "Broadcaster.com"
                                           },
                                "13918157": {"pageid": 13918157,
                                             "ns": 0,
                                             "title": "Broadcaster (definition)"
                                             },
                                "156658": {"pageid": 156658,
                                           "ns": 0,
                                           "title": "Wiktionary"
                                           },
                                "47757": {"pageid": 47757,
                                          "ns": 4,
                                          "title": "Wikipedia:Disambiguation"
                                          }
                                }
                      }
        }, self.gen.request)

        # On a dry site, the namespace objects only have canonical names.
        # Add custom_name for this site namespace, to match the live site.
        if 'Wikipedia' not in self.site.namespaces:
            self.site.namespaces[4].custom_name = 'Wikipedia'

    def test_results(self):
        """Test that PageGenerator yields pages with expected attributes."""
        self.assertPagelistTitles(self.gen, self.titles)

    def test_initial_limit(self):
        self.assertEqual(self.gen.limit, None)  # limit is initally None

    def test_set_limit_as_number(self):
        for i in range(-2, 4):
            self.gen.set_maximum_items(i)
            self.assertEqual(self.gen.limit, i)

    def test_set_limit_as_string(self):
        for i in range(-2, 4):
            self.gen.set_maximum_items(str(i))
            self.assertEqual(self.gen.limit, i)

    def test_set_limit_not_number(self):
        with self.assertRaisesRegex(
                ValueError,
                "invalid literal for int\(\) with base 10: 'test'"):
            self.gen.set_maximum_items('test')

    def test_limit_equal_total(self):
        """Test that PageGenerator yields the requested amount of pages."""
        self.gen.set_maximum_items(4)
        self.assertPagelistTitles(self.gen, self.titles)

    def test_limit_one(self):
        """Test that PageGenerator yields the requested amount of pages."""
        self.gen.set_maximum_items(1)
        self.assertPagelistTitles(self.gen, self.titles[0:1])

    def test_limit_zero(self):
        """Test that a limit of zero is the same as limit None."""
        self.gen.set_maximum_items(0)
        self.assertPagelistTitles(self.gen, self.titles)

    def test_limit_omit(self):
        """Test that limit omitted is the same as limit None."""
        self.gen.set_maximum_items(-1)
        self.assertPagelistTitles(self.gen, self.titles)

    def test_namespace(self):
        """Test PageGenerator set_namespace."""
        self.assertRaises(AssertionError, self.gen.set_namespace, 0)
        self.assertRaises(AssertionError, self.gen.set_namespace, 1)
        self.assertRaises(AssertionError, self.gen.set_namespace, None)


class TestPropertyGenerator(TestCase):

    """API PropertyGenerator object test class."""

    family = 'wikipedia'
    code = 'en'

    def test_info(self):
        """Test PropertyGenerator with prop 'info'."""
        mainpage = self.get_mainpage()
        links = list(self.site.pagelinks(mainpage, total=10))
        titles = [l.title(withSection=False)
                  for l in links]
        gen = api.PropertyGenerator(site=self.site,
                                    prop="info",
                                    titles='|'.join(titles))

        count = 0
        for pagedata in gen:
            self.assertIsInstance(pagedata, dict)
            self.assertIn('pageid', pagedata)
            self.assertIn('lastrevid', pagedata)
            count += 1
        self.assertEqual(len(links), count)

    def test_one_continuation(self):
        """Test PropertyGenerator with prop 'revisions'."""
        mainpage = self.get_mainpage()
        links = list(self.site.pagelinks(mainpage, total=10))
        titles = [l.title(withSection=False)
                  for l in links]
        gen = api.PropertyGenerator(site=self.site,
                                    prop="revisions",
                                    titles='|'.join(titles))
        gen.set_maximum_items(-1)  # suppress use of "rvlimit" parameter

        count = 0
        for pagedata in gen:
            self.assertIsInstance(pagedata, dict)
            self.assertIn('pageid', pagedata)
            self.assertIn('revisions', pagedata)
            self.assertIn('revid', pagedata['revisions'][0])
            count += 1
        self.assertEqual(len(links), count)

    def test_two_continuations(self):
        """Test PropertyGenerator with prop 'revisions' and 'coordinates'."""
        mainpage = self.get_mainpage()
        links = list(self.site.pagelinks(mainpage, total=10))
        titles = [l.title(withSection=False)
                  for l in links]
        gen = api.PropertyGenerator(site=self.site,
                                    prop="revisions|coordinates",
                                    titles='|'.join(titles))
        gen.set_maximum_items(-1)  # suppress use of "rvlimit" parameter

        count = 0
        for pagedata in gen:
            self.assertIsInstance(pagedata, dict)
            self.assertIn('pageid', pagedata)
            self.assertIn('revisions', pagedata)
            self.assertIn('revid', pagedata['revisions'][0])
            count += 1
        self.assertEqual(len(links), count)

    @allowed_failure
    def test_many_continuations_limited(self):
        """Test PropertyGenerator with many limited props."""
        mainpage = self.get_mainpage()
        links = list(self.site.pagelinks(mainpage, total=30))
        titles = [l.title(withSection=False)
                  for l in links]
        gen = api.PropertyGenerator(site=self.site,
                                    prop="revisions|info|categoryinfo|langlinks|templates",
                                    rvprop="ids|flags|timestamp|user|comment|content",
                                    titles='|'.join(titles))

        # An APIError is raised if set_maximum_items is not called.
        gen.set_maximum_items(-1)  # suppress use of "rvlimit" parameter
        # Force the generator into continuation mode
        gen.set_query_increment(5)

        count = 0
        for pagedata in gen:
            self.assertIsInstance(pagedata, dict)
            self.assertIn('pageid', pagedata)
            count += 1
        self.assertEqual(len(links), count)
        # FIXME: AssertionError: 30 != 6150

    @allowed_failure
    def test_two_continuations_limited(self):
        """Test PropertyGenerator with many limited props and continuations."""
        # FIXME: test fails
        mainpage = self.get_mainpage()
        links = list(self.site.pagelinks(mainpage, total=30))
        titles = [l.title(withSection=False)
                  for l in links]
        gen = api.PropertyGenerator(site=self.site,
                                    prop="info|categoryinfo|langlinks|templates",
                                    titles='|'.join(titles))
        # Force the generator into continuation mode
        gen.set_query_increment(5)

        count = 0
        for pagedata in gen:
            self.assertIsInstance(pagedata, dict)
            self.assertIn('pageid', pagedata)
            count += 1
        self.assertEqual(len(links), count)
        # FIXME: AssertionError: 30 != 11550

    # FIXME: test disabled as it takes longer than 10 minutes
    def _test_two_continuations_limited_long_test(self):
        """Long duration test, with total & step that are a real scenario."""
        mainpage = self.get_mainpage()
        links = list(mainpage.backlinks(total=300))
        titles = [l.title(withSection=False)
                  for l in links]
        gen = api.PropertyGenerator(site=self.site,
                                    prop="info|categoryinfo|langlinks|templates",
                                    titles='|'.join(titles))
        # Force the generator into continuation mode
        gen.set_query_increment(50)

        count = 0
        for pagedata in gen:
            self.assertIsInstance(pagedata, dict)
            self.assertIn('pageid', pagedata)
            count += 1
        self.assertEqual(len(links), count)


class TestDryListGenerator(TestCase):

    """Test ListGenerator."""

    family = 'wikipedia'
    code = 'en'

    dry = True

    def setUp(self):
        """Set up test case."""
        super(TestDryListGenerator, self).setUp()
        mysite = self.get_site()
        mysite._paraminfo['query+allpages'] = {
            'prefix': 'ap',
            'limit': {'max': 10},
            'namespace': {'multi': True}
        }
        mysite._paraminfo.query_modules_with_limits = set(['allpages'])
        self.gen = api.ListGenerator(listaction="allpages", site=mysite)

    def test_namespace_none(self):
        """Test ListGenerator set_namespace with None."""
        self.assertRaises(TypeError, self.gen.set_namespace, None)

    def test_namespace_zero(self):
        """Test ListGenerator set_namespace with 0."""
        self.gen.set_namespace(0)


class TestCachedRequest(DefaultSiteTestCase):

    """Test API Request caching.

    This test class does not use the forced test caching.
    """

    cached = False

    def test_normal_use(self):
        mysite = self.get_site()
        mainpage = self.get_mainpage()
        # Run the cached query three times to ensure the
        # data returned is equal, and the last two have
        # the same cache time.
        params = {'action': 'query',
                  'prop': 'info',
                  'titles': mainpage.title(),
                  }
        req1 = api.CachedRequest(datetime.timedelta(minutes=10),
                                 site=mysite, **params)
        data1 = req1.submit()
        req2 = api.CachedRequest(datetime.timedelta(minutes=10),
                                 site=mysite, **params)
        data2 = req2.submit()
        req3 = api.CachedRequest(datetime.timedelta(minutes=10),
                                 site=mysite, **params)
        data3 = req3.submit()
        self.assertEqual(data1, data2)
        self.assertEqual(data2, data3)
        self.assertIsNotNone(req2._cachetime)
        self.assertIsNotNone(req3._cachetime)
        self.assertEqual(req2._cachetime, req3._cachetime)

    def test_internals(self):
        mysite = self.get_site()
        # Run tests on a missing page unique to this test run so it can
        # not be cached the first request, but will be cached after.
        now = datetime.datetime.now()
        params = {'action': 'query',
                  'prop': 'info',
                  'titles': 'TestCachedRequest_test_internals ' + str(now),
                  }
        req = api.CachedRequest(datetime.timedelta(minutes=10),
                                site=mysite, **params)
        rv = req._load_cache()
        self.assertFalse(rv)
        self.assertIsNone(req._data)
        self.assertIsNone(req._cachetime)

        data = req.submit()

        self.assertIsNotNone(req._data)
        self.assertIsNone(req._cachetime)

        rv = req._load_cache()

        self.assertTrue(rv)
        self.assertIsNotNone(req._data)
        self.assertIsNotNone(req._cachetime)
        self.assertGreater(req._cachetime, now)
        self.assertEqual(req._data, data)


class TestLazyLogin(TestCase):

    """
    Test that it tries to login when read API access is denied.

    Because there is no such family configured it creates an AutoFamily and
    BaseSite on it's own. It's testing against steward.wikimedia.org.
    """

    net = True
    hostname = 'steward.wikimedia.org'

    def test_access_denied(self):
        """Test the query."""
        fam = pywikibot.family.AutoFamily(
            'steward', 'https://steward.wikimedia.org/w/api.php')
        site = pywikibot.site.APISite('steward', fam)
        req = api.Request(site=site, action='query')
        self.assertRaises(pywikibot.NoUsername, req.submit)


class TestBadTokenRecovery(TestCase):

    """Test that the request recovers from bad tokens."""

    family = 'wikipedia'
    code = 'test'

    write = True

    def test_bad_token(self):
        site = self.get_site()
        site.tokens._tokens.setdefault(site.user(), {})['edit'] = 'INVALID'
        page = pywikibot.Page(site, 'Pywikibot bad token test')
        page.text = ('This page is testing whether pywikibot-core rerequests '
                     'a token when a badtoken error was received.')
        page.save(comment='Bad token test')


if __name__ == '__main__':
    try:
        unittest.main()
    except SystemExit:
        pass
