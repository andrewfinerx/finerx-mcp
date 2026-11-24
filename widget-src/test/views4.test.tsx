// MCP 2.3 (#175 stage 2): a part of a package (30 g of a 50 g tube) is picked by
// what is billed — billing_quantity — never sent as 0.6 of a tube; a whole one
// keeps going out as a count.
import { describe, expect, it, afterEach } from "vitest";
import { cleanup, fireEvent, screen } from "@testing-library/preact";
import { fixture, flush, renderWith } from "./helpers";
import { packArgs } from "../src/result";

afterEach(() => cleanup());

const NOTE = "A pharmacy may dispense only the whole package (50 g each).";

function part() {
  const r = fixture("prices-part");
  const data = (r.structuredContent as any).data;
  data.package = {
    ...data.package,
    quantity: 0.6,
    label: "15% gel · 30 g · from a 50 g tube",
    billingQuantity: 30,
    labelNote: NOTE,
  };
  return r;
}

describe("packArgs", () => {
  it("a whole number of packages is a count; a part of one is its billed amount", () => {
    expect(packArgs({ quantity: 1, billingQuantity: 50 })).toEqual({ quantity: 1, billing_quantity: undefined });
    expect(packArgs({ quantity: 0.6, billingQuantity: 30 })).toEqual({ quantity: undefined, billing_quantity: 30 });
    expect(packArgs({ quantity: 0.6 })).toEqual({ quantity: undefined, billing_quantity: undefined });
    expect(packArgs(undefined)).toEqual({ quantity: undefined, billing_quantity: undefined });
  });
});

describe("prices: a part of a package", () => {
  it("the 30 g chip asks for 30 (billed), not for 0.6 of a tube", async () => {
    const { bridge } = await renderWith(fixture("prices-part"));
    expect(screen.queryByTestId("label-note")).toBeNull(); // a whole tube needs no note
    fireEvent.click(screen.getByRole("button", { name: "30 g · from a 50 g tube" }));
    await flush();
    expect(bridge.callTool).toHaveBeenCalledWith("ui_prices", {
      slug: "azelaic-acid",
      form: "gel",
      strength: "15%",
      billing_quantity: 30,
    });
  });

  it("shows the note under the label, and a whole tube goes out as a count again", async () => {
    const { bridge } = await renderWith(part());
    expect(screen.getByTestId("label-note").textContent).toBe(NOTE);
    fireEvent.click(screen.getByRole("button", { name: "1 tube · 50 g" }));
    await flush();
    expect(bridge.callTool).toHaveBeenLastCalledWith("ui_prices", {
      slug: "azelaic-acid",
      form: "gel",
      strength: "15%",
      quantity: 1,
    });
  });

  it("all pharmacies keeps the part of the package", async () => {
    const { bridge } = await renderWith(part());
    fireEvent.click(screen.getByRole("button", { name: "All pharmacies" }));
    await flush();
    expect(bridge.callTool).toHaveBeenCalledWith(
      "ui_nearby",
      expect.objectContaining({ slug: "azelaic-acid", billing_quantity: 30 }),
    );
    const calls = bridge.callTool.mock.calls;
    const args = calls[calls.length - 1][1];
    expect(args).not.toHaveProperty("quantity");
  });
});
