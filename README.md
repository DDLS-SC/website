# DDLS Student Council Website

🌐 **Website:** <https://ddls-sc.github.io/website/>

> **Status:** 🚧 Draft – the website is in planning and has not launched yet.

The official website of the **DDLS Student Council**, built by students for students. It will be the one place to find out about your courses, connect with the community, and get involved in our open-source projects.

## Goals

- **Inform** – give students clear, up-to-date information about courses.
- **Connect** – showcase the student community, events and ways to get involved.
- **Collaborate** – invite students to join our GitHub organisation and contribute.

## Planned Sections

| Section | What it will contain |
| --- | --- |
| **Home** | Welcome message, news and announcements |
| **Community** | Student council members, events, clubs, and how to get in touch |
| **Calendar** | Upcoming events, deadlines and student council meetings |
| **Join us** | Buttons to join the GitHub organisation and the WhatsApp group (links in `data/links.json`) |
| **About** | What the Student Council does and how to participate |
| **FAQs** | Common questions and answers (edit `data/faq.json`) |

## Roadmap

- [ ] Agree on site structure and content
- [ ] Design layout and visual identity
- [ ] Collect course information
- [ ] Write community and events pages
- [ ] Set up the GitHub organisation and onboarding guide
- [ ] Review with the student council
- [ ] Public launch 🚀

## Tech

A static site generated with Python and [Jinja2](https://jinja.palletsprojects.com/), hosted on **GitHub Pages**. Every push to `main` builds the site and deploys it with [.github/workflows/deploy-pages.yml](.github/workflows/deploy-pages.yml).

### Project layout

```text
site.json        Site title, tagline, status badge and the navigation menu
pages/           One template per page (index.html, calendar.html, ...)
templates/       base.html: shared header, navigation and footer
data/            JSON content: members, site contacts, links, FAQs, news
course/          Courses per term (e.g. 2026HT_courses.json), shown on the Calendar
event/           Events per term (e.g. 2026HT_events.json), shown on the Calendar
static/          CSS and other files copied as-is
build.py         Builds everything into dist/ (not committed)
```

### Run locally

```bash
conda env create -f environment.yml   # first time only
conda activate ddls-website
python build.py --serve               # http://localhost:8000
```

### Research, Collaborate and People pages

| Page | Data file | How students submit |
| --- | --- | --- |
| **Research** | `data/publications.json` | GitHub issue "Add a publication" (DOI, students, site, area) |
| **Collaborate** | `data/opportunities.json` | GitHub issue "Post an opportunity" |
| **People** | `student/<cohort>/<first.last>.json` | GitHub issue "Add or update your profile" |

The forms live in `.github/ISSUE_TEMPLATE/`. When an issue comes in, a maintainer copies it into the data file and closes the issue.

- **Publications:** run `python tools/add_publication.py <DOI> --students "Name; Name" --site Stockholm --area "Cell and molecular biology"`. It fetches title, authors, journal and date from Crossref and adds the entry. Research areas are listed in `site.json` → `research_areas`.
- **Opportunities** need `type` (`collaboration`, `skill-swap`, `position` or `hackathon`), `posted` and `expires` dates (YYYY-MM-DD). Expired posts are hidden automatically, both when the site is built and in the visitor's browser, so you can clean the file up whenever convenient.
- **People** reads every file in `student/<cohort year>/`. Use `"not available"` for missing links. `ra` is a research-area code from `site.json` → `research_area_codes` (CMB, EB, PMD, EBI); the site (Stockholm, Uppsala, …) comes from the university via `data/universities.json`. A new university must be added there, or the build prints a warning. Remove a student's file as soon as they ask.
- Entries with `"example": true` are placeholders shown with an *Example* label. Delete them before launch.
- Search and filters on these pages use `static/filter.js`; without JavaScript everything is simply listed.

### Common changes

- **Add a course, event, member or news item:** edit the matching file in `data/` (each is a JSON list; the page templates show the fields they use).
- **Add a page:** create `pages/<name>.html` that extends `base.html`, then add `{ "page": "<name>", "label": "..." }` to `nav` in `site.json`. The build stops with a clear error if the two get out of sync.
- **Change the look:** edit `static/style.css`; colours (SciLifeLab/DDLS palette) live in the variables at the top. The font is Schibsted Grotesk, self-hosted in `static/fonts/` (SIL Open Font License), so no visitor data goes to Google.
- **The site map** on the home and Community pages is drawn from `lat`/`lon` in `data/site_contacts.json`. A new site with coordinates appears on the map automatically; shared pieces like the map live in `templates/macros.html`.
- **Link previews:** `static/og-image.png` is the image shown when the site is shared; `site.json` → `url` must be the live address.

## Contributing

We welcome contributions from all DDLS students! Once the GitHub organisation is open, you will be able to:

1. Fork this repository and create a branch.
2. Make your changes (fix a typo, add course info, improve the design).
3. Open a pull request for the student council to review.

Have an idea but not sure where to start? Open an issue.

## Contact

Questions or suggestions? Reach the DDLS Student Council at *(contact details to be added)*.


## To dos 
[] Writing FAQs
[] Update calendar
[] Set up links 
[] Form for registration
[] Course data 
[] Invitation for the members 

