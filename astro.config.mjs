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
        "Reproducible, peer-reviewable studies on software governance and ADR enforcement.",
      favicon: "/favicon.svg",
      social: [
        {
          icon: "github",
          label: "GitHub",
          href: "https://github.com/archgate/studies",
        },
      ],
      customCss: ["./src/styles/custom.css"],
      sidebar: [
        {
          label: "Home",
          link: "/",
        },
        {
          label: "Published Studies",
          items: [
            {
              label: "All Studies",
              link: "/studies/",
            },
            {
              label: "Sentry PR Friction & ADR Standardization",
              link: "/studies/sentry-pr-review-friction/",
            },
          ],
        },
        {
          label: "Resources",
          items: [
            {
              label: "Source Repository",
              link: "https://github.com/archgate/studies",
              attrs: { target: "_blank" },
            },
          ],
        },
      ],
    }),
  ],
});
