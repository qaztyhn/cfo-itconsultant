import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DEMO_LABEL } from "./constants";
import { ContactLogDemo } from "./ContactLogDemo";

const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

async function addEntry(user: ReturnType<typeof userEvent.setup>, channel: string, reason: string, note?: string) {
  await user.selectOptions(screen.getByLabelText("Channel"), channel);
  await user.selectOptions(screen.getByLabelText("Reason"), reason);
  if (note) await user.type(screen.getByLabelText("Note (optional)"), note);
  await user.click(screen.getByRole("button", { name: "Add demo entry" }));
}

describe("CS contact-log demo", () => {
  it("test_US_CS_02_demo_label_is_always_visible_and_no_button_says_save", () => {
    render(<ContactLogDemo />);
    expect(screen.getByText(DEMO_LABEL)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /save|submit|send/i })).toBeNull();
  });

  it("test_US_CS_02_channel_and_reason_are_required", async () => {
    const user = userEvent.setup();
    render(<ContactLogDemo />);
    await user.click(screen.getByRole("button", { name: "Add demo entry" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Choose a channel and a reason.");
    expect(screen.queryByRole("list", { name: "Demo entries" })).toBeNull();
  });

  it("test_US_CS_02_adding_an_entry_is_local_only_labelled_demo_and_never_calls_the_network", async () => {
    const user = userEvent.setup();
    render(<ContactLogDemo />);
    await addEntry(user, "phone", "complaint", "Called back at lunch");
    const list = screen.getByRole("list", { name: "Demo entries" });
    expect(list).toHaveTextContent("Demo");
    expect(list).toHaveTextContent("Phone · Complaint");
    expect(list).toHaveTextContent("Called back at lunch");
    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Channel")).toHaveValue("");
    expect(screen.getByLabelText("Note (optional)")).toHaveValue("");
  });

  it("test_US_CS_02_note_is_optional_and_newest_entry_is_first", async () => {
    const user = userEvent.setup();
    render(<ContactLogDemo />);
    await addEntry(user, "email", "other");
    await addEntry(user, "chat", "delay_inquiry");
    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent("Chat · Delay inquiry");
    expect(items[1]).toHaveTextContent("Email · Other");
  });

  it("test_US_CS_02_no_success_wording_only_the_demo_label_mentions_saving", async () => {
    const user = userEvent.setup();
    render(<ContactLogDemo />);
    await user.click(screen.getByRole("button", { name: "Add demo entry" }));
    await addEntry(user, "phone", "other", "note");
    const mentions = screen.getAllByText(/saved/i);
    expect(mentions).toHaveLength(1);
    expect(mentions[0]).toHaveTextContent(DEMO_LABEL);
    expect(screen.queryByText(/success|logged successfully|recorded/i)).toBeNull();
  });

  it("test_US_CS_02_note_is_rendered_as_plain_text", async () => {
    const user = userEvent.setup();
    render(<ContactLogDemo />);
    await user.selectOptions(screen.getByLabelText("Channel"), "chat");
    await user.selectOptions(screen.getByLabelText("Reason"), "other");
    await user.click(screen.getByLabelText("Note (optional)"));
    await user.paste("<b>bold</b>");
    await user.click(screen.getByRole("button", { name: "Add demo entry" }));
    expect(screen.getByText("<b>bold</b>")).toBeInTheDocument();
  });
});