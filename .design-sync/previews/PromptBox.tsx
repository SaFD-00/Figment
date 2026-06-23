import * as React from "react";
import { PromptBox } from "figment-frontend";

// The single home-page entry composer: prompt textarea, optional image
// attachments, an enhance/undo row, the LLM pill, and the Generate action.
export const Default = () => (
  <div style={{ maxWidth: 640 }}>
    <PromptBox />
  </div>
);
