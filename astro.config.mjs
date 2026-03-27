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
      description: "Scientific-style studies about software governance and ADR enforcement.",
      favicon: "/favicon.svg",
      social: [
        {
          icon: "github",
          label: "GitHub",
          href: "https://github.com/archgate/studies",
        },
      ],
    }),
  ],
});
