import * as React from "react";
import { Button, Spinner } from "figment-frontend";

export const Variants = () => (
  <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
    <Button variant="primary">Generate</Button>
    <Button variant="secondary">Enhance</Button>
    <Button variant="ghost">↶ Undo</Button>
    <Button variant="danger">Delete</Button>
  </div>
);

export const Sizes = () => (
  <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
    <Button variant="primary" size="sm">Small</Button>
    <Button variant="primary" size="md">Medium</Button>
    <Button variant="primary" size="lg">Large</Button>
  </div>
);

export const States = () => (
  <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
    <Button variant="primary">Enabled</Button>
    <Button variant="primary" disabled>Disabled</Button>
    <Button variant="secondary" disabled>Disabled</Button>
  </div>
);

export const Loading = () => (
  <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
    <Button variant="primary" disabled>
      <Spinner /> Starting…
    </Button>
    <Button variant="secondary" disabled>
      <Spinner /> Enhancing…
    </Button>
  </div>
);
