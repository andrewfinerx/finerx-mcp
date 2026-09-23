// Phase 2 (contract C3'): search, the pharmacies map, equivalent, rx, the
// "where" field, ui/update-model-context and widgetState.

import { describe, expect, it, afterEach } from "vitest";
import { cleanup, fireEvent, screen, within, act } from "@testing-library/preact";
import { fixture, flush, mockBridge, renderWith, type MockBridge } from "./helpers";
import { modelNote } from "../src/app";
import { parseWhere } from "../src/components/Controls";
import { centreOf, fitExtent, project } from "../src/components/StoreMap";
import type { Envelope, Store, ToolResultLike } from "../src/types";

afterEach(() => {
  cleanup();
  document.documentElement.removeAttribute("data-theme");
  document.documentElement.removeAttribute("data-display");
  document.documentElement.removeAttribute("style");
});

const SUGGEST_FINA: ToolResultLike = {
  structuredContent: {
    results: [
      { slug: "finasteride", name: "Finasteride", kind: "generic", matchedAlias: null, cardFrom: { amount: 7.9, observedAt: "2026-09-21" } },
    ],
    foreignBrands: [],
  },
};

/** ui_suggest → SUGGEST_FINA, ui_prices → prices-exact, ui_nearby → pharmacies,
 * ui_equivalent → equivalent-no-equivalent. */
function reply(name: string): ToolResultLike {
  if (name === "ui_suggest") return JSON.parse(JSON.stringify(SUGGEST_FINA));
  if (name === "ui_nearby") return fixture("pharmacies");
  if (name === "ui_equivalent") return fixture("equivalent-no-equivalent");
  return fixture("prices-exact");
}

async function fullscreen(bridge: MockBridge) {
  await act(() => bridge.push({ type: "host-context", context: { displayMode: "fullscreen" } }));
}

describe("search view", () => {
  it("asks for fullscreen, then shows the field, results with dated card prices and the foreign brand", async () => {
    const { bridge } = await renderWith(fixture("search"), mockBridge({ reply }));
    await flush();
    expect(bridge.requestDisplayMode).toHaveBeenCalledWith("fullscreen");
    const input = screen.getByTestId("search-input") as HTMLInputElement;
    expect(input.value).toBe("estr");
    const results = screen.getByTestId("search-results");
    expect(within(results).getByTestId("result-estradiol").textContent).toContain("with card from $4.20 · Sep 21");
    expect(within(results).getByTestId("result-estropipate").textContent).toContain("no card price seen");
    const foreign = within(results).getByTestId("foreign-estrofem");
    expect(foreign.textContent).toContain("foreign brand");
    expect(foreign.textContent).toContain("in the US: Estradiol");
    expect(screen.getByText(/Austin, TX/)).toBeTruthy();
    expect(bridge.callTool).not.toHaveBeenCalled(); // the server's own answer for "estr"
  });

  it("typing: debounced ui_suggest from 2 characters, nothing for 1", async () => {
    const { bridge } = await renderWith(fixture("search"), mockBridge({ reply }));
    await flush();
    const input = screen.getByTestId("search-input");
    fireEvent.input(input, { target: { value: "f" } });
    await flush(300);
    expect(bridge.callTool).not.toHaveBeenCalled();
    fireEvent.input(input, { target: { value: "fi" } });
    fireEvent.input(input, { target: { value: "fina" } });
    await flush(300);
    expect(bridge.callTool).toHaveBeenCalledTimes(1);
    expect(bridge.callTool).toHaveBeenCalledWith("ui_suggest", { q: "fina", locale: "en" });
    expect(screen.getByTestId("result-finasteride").textContent).toContain("$7.90");
    expect(screen.queryByTestId("result-estradiol")).toBeNull();
  });

  it("a pick → ui_prices in the same frame; model context; Back to search keeps the query", async () => {
    const { bridge } = await renderWith(fixture("search"), mockBridge({ reply }));
    await flush();
    fireEvent.input(screen.getByTestId("search-input"), { target: { value: "fina" } });
    await flush(300);
    fireEvent.click(screen.getByTestId("result-finasteride"));
    await flush();
    // approximate origin: the host's location travels with the call, not ours
    expect(bridge.callTool).toHaveBeenLastCalledWith("ui_prices", { slug: "finasteride" });
    expect(screen.getByTestId("price-rows")).toBeTruthy();
    expect(bridge.updateModelContext).toHaveBeenCalledWith(
      expect.stringContaining("Person selected 30 × 1 mg tablet of Estradiol near Austin, TX (approximate)"),
    );
    expect(bridge.setWidgetState).toHaveBeenCalledWith({ view: "prices", slug: "estradiol", form: "tablet", strength: "1 mg", quantity: 30 });
  });

  it("the where field: a ZIP goes as zip (and to the model), an address as where (never to the model)", async () => {
    const { bridge } = await renderWith(fixture("search"), mockBridge({ reply }));
    await flush();
    fireEvent.click(screen.getByRole("button", { name: "change location" }));
    fireEvent.input(screen.getByTestId("zip-input"), { target: { value: "78704" } });
    fireEvent.click(screen.getByTestId("zip-go"));
    expect(bridge.updateModelContext).toHaveBeenCalledWith("The person set the location to ZIP 78704 in the FineRx search.");
    fireEvent.click(screen.getByTestId("popular-atorvastatin"));
    await flush();
    expect(bridge.callTool).toHaveBeenLastCalledWith("ui_prices", { slug: "atorvastatin", zip: "78704" });
    expect(bridge.setWidgetState).toHaveBeenLastCalledWith(expect.objectContaining({ zip: "78704" }));
  });

  it("an address typed in where is sent once as `where` and kept out of widgetState and model context", async () => {
    const { bridge } = await renderWith(fixture("search"), mockBridge({ reply }));
    await flush();
    fireEvent.click(screen.getByRole("button", { name: "change location" }));
    fireEvent.input(screen.getByTestId("zip-input"), { target: { value: "1100 S Congress Ave, Austin" } });
    fireEvent.click(screen.getByTestId("zip-go"));
    fireEvent.click(screen.getByTestId("result-estradiol"));
    await flush();
    expect(bridge.callTool).toHaveBeenLastCalledWith("ui_prices", { slug: "estradiol", where: "1100 S Congress Ave, Austin" });
    const calls = bridge.setWidgetState.mock.calls;
    const state = calls[calls.length - 1][0];
    expect(state).not.toHaveProperty("zip");
    expect(JSON.stringify(state)).not.toContain("Congress");
    for (const [text] of bridge.updateModelContext.mock.calls) expect(text).not.toContain("Congress");
  });

  it("host refuses fullscreen: inline suggestions, no free-text field, a Search button", async () => {
    const bridge = mockBridge({ reply });
    bridge.requestDisplayMode.mockImplementation(async () => null);
    await renderWith(fixture("search"), bridge);
    await flush();
    expect(screen.queryByTestId("search-input")).toBeNull();
    expect(screen.getByTestId("search-results").querySelectorAll("li").length).toBeLessThanOrEqual(5);
    fireEvent.click(screen.getByTestId("open-search"));
    await flush();
    expect(bridge.requestDisplayMode).toHaveBeenCalledTimes(2);
    fireEvent.click(screen.getByTestId("popular-lisinopril"));
    await flush();
    expect(bridge.callTool).toHaveBeenCalledWith("ui_prices", { slug: "lisinopril" });
  });

  it("every foreign brand opens the equivalent view (ui_equivalent), never prices directly", async () => {
    const { bridge } = await renderWith(fixture("search-foreign"), mockBridge({ reply }));
    await flush();
    const noSpa = screen.getByTestId("foreign-no-spa");
    expect(noSpa.tagName).toBe("BUTTON"); // a different medicine: its guidance is the answer
    expect(noSpa.textContent).toContain("no US product listed");
    fireEvent.click(noSpa);
    await flush();
    expect(bridge.callTool).toHaveBeenCalledWith("ui_equivalent", { brand_slug: "no-spa", locale: "en" });
    expect(document.querySelector('[data-view="equivalent"]')).toBeTruthy();
    expect(screen.getByTestId("same-inn-note")).toBeTruthy();
    expect(bridge.updateModelContext).toHaveBeenCalled();
    fireEvent.click(screen.getByTestId("back"));
    await flush();
    fireEvent.click(screen.getByTestId("foreign-nurofen"));
    await flush();
    expect(bridge.callTool).toHaveBeenCalledWith("ui_equivalent", { brand_slug: "nurofen", locale: "en" });
    expect(bridge.callTool).not.toHaveBeenCalledWith("ui_prices", expect.anything());
  });

  it("the card strip follows ui_suggest: a restricted medicine among the results drops the adjectives", async () => {
    const plainLaw = "Use the free FineRx card — plain law for the test.";
    const restricted: ToolResultLike = {
      structuredContent: {
        results: [{ slug: "oxycodone-hcl", name: "Oxycodone HCl", kind: "generic", matchedAlias: null, cardFrom: null }],
        foreignBrands: [],
        card: { ...((fixture("search").structuredContent as any).card), law: plainLaw },
      },
    };
    const { bridge } = await renderWith(fixture("search"), mockBridge({ reply: (n: string) => (n === "ui_suggest" ? restricted : reply(n)) }));
    await flush();
    fireEvent.input(screen.getByTestId("search-input"), { target: { value: "oxy" } });
    await flush(300);
    expect(bridge.callTool).toHaveBeenCalledWith("ui_suggest", { q: "oxy", locale: "en" });
    expect(document.body.textContent).toContain(plainLaw);
    // back to the server's own query: its own card again
    fireEvent.input(screen.getByTestId("search-input"), { target: { value: "estr" } });
    await flush(300);
    expect(document.body.textContent).not.toContain(plainLaw);
  });

  it("nothing found is announced (role=status)", async () => {
    const empty: ToolResultLike = { structuredContent: { results: [], foreignBrands: [] } };
    const { bridge } = await renderWith(fixture("search"), mockBridge({ reply: (n: string) => (n === "ui_suggest" ? empty : reply(n)) }));
    await fullscreen(bridge);
    await flush();
    fireEvent.input(screen.getByTestId("search-input"), { target: { value: "zzzz" } });
    await flush(300);
    expect(screen.getByRole("status").textContent).toContain("Nothing found");
  });

  it("the where field says an address goes to the Census geocoder once — not for a ZIP", async () => {
    await renderWith(fixture("search"), mockBridge({ reply }));
    await flush();
    const change = screen.queryByRole("button", { name: /change/i });
    if (change) fireEvent.click(change);
    await flush();
    const field = screen.getByTestId("zip-input");
    fireEvent.input(field, { target: { value: "60614" } });
    expect(screen.queryByTestId("where-note")).toBeNull();
    fireEvent.input(field, { target: { value: "233 S Wacker Dr, Chicago" } });
    expect(screen.getByTestId("where-note").textContent).toContain("US Census geocoder");
  });

  it("show at the counter from fullscreen search: nothing to ask, nothing to undo", async () => {
    const { bridge } = await renderWith(fixture("search"), mockBridge({ reply }));
    await fullscreen(bridge);
    await flush();
    const before = bridge.requestDisplayMode.mock.calls.length;
    fireEvent.click(screen.getByRole("button", { name: "Show at the counter" }));
    await flush();
    fireEvent.click(within(screen.getByTestId("counter")).getByRole("button", { name: "Close" }));
    await flush();
    expect(bridge.requestDisplayMode.mock.calls.length).toBe(before);
    expect(screen.getByTestId("search-input")).toBeTruthy();
  });
});

describe("back to search", () => {
  it("returns to the search with what the person typed", async () => {
    const { bridge } = await renderWith(fixture("search"), mockBridge({ reply }));
    await flush();
    fireEvent.input(screen.getByTestId("search-input"), { target: { value: "fina" } });
    await flush(300);
    fireEvent.click(screen.getByTestId("result-finasteride"));
    await flush();
    const back = screen.getByTestId("back");
    expect(back.textContent).toContain("Back to search");
    fireEvent.click(back);
    await flush(300);
    expect((screen.getByTestId("search-input") as HTMLInputElement).value).toBe("fina");
    expect(screen.getByTestId("result-finasteride")).toBeTruthy();
    expect(screen.queryByTestId("back")).toBeNull();
    expect(bridge.callTool).toHaveBeenCalledTimes(2); // no second ui_suggest on the way back
  });
});

describe("prices: the where field takes an address", () => {
  it("address → ui_prices(where); the next chip carries the ZIP the address resolved to", async () => {
    const resolved = fixture("prices-exact");
    (resolved.structuredContent as any).data.origin = { zip: "78704", city: "Austin", state: "TX", precision: "address" };
    const bridge = mockBridge({ reply: () => JSON.parse(JSON.stringify(resolved)) });
    await renderWith(fixture("prices-exact"), bridge);
    // a phase-1 payload translates only "changeZip"; the field takes an address all the same
    fireEvent.click(screen.getByRole("button", { name: "change ZIP" }));
    fireEvent.input(screen.getByTestId("zip-input"), { target: { value: "1100 S Congress Ave, Austin, TX" } });
    fireEvent.click(screen.getByTestId("zip-go"));
    await flush();
    expect(bridge.callTool).toHaveBeenLastCalledWith("ui_prices", {
      slug: "estradiol",
      form: "tablet",
      strength: "1 mg",
      quantity: 30,
      where: "1100 S Congress Ave, Austin, TX",
    });
    expect(screen.getByText(/Near Austin, TX/).textContent).not.toContain("approximate");
    fireEvent.click(screen.getByRole("button", { name: "90 tablets" }));
    await flush();
    expect(bridge.callTool).toHaveBeenLastCalledWith("ui_prices", {
      slug: "estradiol",
      form: "tablet",
      strength: "1 mg",
      quantity: 90,
      zip: "78704",
    });
    // widgetState: a ZIP only when typed — never one derived from an address
    for (const [state] of bridge.setWidgetState.mock.calls) expect(state).not.toHaveProperty("zip");
    for (const [text] of bridge.updateModelContext.mock.calls) {
      expect(text).toContain("near Austin, TX");
      expect(text).not.toContain("Congress");
    }
  });

  it("a city name is an accepted place, digits that are not a ZIP are not", () => {
    expect(parseWhere(" 78704 ")).toEqual({ zip: "78704" });
    expect(parseWhere("78704-1234")).toEqual({ zip: "78704" });
    expect(parseWhere("Chicago,  IL")).toEqual({ where: "Chicago, IL" });
    expect(parseWhere("787")).toBeNull();
    expect(parseWhere("a")).toBeNull();
    expect(parseWhere("x".repeat(201))).toBeNull();
  });
});

describe("pharmacies: the map", () => {
  it("inline: the list plus On the map → fullscreen → the SVG scheme with rings and family dots", async () => {
    const { bridge } = await renderWith(fixture("pharmacies-map"), mockBridge({ reply }));
    expect(screen.getByTestId("store-rows")).toBeTruthy();
    expect(screen.queryByTestId("map")).toBeNull();
    fireEvent.click(screen.getByTestId("map-open"));
    await flush();
    expect(bridge.requestDisplayMode).toHaveBeenCalledWith("fullscreen");
    const map = screen.getByTestId("map");
    expect(map.querySelectorAll(".ring")).toHaveLength(2); // 5 and 10 mi: 80 % of the stores fit in 10
    const dots = screen.getAllByTestId("map-dot");
    expect(dots).toHaveLength(11); // the 12.4 mi CVS is past the 10 mi ring
    expect(screen.getByText("1 farther than 10 mi — in the list")).toBeTruthy();
    expect(dots.find((d) => d.getAttribute("data-family") === "costco")).toBeTruthy();
    expect(map.textContent).toContain("You ≈"); // centre fitted from the stores' distances
    // the list sits beside the map with every store (no "show more" in fullscreen)
    expect(screen.getByTestId("store-rows").querySelectorAll("li")).toHaveLength(12);
    fireEvent.click(screen.getByTestId("map-close"));
    await flush();
    expect(bridge.requestDisplayMode).toHaveBeenLastCalledWith("inline");
    expect(screen.queryByTestId("map")).toBeNull();
  });

  it("fullscreen host: the map at once; a dot opens the store card with price, date and directions", async () => {
    const bridge = mockBridge({ reply });
    await renderWith(fixture("pharmacies-map"), bridge);
    await fullscreen(bridge);
    const costco = screen.getAllByTestId("map-dot").find((d) => d.getAttribute("data-family") === "costco")!;
    fireEvent.click(costco);
    const card = screen.getByTestId("store-card");
    expect(card.textContent).toContain("Costco");
    expect(card.textContent).toContain("$4.20");
    expect(card.textContent).toMatch(/observed Sep 21/);
    expect(card.textContent).toContain("pharmacy in store (not verified)");
    fireEvent.click(within(card).getByTestId("store-directions"));
    expect(bridge.openLink).toHaveBeenCalledWith("https://www.google.com/maps/dir/?api=1&destination=30.3977%2C-97.7461");
    expect(bridge.callTool).not.toHaveBeenCalled();
    // leaving the map from a host-granted fullscreen does not ask for inline
    fireEvent.click(screen.getByTestId("map-close"));
    await flush();
    expect(bridge.requestDisplayMode).not.toHaveBeenCalled();
  });

  it("family filter and range are local; a list row selects its dot", async () => {
    const bridge = mockBridge({ reply });
    await renderWith(fixture("pharmacies-map"), bridge);
    await fullscreen(bridge);
    const families = screen.getByRole("group", { name: "Pharmacies nearby" });
    fireEvent.click(within(families).getByRole("button", { name: "Walgreens" }));
    expect(screen.getAllByTestId("map-dot").every((d) => d.getAttribute("data-family") === "walgreens")).toBe(true);
    fireEvent.click(within(families).getByRole("button", { name: "All" }));
    fireEvent.click(within(screen.getByRole("group", { name: "Range" })).getByRole("button", { name: "30 mi" }));
    expect(screen.getAllByTestId("map-dot")).toHaveLength(12);
    expect(screen.getByTestId("map").querySelectorAll(".ring")).toHaveLength(3);
    const rows = screen.getByTestId("store-rows");
    fireEvent.click(within(rows).getAllByRole("button", { name: /H-E-B/ })[0]);
    expect(screen.getByTestId("store-card").textContent).toContain("H-E-B");
    expect(bridge.callTool).not.toHaveBeenCalled();
  });

  it("where: an address goes to ui_nearby as `where` with the package", async () => {
    const { bridge } = await renderWith(fixture("pharmacies-map"), mockBridge({ reply }));
    fireEvent.click(screen.getByRole("button", { name: "change location" }));
    fireEvent.input(screen.getByTestId("zip-input"), { target: { value: "Round Rock, TX" } });
    fireEvent.click(screen.getByTestId("zip-go"));
    await flush();
    expect(bridge.callTool).toHaveBeenCalledWith("ui_nearby", {
      where: "Round Rock, TX",
      slug: "atorvastatin",
      form: "tablet",
      strength: "40 mg",
      quantity: 90,
    });
  });

  it("the card price without a store (Capsule) is listed with its date", async () => {
    await renderWith(fixture("pharmacies-map"));
    expect(screen.getByText(/Card price, no store nearby:/).textContent).toMatch(/Capsule \$9\.80 \(Sep 21\)/);
  });

  it("centreOf finds the person from the stores' distances; fitExtent keeps most stores", () => {
    const person = { lat: 30.25, lon: -97.75 };
    const at = (dLat: number, dLon: number): Store => {
      const lat = person.lat + dLat;
      const lon = person.lon + dLon;
      const [x, y] = project(person, lat, lon);
      return { family: "cvs", name: "CVS", lat, lon, miles: Math.round(Math.hypot(x, y) * 100) / 100 };
    };
    const stores = [at(0.01, 0.02), at(-0.03, 0.01), at(0.02, -0.04), at(-0.05, -0.05), at(0.07, 0.0)];
    const c = centreOf(null, stores)!;
    const [ex, ey] = project(person, c.lat, c.lon);
    expect(Math.hypot(ex, ey)).toBeLessThan(0.05);
    expect(centreOf({ lat: 41.88, lon: -87.63 }, stores)).toEqual({ lat: 41.88, lon: -87.63 });
    expect(fitExtent([0.4, 1, 2])).toBe(5);
    expect(fitExtent([0.4, 1, 2, 3, 4, 6, 7, 8, 9, 29])).toBe(10);
    expect(fitExtent([12, 14, 25])).toBe(30);
  });
});

describe("equivalent view", () => {
  it("same_inn: brand → INN → US product, guidance verbatim, the note, Prices in the US → ui_prices", async () => {
    const result = fixture("equivalent-same-inn");
    const data = (result.structuredContent as any).data;
    const { bridge } = await renderWith(result, mockBridge({ reply }));
    expect(screen.getByTestId("guidance").textContent).toBe(data.guidance);
    expect(screen.getByTestId("same-inn-note").textContent).toBe(data.disclaimer);
    const flow = document.querySelector(".flow")!;
    expect(flow.textContent).toContain("Active ingredient");
    expect(flow.textContent).not.toContain("INN");
    expect(flow.textContent).toContain("Concor");
    expect(flow.textContent).toContain("bisoprolol");
    expect(screen.getByTestId("flow-us").textContent).toContain("Bisoprolol Fumarate");
    expect(document.body.textContent).toContain("with card from $9.62 · Sep 21");
    fireEvent.click(screen.getByTestId("action-prices-us"));
    await flush();
    expect(bridge.callTool).toHaveBeenCalledWith("ui_prices", { slug: "bisoprolol-fumarate" });
    expect(screen.getByTestId("price-rows")).toBeTruthy();
    expect(screen.getByTestId("back").textContent).toContain("Back");
  });

  it("no_equivalent: names no US product and offers no prices — Save instead", async () => {
    await renderWith(fixture("equivalent-no-equivalent"));
    expect(screen.getByTestId("flow-us").textContent).toContain("no US equivalent");
    expect(screen.queryByTestId("action-prices-us")).toBeNull();
    expect(screen.getByTestId("save-toggle")).toBeTruthy();
    expect(screen.getByTestId("same-inn-note")).toBeTruthy();
  });
});

describe("rx view", () => {
  it("three sections, official links through the host, the dated card price, Prices with the card → ui_prices", async () => {
    const { bridge } = await renderWith(fixture("rx"), mockBridge({ reply }));
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("How to get a prescription: Sildenafil");
    expect(screen.getByTestId("rx-sections").querySelectorAll(".rx-sec")).toHaveLength(3);
    const links = screen.getAllByTestId("rx-link");
    expect(links).toHaveLength(3);
    fireEvent.click(links[0]);
    expect(bridge.openLink).toHaveBeenCalledWith("https://findahealthcenter.hrsa.gov/");
    expect(document.body.textContent).toContain("Without insurance: with card from $9.50 · Sep 21");
    fireEvent.click(screen.getByTestId("action-prices-card"));
    await flush();
    expect(bridge.callTool).toHaveBeenCalledWith("ui_prices", { slug: "sildenafil" });
  });

  it("restricted: one sentence, no sections, no links; Prices with the card stays", async () => {
    const { bridge } = await renderWith(fixture("rx-restricted"), mockBridge({ reply }));
    expect(screen.getByTestId("rx-restricted").textContent).toBe(
      "For this medicine FineRx shows only card prices and the free card. Discuss treatment with a licensed clinician.",
    );
    expect(screen.queryByTestId("rx-sections")).toBeNull();
    expect(screen.queryByTestId("rx-link")).toBeNull();
    // the law for a restricted medicine carries no savings adjective
    expect(screen.getByTestId("card-law").textContent).not.toMatch(/substantial/);
    fireEvent.click(screen.getByTestId("action-prices-card"));
    await flush();
    expect(bridge.callTool).toHaveBeenCalledWith("ui_prices", { slug: "adderall" });
  });

  it("a link that is not https never leaves the frame", async () => {
    const result = fixture("rx");
    (result.structuredContent as any).data.sections[1].links = [{ label: "bad", url: "javascript:alert(1)" }];
    await renderWith(result);
    expect(screen.getAllByTestId("rx-link")).toHaveLength(2);
  });
});

describe("model context", () => {
  it("names the package and the place (city/state or ZIP), never more", () => {
    const env = (fixture("prices-exact").structuredContent as unknown) as Envelope;
    expect(modelNote(env)).toBe(
      "Person selected 30 × 1 mg tablet of Estradiol near Austin, TX (approximate) in the FineRx card; it now shows card prices by pharmacy chain for that package.",
    );
    const ph = (fixture("pharmacies-map").structuredContent as unknown) as Envelope;
    expect(modelNote(ph)).toBe(
      "Person opened pharmacies for Atorvastatin (40 mg tablet · 90 tablets) near Austin, TX in the FineRx card.",
    );
  });
});
