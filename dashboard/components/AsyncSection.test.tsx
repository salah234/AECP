import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AsyncSection } from "./AsyncSection";
import type { AsyncState } from "@/lib/useAsync";

describe("AsyncSection", () => {
  it("shows a loading indicator", () => {
    render(
      <AsyncSection state={{ status: "loading" } as AsyncState<number>}>
        {() => <div>data</div>}
      </AsyncSection>,
    );
    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });

  it("shows an honest not-available notice for a 501, not the children", () => {
    render(
      <AsyncSection
        state={{ status: "not_available", detail: "No RPC exists yet" } as AsyncState<number>}
      >
        {() => <div>should not render</div>}
      </AsyncSection>,
    );
    expect(screen.getByText(/not available yet/i)).toBeInTheDocument();
    expect(screen.getByText(/no rpc exists yet/i)).toBeInTheDocument();
    expect(screen.queryByText("should not render")).not.toBeInTheDocument();
  });

  it("shows an error message", () => {
    render(
      <AsyncSection state={{ status: "error", message: "boom" } as AsyncState<number>}>
        {() => <div>should not render</div>}
      </AsyncSection>,
    );
    expect(screen.getByText("boom")).toBeInTheDocument();
  });

  it("renders children with the resolved data on success", () => {
    render(
      <AsyncSection state={{ status: "success", data: 42 } as AsyncState<number>}>
        {(data) => <div>value: {data}</div>}
      </AsyncSection>,
    );
    expect(screen.getByText("value: 42")).toBeInTheDocument();
  });
});
