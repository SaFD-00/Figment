import * as React from "react";
import { ProjectCard } from "figment-frontend";

const when = { created_at: "2026-06-20T09:12:00Z", updated_at: "2026-06-22T14:30:00Z" };

// No cover asset → the card shows its framed-image placeholder.
export const Default = () => (
  <div style={{ width: 220 }}>
    <ProjectCard project={{ id: "p-aurora", title: "Aurora reaction pathway", ...when }} />
  </div>
);

export const LongTitle = () => (
  <div style={{ width: 220 }}>
    <ProjectCard
      project={{ id: "p-etc", title: "Mitochondrial electron transport chain — full overview", ...when }}
    />
  </div>
);
