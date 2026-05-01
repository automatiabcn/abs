import type { FC } from "react";

const Demo: FC = () => {
  const loomUrl =
    process.env.NEXT_PUBLIC_DEMO_LOOM_URL ?? "https://www.loom.com/embed/PLACEHOLDER";
  return (
    <section
      id="demo"
      aria-labelledby="demo-title"
      className="container mx-auto px-4 py-20"
    >
      <div className="mx-auto max-w-2xl text-center">
        <h2
          id="demo-title"
          className="text-3xl font-bold tracking-tight sm:text-4xl"
        >
          3 dakikada ABS turu
        </h2>
        <p className="mt-4 text-muted-foreground">
          Setup wizard, MCP tool çağrısı ve panel akışı tek videoda.
        </p>
      </div>

      <div className="mx-auto mt-12 max-w-4xl overflow-hidden rounded-lg border border-border bg-card">
        <div
          className="relative aspect-video w-full bg-muted"
          data-testid="demo-iframe-wrapper"
        >
          <iframe
            title="ABS demo screencast"
            src={loomUrl}
            loading="lazy"
            allow="fullscreen"
            allowFullScreen
            className="absolute inset-0 h-full w-full"
          />
        </div>
      </div>
    </section>
  );
};

export default Demo;
