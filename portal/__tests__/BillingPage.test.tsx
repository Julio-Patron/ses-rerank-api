import React from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import BillingPage from "../app/billing/page";

describe("BillingPage", () => {
  it("renders the customer credit purchase page", () => {
    render(<BillingPage />);

    expect(screen.getByRole("heading", { name: "Buy credits" })).toBeDefined();
    expect(screen.getByText("Customer billing")).toBeDefined();
    expect(screen.queryByText("API Keys")).toBeNull();
  });
});
