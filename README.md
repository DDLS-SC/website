# DDLS Student Council Website

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
| **Courses** | Course overviews, schedules, prerequisites, tips and resources from other students |
| **Community** | Student council members, events, clubs, and how to get in touch |
| **Calendar** | Upcoming events, deadlines and student council meetings |
| **Join us on GitHub** | How to join the GitHub organisation, contribution guidelines, and open projects |
| **About** | What the Student Council does and how to participate |

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
pages/           One template per page (index.html, courses.html, ...)
templates/       base.html: shared header, navigation and footer
data/            JSON content: courses, events, members, news
static/          CSS and other files copied as-is
build.py         Builds everything into dist/ (not committed)
```

### Run locally

```bash
conda env create -f environment.yml   # first time only
conda activate ddls-website
python build.py --serve               # http://localhost:8000
```

### Common changes

- **Add a course, event, member or news item:** edit the matching file in `data/` (each is a JSON list; the page templates show the fields they use).
- **Add a page:** create `pages/<name>.html` that extends `base.html`, then add `{ "page": "<name>", "label": "..." }` to `nav` in `site.json`. The build stops with a clear error if the two get out of sync.
- **Change the look:** edit `static/style.css`; colours live in the variables at the top.

## Contributing

We welcome contributions from all DDLS students! Once the GitHub organisation is open, you will be able to:

1. Fork this repository and create a branch.
2. Make your changes (fix a typo, add course info, improve the design).
3. Open a pull request for the student council to review.

Have an idea but not sure where to start? Open an issue.

## Contact

Questions or suggestions? Reach the DDLS Student Council at *(contact details to be added)*.
