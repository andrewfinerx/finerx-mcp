import { describe, expect, it, afterEach } from "vitest";
import { cleanup, fireEvent, screen, within, act } from "@testing-library/preact";
import { FIXTURE_NAMES, fixture, flush, mockBridge, renderWith } from "./helpers";
import { FALLBACK_LAW } from "../src/card";

afterEach(() => {
  cleanup();
  document.documentElement.removeAttribute("data-theme");
  document.documentElement.removeAttribute("style");
});

// The banned words of the card law (contract) — none may reach the screen.
const BANNED = /\b(always|guaranteed|save up to|best|cheapest|usually|works with insurance|most pharmacies|lowest)\b/i;

describe("every fixture renders its view with the card strip and the law", () => {
  for (const name of FIXTURE_NAMES) {
    it(name, async () => {
      const result = fixture(name);
      await renderWith(result);
      const strip = screen.getByTestId("card-strip");
      const law = within(strip).getByTestId("card-law");
      const sc = result.structuredContent as any;
      // The law is the payload's own sentence, verbatim — never ours.
      expect(law.textContent).toBe(sc.card.law);
      expect(within(strip).getByTestId("card-fine").textContent).toBe(sc.card.fine);
      // The card face with the codes is on screen in every view (the card view
      // draws the full face above the strip, the others a compact one inside it).
      expect(screen.getAllByTestId("card-codes")).toHaveLength(1);
      expect(screen.getByTestId("card-codes").textContent).toContain("MYCARD3993");
      expect(screen.getByTestId("card-face")).toBeTruthy();
      expect(document.body.textContent || "").not.toMatch(BANNED);
    });
  }
});

describe("prices view", () => {
  it("draws rows with price, date and miles, the zone, more-count and the location line", async () => {
    await renderWith(fixture("prices-exact"));
    const rows = screen.getByTestId("price-rows").querySelectorAll("li");
    expect(rows).toHaveLength(6);
    expect(rows[0].textContent).toContain("Costco");
    expect(rows[0].textContent).toContain("$4.20");
    expect(rows[0].textContent).toContain("1.2 mi");
    expect(rows[0].textContent).toMatch(/observed Sep 21/);
    expect(rows[1].textContent).toContain("(TX)");
    expect(screen.getByText("+ 3 more chains")).toBeTruthy();
    expect(screen.getByText(/Near Austin, TX \(approximate\)/)).toBeTruthy();
    expect(screen.getAllByRole("button", { name: "Show at the counter" })).toHaveLength(1);
    expect(screen.getByRole("button", { name: "All pharmacies" })).toBeTruthy();
  });

  it("a quantity chip calls ui_prices with the same package and the new quantity", async () => {
    const { bridge } = await renderWith(fixture("prices-exact"));
    fireEvent.click(screen.getByRole("button", { name: "90 tablets" }));
    await flush();
    expect(bridge.callTool).toHaveBeenCalledWith("ui_prices", {
      slug: "estradiol",
      form: "tablet",
      strength: "1 mg",
      quantity: 90,
    });
    // The model learns what was picked; ChatGPT keeps it in widgetState.
    expect(bridge.updateModelContext).toHaveBeenCalledTimes(1);
    expect(bridge.setWidgetState).toHaveBeenCalledWith(
      expect.objectContaining({ view: "prices", slug: "estradiol", quantity: 30 }),
    );
  });

  it("a dose chip keeps the quantity when the new dose sells it", async () => {
    const { bridge } = await renderWith(fixture("prices-exact"));
    fireEvent.click(screen.getByRole("button", { name: "2 mg tablet" }));
    await flush();
    expect(bridge.callTool).toHaveBeenCalledWith("ui_prices", {
      slug: "estradiol",
      form: "tablet",
      strength: "2 mg",
      quantity: 30,
    });
  });

  it("change ZIP → ui_prices with the typed ZIP; the ZIP is remembered for the next call", async () => {
    const { bridge } = await renderWith(fixture("prices-exact"));
    fireEvent.click(screen.getByRole("button", { name: "change ZIP" }));
    const input = screen.getByTestId("zip-input") as HTMLInputElement;
    fireEvent.input(input, { target: { value: "78704" } });
    fireEvent.click(screen.getByTestId("zip-go"));
    await flush();
    expect(bridge.callTool).toHaveBeenLastCalledWith("ui_prices", {
      slug: "estradiol",
      form: "tablet",
      strength: "1 mg",
      quantity: 30,
      zip: "78704",
    });
    fireEvent.click(screen.getByRole("button", { name: "All pharmacies" }));
    await flush();
    expect(bridge.callTool).toHaveBeenLastCalledWith("ui_nearby", {
      slug: "estradiol",
      form: "tablet",
      strength: "1 mg",
      quantity: 30,
      zip: "78704",
    });
  });

  it("a bad ZIP is not sent", async () => {
    const { bridge } = await renderWith(fixture("prices-exact"));
    fireEvent.click(screen.getByRole("button", { name: "change ZIP" }));
    fireEvent.input(screen.getByTestId("zip-input"), { target: { value: "787" } });
    fireEvent.click(screen.getByTestId("zip-go"));
    await flush();
    expect(bridge.callTool).not.toHaveBeenCalled();
    expect(screen.getByRole("alert").textContent).toContain("5-digit");
  });

  it("All pharmacies → ui_nearby with the package (no ZIP for an approximate origin) and draws the list", async () => {
    const { bridge } = await renderWith(fixture("prices-exact"));
    fireEvent.click(screen.getByRole("button", { name: "All pharmacies" }));
    await flush();
    expect(bridge.callTool).toHaveBeenCalledWith("ui_nearby", {
      slug: "estradiol",
      form: "tablet",
      strength: "1 mg",
      quantity: 30,
    });
    expect(screen.getByTestId("store-rows")).toBeTruthy();
    expect(screen.getByTestId("card-strip")).toBeTruthy();
  });

  it("other_quantities: says so, never rescales, offers the quantities we hold as buttons", async () => {
    const { bridge } = await renderWith(fixture("prices-other-quantities"));
    expect(screen.getByText(/haven't seen a card price for this package/)).toBeTruthy();
    expect(screen.queryByTestId("price-rows")).toBeNull(); // no rows of dashes
    const q90 = screen.getByTestId("other-q-90");
    expect(q90.textContent).toContain("$10.40");
    fireEvent.click(q90);
    await flush();
    // precision "zip": the ZIP came from the chat, so it travels with the call.
    expect(bridge.callTool).toHaveBeenCalledWith("ui_prices", {
      slug: "estradiol",
      form: "tablet",
      strength: "1 mg",
      quantity: 90,
      zip: "10001",
    });
  });

  it("needsZip: national prices by chain and the ZIP field in focus", async () => {
    const { bridge } = await renderWith(fixture("prices-needs-zip"));
    const input = screen.getByTestId("zip-input");
    expect(document.activeElement).toBe(input);
    expect(screen.getByTestId("price-rows").querySelectorAll("li")).toHaveLength(5);
    fireEvent.input(input, { target: { value: "33101" } });
    fireEvent.click(screen.getByTestId("zip-go"));
    await flush();
    expect(bridge.callTool).toHaveBeenCalledWith(
      "ui_prices",
      expect.objectContaining({ slug: "estradiol", zip: "33101" }),
    );
  });

  it("RTL: dir=rtl on the app, prices and codes pinned ltr, labels from the payload", async () => {
    await renderWith(fixture("prices-rtl-ar"));
    const app = screen.getByTestId("app");
    expect(app.getAttribute("dir")).toBe("rtl");
    expect(document.documentElement.dir).toBe("rtl");
    expect(screen.getByTestId("card-codes").getAttribute("dir")).toBe("ltr");
    const amt = screen.getByTestId("price-rows").querySelector(".amt")!;
    expect(amt.getAttribute("dir")).toBe("ltr");
    expect(amt.textContent).toMatch(/4\.20/); // Latin digits
    expect(screen.getByRole("button", { name: "أظهرها عند الصندوق" })).toBeTruthy();
    // A key the payload lacks falls back to English rather than a blank.
    expect(screen.getByTestId("card-codes").textContent).toContain("Group MYCARD3993");
  });

  it("a failed ui_prices keeps the prices on screen and says it did not load", async () => {
    const bridge = mockBridge({ reply: () => fixture("error") });
    await renderWith(fixture("prices-exact"), bridge);
    fireEvent.click(screen.getByRole("button", { name: "90 tablets" }));
    await flush();
    expect(screen.getByText("That didn't load. Try again.")).toBeTruthy();
    expect(screen.getByTestId("price-rows")).toBeTruthy();
  });
});

describe("pharmacies view", () => {
  it("lists stores with price+date, marks in-store pharmacies, filters by family locally", async () => {
    const { bridge } = await renderWith(fixture("pharmacies"));
    const list = screen.getByTestId("store-rows");
    expect(list.querySelectorAll("li")).toHaveLength(6); // + "show 1 more"
    expect(list.textContent).toContain("pharmacy in store (not verified)");
    expect(list.textContent).toMatch(/\$12\.40/);
    expect(list.textContent).toMatch(/observed Sep 20/);
    fireEvent.click(screen.getByRole("button", { name: "Walgreens" }));
    const filtered = screen.getByTestId("store-rows").querySelectorAll("li");
    expect(filtered).toHaveLength(2);
    expect(bridge.callTool).not.toHaveBeenCalled(); // local filter, no tool call
  });

  it("Directions opens the store's coordinates through the host", async () => {
    const { bridge } = await renderWith(fixture("pharmacies"));
    fireEvent.click(screen.getAllByTestId("directions")[0]);
    expect(bridge.openLink).toHaveBeenCalledWith(
      "https://www.google.com/maps/dir/?api=1&destination=30.25%2C-97.75",
    );
  });

  it("change ZIP → ui_nearby with the ZIP and the package", async () => {
    const { bridge } = await renderWith(fixture("pharmacies"));
    fireEvent.click(screen.getByRole("button", { name: "change ZIP" }));
    fireEvent.input(screen.getByTestId("zip-input"), { target: { value: "78745" } });
    fireEvent.click(screen.getByTestId("zip-go"));
    await flush();
    expect(bridge.callTool).toHaveBeenCalledWith("ui_nearby", {
      zip: "78745",
      slug: "estradiol",
      form: "tablet",
      strength: "1 mg",
      quantity: 30,
    });
  });
});

describe("card view and the Save menu", () => {
  it("shows the price with its date and two buttons", async () => {
    await renderWith(fixture("card"));
    expect(screen.getByText("$4.20")).toBeTruthy();
    expect(document.body.textContent).toMatch(/observed Sep 21/);
    const actions = screen.getByTestId("card-strip").querySelector(".actions")!;
    expect(actions.querySelectorAll("button")).toHaveLength(2);
  });

  it("email: nothing is sent without consent; with it, email_savings_card gets the address once", async () => {
    const bridge = mockBridge({ reply: () => ({ structuredContent: { sent: true } }) });
    await renderWith(fixture("card"), bridge);
    fireEvent.click(screen.getByTestId("save-toggle"));
    fireEvent.click(screen.getByTestId("save-email"));
    const input = screen.getByTestId("email-input") as HTMLInputElement;
    input.value = "person@example.com";
    fireEvent.click(screen.getByTestId("email-send"));
    await flush();
    expect(bridge.callTool).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId("email-consent"));
    fireEvent.click(screen.getByTestId("email-send"));
    await flush();
    expect(bridge.callTool).toHaveBeenCalledWith("email_savings_card", {
      email: "person@example.com",
      consent: true,
      locale: "en",
    });
    expect(screen.getByRole("status").textContent).toContain("Sent");
    expect(document.body.textContent).not.toContain("person@example.com");
  });

  it("print and Wallet open the printable card; SMS opens an sms: link with the body", async () => {
    const { bridge } = await renderWith(fixture("card"));
    fireEvent.click(screen.getByTestId("save-toggle"));
    fireEvent.click(screen.getByTestId("save-print"));
    fireEvent.click(screen.getByTestId("save-wallet"));
    const printUrl = (fixture("card").structuredContent as any).card.printUrl;
    expect(bridge.openLink).toHaveBeenNthCalledWith(1, printUrl);
    expect(bridge.openLink).toHaveBeenNthCalledWith(2, printUrl);
    fireEvent.click(screen.getByTestId("save-sms"));
    const body = (fixture("card").structuredContent as any).card.actions.smsBody;
    expect(bridge.openLink).toHaveBeenLastCalledWith(`sms:?&body=${encodeURIComponent(body)}`);
  });

  it("copy puts the three codes on the clipboard", async () => {
    let copied = "";
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: async (s: string) => void (copied = s) },
    });
    await renderWith(fixture("card"));
    fireEvent.click(screen.getByRole("button", { name: "Copy" }));
    await flush();
    expect(copied).toBe("BIN 610219 · PCN DRX · Group MYCARD3993");
    expect(screen.getByRole("button", { name: "Copied" })).toBeTruthy();
  });
});

describe("show at the counter", () => {
  it("asks the host for fullscreen and shows large codes + Not insurance; close goes back inline", async () => {
    const { bridge } = await renderWith(fixture("prices-exact"));
    fireEvent.click(screen.getByRole("button", { name: "Show at the counter" }));
    await flush();
    expect(bridge.requestDisplayMode).toHaveBeenCalledWith("fullscreen");
    const counter = screen.getByTestId("counter");
    expect(counter.textContent).toContain("610219");
    expect(counter.textContent).toContain("MYCARD3993");
    expect(counter.textContent).toContain("Not insurance");
    fireEvent.click(within(counter).getByRole("button", { name: "Close" }));
    await flush();
    expect(bridge.requestDisplayMode).toHaveBeenLastCalledWith("inline");
    expect(screen.queryByTestId("counter")).toBeNull();
  });

  it("works without fullscreen (the host refuses): the overlay still shows", async () => {
    const bridge = mockBridge();
    bridge.requestDisplayMode.mockImplementation(async () => null);
    await renderWith(fixture("card"), bridge);
    fireEvent.click(screen.getByRole("button", { name: "Show at the counter" }));
    await flush();
    expect(screen.getByTestId("counter")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    await flush();
    expect(bridge.requestDisplayMode).toHaveBeenCalledTimes(1); // nothing to undo
  });
});

describe("states", () => {
  it("error: says prices did not load, the card still works", async () => {
    await renderWith(fixture("error"));
    expect(screen.getByRole("alert").textContent).toBe("Prices didn't load. The card still works.");
    expect(screen.getByTestId("card-strip")).toBeTruthy();
  });

  it("no data at all: the bundled codes and the approved English law", async () => {
    await renderWith({ isError: true, content: [] });
    expect(screen.getByTestId("card-codes").textContent).toContain("610219");
    expect(screen.getByTestId("card-law").textContent).toBe(FALLBACK_LAW);
  });

  it("before any result: the codes are on screen already", async () => {
    await renderWith(null);
    expect(screen.getByTestId("card-codes").textContent).toContain("MYCARD3993");
  });

  it("tool-input shows a skeleton with the drug name, then the result replaces it", async () => {
    const { bridge } = await renderWith(null);
    await act(() => bridge.push({ type: "tool-input", args: { drug: "estradiol", strength: "1 mg" } }));
    expect(screen.getByText("estradiol 1 mg")).toBeTruthy();
    expect(screen.getByRole("status").textContent).toBe("Loading prices…");
    expect(screen.getByTestId("card-strip")).toBeTruthy();
    await act(() => bridge.push({ type: "tool-result", result: fixture("prices-exact") }));
    expect(screen.getByTestId("price-rows")).toBeTruthy();
  });

  it("an unknown view falls back to the model text + the card", async () => {
    const result = fixture("card");
    (result.structuredContent as any).view = "equivalent";
    await renderWith(result);
    expect(screen.getByText(/BIN 610219 · PCN DRX/)).toBeTruthy();
    expect(screen.getByTestId("card-strip")).toBeTruthy();
  });

  it("host theme and style variables land on :root (without url())", async () => {
    const { bridge } = await renderWith(fixture("card"));
    await act(() =>
      bridge.push({
        type: "host-context",
        context: {
          theme: "dark",
          styles: { variables: { "--color-background-primary": "#1a1a1a", "--font-sans": "url(x)" } },
        },
      }),
    );
    const root = document.documentElement;
    expect(root.getAttribute("data-theme")).toBe("dark");
    expect(root.style.getPropertyValue("--color-background-primary")).toBe("#1a1a1a");
    expect(root.style.getPropertyValue("--font-sans")).toBe("");
  });

  it("ChatGPT re-mount: widgetState brings back the package the person had picked", async () => {
    const bridge = mockBridge({ widgetState: { view: "prices", slug: "estradiol", form: "tablet", strength: "1 mg", quantity: 90 } });
    await renderWith(fixture("prices-exact"), bridge);
    await flush();
    expect(bridge.callTool).toHaveBeenCalledWith("ui_prices", {
      slug: "estradiol",
      form: "tablet",
      strength: "1 mg",
      quantity: 90,
    });
  });
});
