import json

from django.conf import settings
from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.templatetags.static import static
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import cache_page
from django.views.decorators.http import require_GET

from .seo import ROBOTS_DISALLOW, SITEMAP_ROUTES, SOLUTION_PAGES, SOLUTION_PAGES_BY_SLUG


@require_GET
@cache_page(60 * 60)
def robots_txt(request):
    lines = ["User-agent: *", "Allow: /"]
    lines += [f"Disallow: {path}" for path in ROBOTS_DISALLOW]
    lines += ["", f"Sitemap: {settings.SEO_SITE_URL}{reverse('sitemap-xml')}", ""]
    return HttpResponse("\n".join(lines), content_type="text/plain; charset=utf-8")


@require_GET
@cache_page(60 * 60)
def sitemap_xml(request):
    lastmod = timezone.localdate().isoformat()
    entries = []
    for route, changefreq, priority in SITEMAP_ROUTES:
        entries.append(
            "  <url>"
            f"<loc>{settings.SEO_SITE_URL}{reverse(route)}</loc>"
            f"<lastmod>{lastmod}</lastmod>"
            f"<changefreq>{changefreq}</changefreq>"
            f"<priority>{priority}</priority>"
            "</url>"
        )
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(entries)
        + "\n</urlset>\n"
    )
    return HttpResponse(body, content_type="application/xml; charset=utf-8")


def _solution_structured_data(page, page_url, image_url):
    home_url = f"{settings.SEO_SITE_URL}{reverse('home')}"
    return [
        {
            "@context": "https://schema.org",
            "@type": "SoftwareApplication",
            "name": f"RegiManager {page['nav_label']}",
            "applicationCategory": "BusinessApplication",
            "operatingSystem": "Web, iOS, Android",
            "url": page_url,
            "image": image_url,
            "description": page["description"],
            "offers": {
                "@type": "AggregateOffer",
                "priceCurrency": "USD",
                "lowPrice": "79",
                "highPrice": "300",
                "offerCount": "4",
            },
            "publisher": {"@type": "Organization", "name": "RegiManager", "url": home_url},
        },
        {
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": [
                {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}}
                for q, a in page["faqs"]
            ],
        },
        {
            "@context": "https://schema.org",
            "@type": "BreadcrumbList",
            "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "RegiManager", "item": home_url},
                {"@type": "ListItem", "position": 2, "name": page["nav_label"], "item": page_url},
            ],
        },
    ]


def solution_page(request, slug):
    page = SOLUTION_PAGES_BY_SLUG.get(slug)
    if page is None:
        raise Http404
    page_url = f"{settings.SEO_SITE_URL}{request.path}"
    image_url = f"{settings.SEO_SITE_URL}{static(page['image'])}"
    return render(
        request,
        "core/solution_page.html",
        {
            "page": page,
            "seo_title": page["title"],
            "seo_description": page["description"],
            "related_pages": [p for p in SOLUTION_PAGES if p["slug"] != slug],
            "seo_image_url": image_url,
            "structured_data": json.dumps(_solution_structured_data(page, page_url, image_url)).replace("<", "\\u003c"),
        },
    )
