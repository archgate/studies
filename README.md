# Archgate Studies

Reproducible studies on architecture governance, review friction, and ADR-driven standardization.

## Website

The studies website is published at:

- https://studies.archgate.dev

The site uses Astro + Starlight, so studies are written in Markdown/MDX instead of hand-crafted HTML.

### Local development

```bash
npm install
npm run dev
```

### Build

```bash
npm run build
```

Site source lives in `src/content/docs/` and deployment is handled by `.github/workflows/deploy-pages.yml`.

## Studies

- `studies/sentry-pr-review-friction/` - methodology code and generated data artifacts for the Sentry PR friction study.
- Published narrative: `src/content/docs/studies/sentry-pr-review-friction.mdx`

## Peer review workflow

Each study should include:

- methodology code
- generated raw metrics output
- assumptions and thresholds
- interpretation notes

Re-run scripts and open pull requests with alternative thresholds or additional validations to challenge findings.
