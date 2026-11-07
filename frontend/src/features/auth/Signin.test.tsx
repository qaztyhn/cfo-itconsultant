import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it } from "vitest";
import { API_BASE_URL } from "../../api/config";
import { handlers } from "../../api/mocks/handlers";
import { resetLoginRateLimit } from "../../api/mocks/authHandlers";
import { currentPath, renderAt } from "../../test/utils";

const server = setupServer(...handlers);

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
beforeEach(() => resetLoginRateLimit());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const submitButton = () => screen.getByRole("button", { name: /^sign(ing)? in/i });

describe("SignIn", () => {
  it("lists the 7 demo account cards, including Customer service and Business owner (03 #24)", async () => {
    renderAt("/login");

    const cards = within(await screen.findByRole("list", { name: "Demo accounts" })).getAllByRole("button");
    expect(cards).toHaveLength(7);
    expect(screen.getByRole("button", { name: /Customer service/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Business owner/ })).toBeInTheDocument();
  });

  it("a demo card fills the email only and moves focus to the password", async () => {
    renderAt("/login");

    await userEvent.setup().click(screen.getByRole("button", { name: /Customer service/ }));

    expect(screen.getByLabelText("Email")).toHaveValue("cs@cfo.demo");
    expect(screen.getByLabelText("Password")).toHaveValue("");
    expect(screen.getByLabelText("Password")).toHaveFocus();
  });

  it("validates empty fields before sending anything and focuses the first invalid one", async () => {
    renderAt("/login");

    await userEvent.setup().click(submitButton());

    expect(screen.getByText("Enter a valid email address.")).toBeInTheDocument();
    expect(screen.getByText("Enter your password.")).toBeInTheDocument();
    expect(screen.getByLabelText("Email")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByLabelText("Email")).toHaveFocus();
    expect(currentPath()).toBe("/login");
  });

  it("shows a generic message for wrong credentials and stays on /login", async () => {
    renderAt("/login");
    const user = userEvent.setup();

    await user.type(screen.getByLabelText("Email"), "nobody@cfo.demo");
    await user.type(screen.getByLabelText("Password"), "whatever");
    await user.click(submitButton());

    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid email or password.");
    expect(currentPath()).toBe("/login");
    expect(submitButton()).toBeEnabled();
  });

  it("shows the rate-limit message after repeated failures (429)", async () => {
    renderAt("/login");
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Email"), "nobody@cfo.demo");
    await user.type(screen.getByLabelText("Password"), "whatever");

    for (let attempt = 0; attempt < 6; attempt += 1) {
      await user.click(submitButton());
      await waitFor(() => expect(submitButton()).toBeEnabled());
    }

    expect(await screen.findByRole("alert")).toHaveTextContent("Too many attempts");
  });

  it("disables the form and shows 'Signing in…' while the request is pending", async () => {
    server.use(http.post(`${API_BASE_URL}/auth/login`, async () => {
      await delay("infinite");
      return HttpResponse.json({});
    }));
    renderAt("/login");
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Email"), "dispatcher@cfo.demo");
    await user.type(screen.getByLabelText("Password"), "whatever");

    await user.click(submitButton());

    expect(await screen.findByRole("button", { name: "Signing in…" })).toBeDisabled();
    expect(screen.getByLabelText("Email")).toBeDisabled();
  });

  it("returns to the page the visitor was heading to once signed in", async () => {
    renderAt("/dispatcher/plan-review");
    await waitFor(() => expect(currentPath()).toBe("/login"));
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: /Dispatcher/ }));
    await user.type(screen.getByLabelText("Password"), "whatever");
    await user.click(submitButton());

    await waitFor(() => expect(currentPath()).toBe("/dispatcher/plan-review"));
  });

  it.each([
    ["Dispatcher", "/dispatcher/orders"],
    ["Warehouse manager", "/warehouse/prep"],
    ["Sales", "/store/orders"],
    ["Driver", "/driver"],
    ["Admin", "/it/integration"],
    ["Customer service", "/cs/orders"],
    ["Business owner", "/revenue"],
  ])("%s lands on %s after signing in from the card", async (title, landing) => {
    renderAt("/login");
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: new RegExp(title) }));
    await user.type(screen.getByLabelText("Password"), "whatever");
    await user.click(submitButton());

    await waitFor(() => expect(currentPath()).toBe(landing));
  });
});