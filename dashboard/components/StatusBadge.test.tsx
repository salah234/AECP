import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StatusBadge } from "./StatusBadge";

describe("StatusBadge", () => {
  it("renders the status with underscores replaced by spaces", () => {
    render(<StatusBadge value="in_progress" />);
    expect(screen.getByText("in progress")).toBeInTheDocument();
  });

  it("renders an unrecognized status without crashing", () => {
    render(<StatusBadge value="some_future_status" />);
    expect(screen.getByText("some future status")).toBeInTheDocument();
  });
});
