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
      customCss: [
        "@fontsource/inter/400.css",
        "@fontsource/inter/500.css",
        "@fontsource/inter/600.css",
        "@fontsource/inter/700.css",
        "@fontsource/noto-serif/400.css",
        "@fontsource/noto-serif/400-italic.css",
        "@fontsource/noto-serif/500.css",
        "@fontsource/noto-serif/600.css",
        "@fontsource/noto-serif/700.css",
        "./src/styles/custom.css",
      ],
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
              collapsed: false,
              autogenerate: { directory: "studies/sentry-pr-review-friction" },
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
