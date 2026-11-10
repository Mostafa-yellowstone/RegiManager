import json
import re

from django.test import TestCase, override_settings
from django.urls import reverse

from .seo import ROBOTS_DISALLOW, SOLUTION_PAGES
from .tests_insurance_area import InsuranceAreaBase

SITE = "https://www.regimanager.com"


@override_settings(SEO_SITE_URL=SITE)
class SeoPublicPagesTests(TestCase):
    def test_robots_txt_blocks_private_areas_and_points_to_sitemap(self):
        res = self.client.get("/robots.txt")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res["Content-Type"], "text/plain; charset=utf-8")
        body = res.content.decode()
        self.assertIn("Allow: /", body)
        for path in ROBOTS_DISALLOW:
            self.assertIn(f"Disallow: {path}", body)
        self.assertNotIn("Disallow: /auth/\n", body)
        self.assertIn(f"Sitemap: {SITE}/sitemap.xml", body)

    def test_sitemap_lists_home_and_every_solution_page(self):
        res = self.client.get("/sitemap.xml")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res["Content-Type"], "application/xml; charset=utf-8")
        body = res.content.decode()
        self.assertIn(f"<loc>{SITE}/</loc>", body)
        for page in SOLUTION_PAGES:
            self.assertIn(f"<loc>{SITE}/{page['slug']}/</loc>", body)
        self.assertIn(f"<loc>{SITE}{reverse('member-signup')}</loc>", body)
        self.assertNotIn("/dashboard/", body)

    def test_each_solution_page_has_unique_title_meta_and_structured_data(self):
        titles = set()
        for page in SOLUTION_PAGES:
            res = self.client.get(f"/{page['slug']}/")
            self.assertEqual(res.status_code, 200, page["slug"])
            html = res.content.decode()
            title = re.search(r"<title>(.*?)</title>", html, re.S).group(1).strip()
            titles.add(title)
            self.assertLessEqual(len(page["title"]), 65, page["slug"])
            self.assertLessEqual(len(page["description"]), 200, page["slug"])
            self.assertEqual(html.count("<h1"), 1, page["slug"])
            self.assertIn(f'<link rel="canonical" href="{SITE}/{page["slug"]}/">', html)
            self.assertIn('<meta name="robots" content="index, follow', html)
            self.assertIn('property="og:image" content="https://', html)
            blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
            types = set()
            for block in blocks:
                data = json.loads(block)
                for item in data if isinstance(data, list) else data.get("@graph", [data]):
                    types.add(item["@type"])
            self.assertTrue({"Organization", "SoftwareApplication", "FAQPage", "BreadcrumbList"} <= types, page["slug"])
        self.assertEqual(len(titles), len(SOLUTION_PAGES))

    def test_home_targets_dmv_first_and_links_every_solution_page(self):
        res = self.client.get(reverse("home"))
        self.assertContains(res, "<title>RegiManager | DMV Registration Software")
        self.assertContains(res, '<meta name="description" content="DMV registration software')
        self.assertContains(res, f'<link rel="canonical" href="{SITE}/">')
        for page in SOLUTION_PAGES:
            self.assertContains(res, f'href="/{page["slug"]}/"')
        nav = res.content.decode().split('aria-label="Primary"', 1)[1]
        self.assertLess(nav.index("dmv-registration-software"), nav.index("insurance-agency-software"))

    def test_existing_public_routes_still_resolve(self):
        for name in ("contact", "privacy", "login", "member-signup"):
            res = self.client.get(reverse(name))
            self.assertEqual(res.status_code, 200, name)
            self.assertContains(res, '<meta name="description"', msg_prefix=name)
            self.assertContains(res, "core/css/site-layout.css", msg_prefix=name)

    @override_settings(GOOGLE_SITE_VERIFICATION="g-token", BING_SITE_VERIFICATION="b-token")
    def test_search_console_verification_tags(self):
        res = self.client.get(reverse("home"))
        self.assertContains(res, '<meta name="google-site-verification" content="g-token">')
        self.assertContains(res, '<meta name="msvalidate.01" content="b-token">')

    def test_unknown_slug_is_not_a_solution_page(self):
        self.assertEqual(self.client.get("/not-a-real-solution/").status_code, 404)


@override_settings(SEO_SITE_URL=SITE)
class SeoPrivatePagesTests(InsuranceAreaBase):
    def test_portal_pages_are_noindex_without_share_tags(self):
        self.client.force_login(self.owner)
        res = self.client.get(reverse("insurance-home"))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, '<meta name="robots" content="noindex, nofollow">')
        self.assertNotContains(res, 'property="og:title"')
        self.assertNotContains(res, 'rel="canonical"')
        self.assertNotContains(res, "core/css/site-layout.css")

    def test_public_intake_is_noindex(self):
        res = self.client.get(reverse("public-intake-start"))
        self.assertContains(res, '<meta name="robots" content="noindex, nofollow">')
