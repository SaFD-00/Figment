import * as React from "react";
import { ModelPill } from "figment-frontend";

// Inline model selector bound to the unified models store (seeded in preview).
export const ImageModel = () => (
  <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
    <ModelPill kind="image" mode="txt2img" />
  </div>
);

export const LlmModel = () => (
  <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
    <ModelPill kind="llm" />
  </div>
);
