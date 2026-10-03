// MCP 2.2: the basket — several medicines at one place, one row per chain.

import { describe, expect, it, afterEach } from "vitest";
import { cleanup, fireEvent, screen, within } from "@testing-library/preact";
import { fixture, flush, mockBridge, renderWith } from "./helpers";
import { modelNote } from "../src/app";
import { interpret } from "../src/result";
import type { Envelope, ToolResultLike } from "../src/types";

afterEach(() => cleanup());

function reply(name: string): ToolResultLike {
  return fixture(name === "ui_basket" ? "basket" : "prices-exact");
}

describe("basket view", () => {
  it("lists the packages, then a row per chain with the sum and the dates of its prices", async () => {
    await renderWith(fixture("basket"));
    expect(screen.getByRole("heading").textContent).toBe("3 medicines");
    const items = screen.getByTestId("basket-items");
    expect(within(items).getByTestId("basket-item-1").textContent).toContain("#1 Atorvastatin Calcium · 30 × 10mg Tablet");
    const walmart = screen.getByTestId("basket-row-walmart");
    expect(walmart.textContent).toContain("Walmart (TX)");
    expect(walmart.querySelector(".amt")!.textContent).toBe("$27.22");
    expect(walmart.querySelector(".parts")!.textContent).toBe("#1 $14.22 · #2 $9.00 · #3 $4.00 · prices observed Sep 27 – Sep 30");
    expect(walmart.querySelector(".meta")!.textContent).toBe("1 mi");
    expect(screen.getByText("All at one chain, by the sum of card prices")).toBeTruthy();
  });

  it("a chain missing one medicine shows no sum and says which", async () => {
    await renderWith(fixture("basket"));
    const heb = screen.getByTestId("basket-row-heb");
    expect(heb.querySelector(".amt")!.textContent).toBe("—");
    expect(heb.querySelector(".parts")!.textContent).toBe("#1 $15.62 · #2 $4.00 · prices observed Sep 27 · no card price for #3");
  });

  it("gives the one-chain-per-medicine sum with its dates, the left-out count and the not-a-quote line", async () => {
    await renderWith(fixture("basket"));
    const split = screen.getByTestId("basket-split").textContent!;
    expect(split).toContain("One chain per medicine: $22.22 across 2 chains");
    expect(split).toContain("prices observed Sep 27");
    expect(split).toContain("#1 Walmart, #2 HEB, #3 Walmart");
    expect(screen.getByTestId("basket-unmatched").textContent).toBe("1 not found and left out");
    expect(screen.getByText(/It is not a quote/)).toBeTruthy();
    expect(screen.getByTestId("card-strip").textContent).toContain("MYCARD3993");
  });

  it("every dollar amount sits in a row that carries a date", async () => {
    await renderWith(fixture("basket"));
    for (const row of screen.getByTestId("basket-rows").querySelectorAll("li")) {
      if (/\$\d/.test(row.textContent || "")) expect(row.textContent).toMatch(/Sep \d+|Oct \d+/);
    }
  });

  it("without a place: asks for one, and a typed ZIP re-asks for the same packages", async () => {
    const { bridge } = await renderWith(fixture("basket-national"), mockBridge({ reply }));
    expect(screen.getByText(/Enter a ZIP code, a city or an address/)).toBeTruthy();
    fireEvent.input(screen.getByTestId("zip-input"), { target: { value: "77002" } });
    fireEvent.click(screen.getByTestId("zip-go"));
    await flush();
    expect(bridge.callTool).toHaveBeenCalledWith("ui_basket", {
      slugs: ["atorvastatin-calcium", "lisinopril"],
      strengths: ["10mg", "10mg"],
      forms: ["Tablet", "Tablet"],
      quantities: [30, 30],
      zip: "77002",
    });
    expect(screen.getByRole("heading").textContent).toBe("3 medicines");
  });

  it("a typed address goes out once as `where` and the model learns only the city", async () => {
    const { bridge } = await renderWith(fixture("basket-national"), mockBridge({ reply }));
    fireEvent.input(screen.getByTestId("zip-input"), { target: { value: "500 Main St, Houston" } });
    fireEvent.click(screen.getByTestId("zip-go"));
    await flush();
    const args = bridge.callTool.mock.calls[0][1];
    expect(args.where).toBe("500 Main St, Houston");
    expect(args.zip).toBeUndefined();
    const note = bridge.updateModelContext.mock.calls[0][0] as string;
    expect(note).toContain("Atorvastatin Calcium, Lisinopril, Metformin HCl together near Houston, TX");
    expect(note).not.toContain("Main St");
  });

  it("a medicine opens its own prices, and Back returns to the list", async () => {
    const { bridge } = await renderWith(fixture("basket"), mockBridge({ reply }));
    fireEvent.click(screen.getByTestId("basket-item-2"));
    await flush();
    expect(bridge.callTool).toHaveBeenCalledWith("ui_prices", {
      slug: "lisinopril",
      form: "Tablet",
      strength: "10mg",
      quantity: 30,
      zip: "77002",
    });
    expect(document.querySelector('[data-view="prices"]')).toBeTruthy();
    fireEvent.click(screen.getByTestId("back"));
    expect(document.querySelector('[data-view="basket"]')).toBeTruthy();
  });

  it("a medicine no chain prices is marked and the sums say they leave it out", async () => {
    const result = fixture("basket");
    const sc = result.structuredContent as any;
    sc.data.items[2].priced = false;
    await renderWith(result);
    expect(screen.getByTestId("basket-items").textContent).toContain("Metformin HCl · 30 × 10mg Tablet — no card price seen");
    expect(screen.getByTestId("basket-left-out").textContent).toBe("The sums leave out #3: no card price seen.");
  });

  it("a list with no usable item falls back to the text and the card", () => {
    const broken = fixture("basket");
    (broken.structuredContent as any).data.items = [];
    expect(interpret(broken).kind).toBe("fallback");
  });

  it("the model note names the medicines, not the widget's sums", () => {
    const env = fixture("basket").structuredContent as Envelope;
    expect(modelNote(env)).toMatch(/^Person is looking at Atorvastatin Calcium, Lisinopril, Metformin HCl together near Houston, TX/);
    expect(modelNote(env)).not.toMatch(/\$/);
  });
});

describe("prices view: an amount the person named", () => {
  function withAmount(amount: number): ToolResultLike {
    const result = fixture("prices-exact");
    const data = (result.structuredContent as any).data;
    const priced = data.rows.filter((r: any) => r.price);
    data.compareTo = {
      amount,
      below: priced.filter((r: any) => r.price.amount < amount).length,
      of: priced.length,
      observedFrom: "2026-09-20",
      observedTo: "2026-09-21",
    };
    return result;
  }

  it("says how many chains were seen below it, with the insurance sentence, and marks those rows", async () => {
    const result = withAmount(6);
    const data = (result.structuredContent as any).data;
    await renderWith(result);
    const box = screen.getByTestId("compare-to");
    expect(box.textContent).toContain(`Against $6.00: ${data.compareTo.below} of ${data.compareTo.of} chains were seen below it`);
    expect(box.textContent).toContain("it is not added to a copay");
    const marked = [...screen.getByTestId("price-rows").querySelectorAll("li")].filter((li) => /below \$6\.00/.test(li.textContent || ""));
    expect(marked.length).toBe(data.compareTo.below);
    expect(marked.length).toBeGreaterThan(0);
  });

  it("is absent without an amount", async () => {
    await renderWith(fixture("prices-exact"));
    expect(screen.queryByTestId("compare-to")).toBeNull();
    expect(screen.getByTestId("price-rows").textContent).not.toMatch(/below \$/);
  });

  it("a pick inside the card keeps the amount", async () => {
    const { bridge } = await renderWith(withAmount(6), mockBridge({ reply }));
    const chip = [...document.querySelectorAll("button.chip")].find((b) => b.getAttribute("aria-pressed") === "false") as HTMLButtonElement;
    fireEvent.click(chip);
    await flush();
    expect(bridge.callTool.mock.calls[0][0]).toBe("ui_prices");
    expect(bridge.callTool.mock.calls[0][1].compare_to).toBe(6);
  });
});

describe("packages view (get_drug)", () => {
  it("lists each strength with its pack sizes, the dated from-price and the chains", async () => {
    await renderWith(fixture("packages"));
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("Atorvastatin Calcium");
    const ten = screen.getByTestId("pkg-10mg-Tablet");
    const rows = ten.querySelectorAll("li");
    expect(rows[0].querySelector(".amt")!.textContent).toBe("$11.62");
    expect(rows[0].querySelector(".meta")!.textContent).toBe("observed Sep 20 · 16 chains");
    expect(ten.textContent).toContain("observed Sep 19 · 14 chains");
    expect(document.querySelector('[data-view="packages"]')!.textContent).not.toMatch(/per unit/);
  });

  it("a pack size nobody priced shows no amount", async () => {
    await renderWith(fixture("packages"));
    const row = screen.getByTestId("pkg-open-10mg-45").closest("li")!;
    expect(row.querySelector(".amt")!.textContent).toBe("—");
    expect(row.querySelector(".meta")!.textContent).toBe("no card price seen");
    expect(row.textContent).not.toMatch(/\$/);
  });

  it("marks the package most chains price", async () => {
    await renderWith(fixture("packages"));
    expect(screen.getByTestId("pkg-open-10mg-30").closest("li")!.className).toContain("on");
    expect(screen.getByTestId("pkg-open-10mg-90").closest("li")!.className).not.toContain("on");
  });

  it("every amount shown sits in a row with a date", async () => {
    await renderWith(fixture("packages"));
    for (const li of document.querySelectorAll('[data-view="packages"] li')) {
      if (/\$\d/.test(li.textContent || "")) expect(li.textContent).toMatch(/observed (Sep|Oct) \d+/);
    }
  });

  it("a tap opens that package's prices by chain, and Back returns", async () => {
    const { bridge } = await renderWith(fixture("packages"), mockBridge({ reply }));
    fireEvent.click(screen.getByTestId("pkg-open-10mg-90"));
    await flush();
    expect(bridge.callTool).toHaveBeenCalledWith("ui_prices", { slug: "atorvastatin-calcium", form: "Tablet", strength: "10mg", quantity: 90 });
    expect(document.querySelector('[data-view="prices"]')).toBeTruthy();
    fireEvent.click(screen.getByTestId("back"));
    expect(document.querySelector('[data-view="packages"]')).toBeTruthy();
  });

  it("says how many strengths are not listed", async () => {
    const result = fixture("packages");
    (result.structuredContent as any).data.moreCount = 3;
    await renderWith(result);
    expect(screen.getByTestId("more-strengths").textContent).toBe("+ 3 more strengths — name the one you take");
  });

  it("the second button opens the default package", async () => {
    const { bridge } = await renderWith(fixture("packages"), mockBridge({ reply }));
    fireEvent.click(screen.getByTestId("action-prices"));
    await flush();
    expect(bridge.callTool).toHaveBeenCalledWith("ui_prices", { slug: "atorvastatin-calcium", form: "Tablet", strength: "10mg", quantity: 30 });
  });
});

describe("equivalents view (several medicines from abroad)", () => {
  it("one block per medicine with the reviewed sentence verbatim", async () => {
    const result = fixture("equivalents");
    const items = (result.structuredContent as any).data.items;
    await renderWith(result);
    const first = screen.getByTestId("eq-1");
    expect(first.textContent).toContain("Nurofen");
    expect(first.textContent).toContain("RU, UA");
    expect(first.querySelector(".guidance")!.textContent).toBe(items[0].guidance);
    expect(screen.getByTestId("eq-2").querySelector(".guidance")!.textContent).toBe(items[1].guidance);
  });

  it("names a US product only for the same active ingredient", async () => {
    await renderWith(fixture("equivalents"));
    expect(screen.getByTestId("eq-1").textContent).toContain("in the US: Atorvastatin Calcium");
    expect(screen.getByTestId("eq-1").textContent).toMatch(/with card from \$[\d.]+ · (Sep|Oct) \d+/);
    const alt = screen.getByTestId("eq-2");
    expect(alt.textContent).toContain("not sold in the US as the same product");
    expect(alt.textContent).not.toMatch(/in the US:/);
    expect(alt.textContent).not.toMatch(/\$/);
    expect(document.body.textContent!.toLowerCase()).not.toContain("dicyclomine");
  });

  it("says the same-ingredient caveat and how many names were left out", async () => {
    await renderWith(fixture("equivalents"));
    expect(screen.getByTestId("same-inn-note").textContent).toMatch(/not the same product/);
    expect(screen.getByTestId("equivalents-unmatched").textContent).toBe("1 not in our reviewed list — left out");
  });

  it("a tap opens that brand, and Back returns to the list", async () => {
    const { bridge } = await renderWith(
      fixture("equivalents"),
      mockBridge({ reply: (name) => fixture(name === "ui_equivalent" ? "equivalent-same-inn" : "prices-exact") }),
    );
    fireEvent.click(screen.getByTestId("eq-open-2"));
    await flush();
    expect(bridge.callTool).toHaveBeenCalledWith("ui_equivalent", { brand_slug: "no-spa" });
    expect(document.querySelector('[data-view="equivalent"]')).toBeTruthy();
    fireEvent.click(screen.getByTestId("back"));
    expect(document.querySelector('[data-view="equivalents"]')).toBeTruthy();
  });

  it("Prices in the US prices only the same-ingredient medicine", async () => {
    const { bridge } = await renderWith(fixture("equivalents"), mockBridge({ reply }));
    fireEvent.click(screen.getByTestId("action-prices"));
    await flush();
    expect(bridge.callTool).toHaveBeenCalledWith("ui_prices", { slug: "atorvastatin-calcium" });
  });

  it("with nothing sold in the US there is no prices button", async () => {
    const result = fixture("equivalents");
    const data = (result.structuredContent as any).data;
    data.items = [data.items[1]];
    await renderWith(result);
    expect(screen.queryByTestId("action-prices")).toBeNull();
  });
});

describe("transfer view (moving a prescription)", () => {
  it("shows the chain, its dated card price, and the server's steps and notes verbatim", async () => {
    const result = fixture("transfer");
    const data = (result.structuredContent as any).data;
    await renderWith(result);
    expect(screen.getByRole("heading").textContent).toBe("Move a prescription to Publix");
    const price = screen.getByTestId("transfer-price").textContent!;
    expect(price).toContain("$30.15 with card");
    expect(price).toContain("observed Sep 20");
    const steps = [...screen.getByTestId("transfer-steps").querySelectorAll("li")].map((li) => li.textContent);
    expect(steps).toEqual(data.steps);
    expect(steps).toHaveLength(4);
    const notes = [...screen.getByTestId("transfer-notes").querySelectorAll("li")].map((li) => li.textContent);
    expect(notes).toEqual(data.notes);
  });

  it("lists the chain's nearest stores with directions through the host", async () => {
    const { bridge } = await renderWith(fixture("transfer"));
    const stores = screen.getByTestId("transfer-stores").querySelectorAll("li");
    expect(stores.length).toBeGreaterThan(0);
    expect(stores.length).toBeLessThanOrEqual(3);
    expect(stores[0].textContent).toContain("601 Northwest 2nd Avenue, Miami");
    fireEvent.click(screen.getAllByTestId("transfer-directions")[0]);
    expect(bridge.openLink.mock.calls[0][0]).toMatch(/^https:\/\/www\.google\.com\/maps\/dir\//);
  });

  it("the second button opens that package's prices", async () => {
    const { bridge } = await renderWith(fixture("transfer"), mockBridge({ reply }));
    fireEvent.click(screen.getByTestId("action-prices"));
    await flush();
    expect(bridge.callTool.mock.calls[0][0]).toBe("ui_prices");
    expect(bridge.callTool.mock.calls[0][1]).toMatchObject({ slug: "atorvastatin-calcium", zip: "33101" });
  });

  it("a restricted medicine shows only the note and the card", async () => {
    await renderWith(fixture("transfer-restricted"));
    expect(screen.getByTestId("transfer-restricted").textContent).toMatch(/only card prices and the free card/);
    expect(screen.queryByTestId("transfer-steps")).toBeNull();
    expect(screen.queryByTestId("transfer-stores")).toBeNull();
    expect(screen.getByTestId("card-strip").textContent).toContain("MYCARD3993");
  });

  it("without a chain or a medicine it is just the steps", async () => {
    const result = fixture("transfer");
    const data = (result.structuredContent as any).data;
    Object.assign(data, { chain: null, drug: null, price: null, stores: [] });
    await renderWith(result);
    expect(screen.getByRole("heading").textContent).toBe("Move a prescription to another pharmacy");
    expect(screen.queryByTestId("transfer-price")).toBeNull();
    expect(screen.getByTestId("transfer-steps").querySelectorAll("li")).toHaveLength(4);
  });
});

describe("card view: the card page as a QR", () => {
  it("draws the QR from the server's rows, dark on white, with the scan line", async () => {
    const result = fixture("card-qr");
    const rows: string[] = (result.structuredContent as any).data.qr.rows;
    await renderWith(result);
    const box = screen.getByTestId("card-qr");
    expect(box.textContent).toBe("At a computer? Scan to open the card on your phone.");
    const svg = box.querySelector("svg")!;
    expect(svg.querySelector("rect")!.getAttribute("fill")).toBe("#fff");
    const d = svg.querySelector("path")!.getAttribute("d")!;
    const dark = rows.join("").split("1").length - 1;
    expect(d.split("M").length - 1).toBe(dark);
    expect(svg.querySelector("path")!.getAttribute("fill")).toBe("#000");
    // Nothing is fetched to draw it.
    expect(box.querySelector("img, image")).toBeNull();
  });

  it("no rows, or rows that are not a square of 0/1, draw nothing", async () => {
    const { qrPath } = await import("../src/views/Card");
    expect(qrPath(null)).toBeNull();
    expect(qrPath(["101", "010"])).toBeNull();
    const n = 21;
    const ok = Array.from({ length: n }, () => "1".repeat(n));
    expect(qrPath(ok)!.size).toBe(n);
    expect(qrPath([...ok.slice(0, n - 1), "1".repeat(n - 1)])).toBeNull();
    expect(qrPath([...ok.slice(0, n - 1), "x".repeat(n)])).toBeNull();
    await renderWith(fixture("card"));
    expect(screen.queryByTestId("card-qr")).toBeNull();
  });
});
