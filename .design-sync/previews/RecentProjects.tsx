import * as React from "react";
import { RecentProjects } from "figment-frontend";

// Fetches GET /api/projects on mount; the preview environment serves a mock
// list so the populated grid renders (empty state shows when there are none).
export const Default = () => <RecentProjects />;
