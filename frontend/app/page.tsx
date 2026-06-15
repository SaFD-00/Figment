import { PromptBox } from "../components/home/PromptBox";
import { RecentProjects } from "../components/home/RecentProjects";
import { FeatureGrid } from "../components/home/FeatureGrid";

export default function HomePage() {
  return (
    <main className="min-h-screen">
      {/* Header */}
      <header className="border-b border-line bg-panel/70 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <div className="flex items-center gap-2 text-lg font-extrabold tracking-tight text-ink">
            <span className="text-accent">✦</span> Figment
          </div>
          <nav className="hidden items-center gap-6 text-sm font-medium text-muted sm:flex">
            <a href="#generate" className="hover:text-ink">Generate</a>
            <a href="#features" className="hover:text-ink">Features</a>
            <a href="#recent" className="hover:text-ink">Projects</a>
          </nav>
        </div>
      </header>

      <div className="mx-auto flex max-w-5xl flex-col gap-20 px-6 py-16">
        <section id="generate" className="mx-auto w-full max-w-2xl text-center">
          <h1 className="text-4xl font-extrabold leading-tight tracking-tight text-ink sm:text-5xl">
            Figures &amp; images,
            <br />
            <span className="text-accent">made effortless.</span>
          </h1>
          <p className="mx-auto mt-4 max-w-xl text-base text-muted">
            Turn ideas into editable scientific figures and images. Generate from
            text, sketches, or references — then edit, vectorize, and export to
            PPTX, SVG, or PNG. Pick any cloud or local model.
          </p>
          <div className="mt-8">
            <PromptBox />
          </div>
        </section>

        <FeatureGrid />

        <div id="recent">
          <RecentProjects />
        </div>
      </div>
    </main>
  );
}
