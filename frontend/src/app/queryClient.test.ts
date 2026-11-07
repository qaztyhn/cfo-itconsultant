import { afterEach, describe, expect, it } from "vitest";
import { signInAs, userByEmail } from "../test/utils";
import { queryClient } from "./queryClient";
import { useAuthStore } from "./store";

const COUNTS_KEY = ["orders", "counts"];

describe("query cache follows the session", () => {
  afterEach(() => {
    useAuthStore.getState().clearAuth();
    queryClient.clear();
  });

  it("drops cached data when the user signs out", () => {
    signInAs(userByEmail("dispatcher@cfo.demo"));
    queryClient.setQueryData(COUNTS_KEY, { needs_plan: 5 });

    useAuthStore.getState().clearAuth();

    expect(queryClient.getQueryData(COUNTS_KEY)).toBeUndefined();
  });

  it("does not show user A's data to user B after A signs out and B signs in", () => {
    const userA = userByEmail("dispatcher@cfo.demo");
    const userB = { ...userA, id: userA.id + 1000 };
    signInAs(userA);
    queryClient.setQueryData(COUNTS_KEY, { needs_plan: 5 });

    useAuthStore.getState().clearAuth();
    signInAs(userB);

    expect(queryClient.getQueryData(COUNTS_KEY)).toBeUndefined();
  });

  it("drops cached data when another account signs in without an explicit logout", () => {
    const userA = userByEmail("dispatcher@cfo.demo");
    const userB = { ...userA, id: userA.id + 1000 };
    signInAs(userA);
    queryClient.setQueryData(COUNTS_KEY, { needs_plan: 5 });

    signInAs(userB);

    expect(queryClient.getQueryData(COUNTS_KEY)).toBeUndefined();
  });

  it("aborts in-flight requests when the session ends", async () => {
    signInAs(userByEmail("dispatcher@cfo.demo"));
    let aborted = false;
    const pending = queryClient
      .fetchQuery({
        queryKey: ["slow"],
        queryFn: ({ signal }) =>
          new Promise((_resolve, reject) => {
            signal.addEventListener("abort", () => {
              aborted = true;
              reject(new Error("aborted"));
            });
          }),
      })
      .catch(() => undefined);
    await Promise.resolve();

    useAuthStore.getState().clearAuth();
    await pending;

    expect(aborted).toBe(true);
  });
});
