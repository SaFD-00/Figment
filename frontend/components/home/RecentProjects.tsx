"use client";

import { useEffect, useState } from "react";
import { listProjects } from "../../lib/api";
import type { Project } from "../../lib/types";
import { ProjectCard } from "./ProjectCard";

export function RecentProjects() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let alive = true;
    listProjects()
      .then((p) => {
        if (alive) setProjects(p);
      })
      .catch(() => {
        /* backend may be down; render empty state */
      })
      .finally(() => {
        if (alive) setLoaded(true);
      });
    return () => {
      alive = false;
    };
  }, []);

  if (!loaded) return null;
  if (projects.length === 0) {
    return (
      <p className="text-center text-sm text-muted">
        No projects yet. Generate your first image above.
      </p>
    );
  }

  return (
    <section>
      <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-muted">
        Recent projects
      </h2>
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5">
        {projects.map((p) => (
          <ProjectCard key={p.id} project={p} />
        ))}
      </div>
    </section>
  );
}
