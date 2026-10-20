from django.template.loader import render_to_string
from .models import SiteSettings, Page, ResearchDirection, Project, Member, Publication, Resource


def website_context(slug):
    site = SiteSettings.objects.get(pk=1)
    pages = list(Page.objects.all())
    current = next(page for page in pages if page.slug == slug)
    members = list(Member.objects.filter(is_published=True))
    resources = list(Resource.objects.filter(is_published=True))
    return {
        "site": site, "pages": pages, "page": current, "route": slug,
        "directions": list(ResearchDirection.objects.filter(is_published=True)),
        "projects": list(Project.objects.filter(is_published=True)),
        "publications": list(Publication.objects.filter(is_published=True)),
        "member_groups": [{"id": key, "title": title, "members": [m for m in members if m.group == key]}
                          for key, title in Member.GROUPS],
        "resources": resources,
        "resource_kinds": sorted({r.kind for r in resources}),
        "resource_diseases": sorted({r.disease for r in resources}),
        "leader_paragraphs": [p.strip() for p in site.leader_bio.split("\n\n") if p.strip()],
    }


def render_website(slug, context=None):
    return render_to_string(f"public/{slug}.html", context or website_context(slug))
