import starlight from "@astrojs/starlight";
import { defineConfig } from "astro/config";

export default defineConfig({
  site: "https://studies.archgate.dev",
  integrations: [
    starlight({
      title: "Archgate Studies",
      defaultLocale: "root",
      locales: {
        root: { label: "English", lang: "en" },
      },
      description:
        "Reproducible, peer-reviewable studies on software governance, review friction, and ADR enforcement.",
      favicon: "/favicon.svg",
      customCss: ["./src/styles/custom.css"],
      social: [
        {
          icon: "github",
          label: "GitHub",
          href: "https://github.com/archgate/studies",
        },
      ],
      sidebar: [
        {
          label: "About",
          items: [{ label: "Overview", slug: "" }],
        },
        {
          label: "Studies",
          items: [
            {
              label: "Sentry PR Review Friction",
              slug: "studies/sentry-pr-review-friction",
            },
          ],
        },
      ],
      head: [
        {
          tag: "meta",
          attrs: {
            name: "keywords",
            content:
              "software governance, ADR, architecture decision records, code review, pull request friction, empirical software engineering",
          },
        },
        {
          tag: "meta",
          attrs: {
            name: "author",
            content: "Archgate Research",
          },
        },
      ],
    }),
  ],
});
