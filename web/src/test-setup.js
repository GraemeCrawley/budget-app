import "@testing-library/jest-dom/vitest";
import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

// Recharts leaves a hidden span on <body> that it measures text with; it holds the last tick label.
afterEach(() => {
  cleanup();
  document.getElementById("recharts_measurement_span")?.remove();
});
