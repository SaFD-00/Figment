"use client";

import Link from "next/link";
import { assetFileUrl } from "../../lib/api";
import { relativeTime } from "../../lib/format";
import type { Project } from "../../lib/types";

export function ProjectCard({ project }: { project: Project }) {
  const cover = project.cover_asset ? assetFileUrl(project.cover_asset) : null;
  return (
    <Link
      href={`/editor/${project.id}`}
      className="group block overflow-hidden rounded-2xl border border-line bg-panel shadow-card transition-shadow hover:shadow-soft"
    >
      <div className="aspect-square w-full overflow-hidden bg-zinc-100">
        {cover ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={cover}
            alt={project.title}
            className="h-full w-full object-cover transition-transform duration-200 group-hover:scale-[1.02]"
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center text-muted">
            <span className="text-3xl">🖼️</span>
          </div>
        )}
      </div>
      <div className="p-3">
        <p className="truncate text-sm font-medium text-ink">
          {project.title || "Untitled"}
        </p>
        <p className="mt-0.5 text-xs text-muted">
          {relativeTime(project.updated_at || project.created_at)}
        </p>
      </div>
    </Link>
  );
}
