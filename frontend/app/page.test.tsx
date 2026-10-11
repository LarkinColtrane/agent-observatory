import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import HomePage from "./page";

describe("HomePage", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders the product title as the only top-level heading", () => {
    render(<HomePage />);

    const headings = screen.getAllByRole("heading", { level: 1 });
    expect(headings).toHaveLength(1);
    expect(headings[0]).toHaveTextContent("Agent Observatory");
  });

  it("states that this is the engineering foundation without product features", () => {
    render(<HomePage />);

    expect(
      screen.getByText("Engineering foundation — no product features yet."),
    ).toBeVisible();
  });

  it("renders inside a main landmark with no interactive product UI", () => {
    render(<HomePage />);

    const main = screen.getByRole("main");
    expect(main).toBeInTheDocument();
    expect(screen.queryAllByRole("link")).toHaveLength(0);
    expect(screen.queryAllByRole("button")).toHaveLength(0);
    expect(screen.queryAllByRole("textbox")).toHaveLength(0);
  });

  it("makes no network calls while rendering", () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);

    render(<HomePage />);

    expect(fetchSpy).not.toHaveBeenCalled();
  });
});
