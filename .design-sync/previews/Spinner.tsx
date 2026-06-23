import * as React from "react";
import { Spinner, Button } from "figment-frontend";

// Spinner inherits its colour from `currentColor` and is 1rem by default.
export const Sizes = () => (
  <div style={{ display: "flex", gap: 16, alignItems: "center", color: "#3b82f6" }}>
    <Spinner />
    <Spinner className="h-6 w-6" />
    <Spinner className="h-8 w-8" />
  </div>
);

export const OnTones = () => (
  <div style={{ display: "flex", gap: 16, alignItems: "center" }}>
    <span style={{ color: "#0f1b35" }}><Spinner /></span>
    <span style={{ color: "#3b82f6" }}><Spinner /></span>
    <span style={{ color: "#7488a8" }}><Spinner /></span>
  </div>
);

export const InButton = () => (
  <Button variant="primary" disabled>
    <Spinner /> Generating…
  </Button>
);
