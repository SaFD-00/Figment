import * as React from "react";
import { ModelPillRow } from "figment-frontend";

// Image + LLM pills side by side — used in the composer toolbars.
export const Default = () => (
  <div style={{ display: "flex" }}>
    <ModelPillRow mode="txt2img" />
  </div>
);
