import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, get, send, upload } from "./api.js";

function reply(status, body) {
  return Promise.resolve(new Response(JSON.stringify(body), {
    status, headers: { "Content-Type": "application/json" },
  }));
}

afterEach(() => vi.unstubAllGlobals());

describe("api", () => {
  it("resolves a 200 to its parsed body, from a relative URL", async () => {
    const fetch = vi.fn(() => reply(200, { months: [] }));
    vi.stubGlobal("fetch", fetch);
    await expect(get("months")).resolves.toEqual({ months: [] });
    expect(fetch.mock.calls[0][0]).toBe("api/v1/months");
  });
  it("throws an ApiError carrying the status and the detail", async () => {
    vi.stubGlobal("fetch", vi.fn(() => reply(401, { detail: "not signed in", reason: "no_token" })));
    const err = await get("months").catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(401);
    expect(err.detail).toBe("not signed in");
    expect(err.body).toEqual({ detail: "not signed in", reason: "no_token" });
  });
  it("turns a network failure into an ApiError with status 0", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new TypeError("Failed to fetch"))));
    const err = await get("months").catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(0);
  });
  it("sends a JSON body with the method", async () => {
    const fetch = vi.fn(() => reply(200, { id: 7 }));
    vi.stubGlobal("fetch", fetch);
    await send("PUT", "transactions/7/override", { category: "Coffee" });
    const [url, init] = fetch.mock.calls[0];
    expect(url).toBe("api/v1/transactions/7/override");
    expect(init.method).toBe("PUT");
    expect(init.headers["Content-Type"]).toBe("application/json");
    expect(JSON.parse(init.body)).toEqual({ category: "Coffee" });
  });
  it("posts form data as it is, without a JSON content type", async () => {
    const fetch = vi.fn(() => reply(200, { ok: true, batches: [] }));
    vi.stubGlobal("fetch", fetch);
    const form = new FormData();
    form.append("account_key", "card");
    await upload("uploads", form);
    const [url, init] = fetch.mock.calls[0];
    expect(url).toBe("api/v1/uploads");
    expect(init.method).toBe("POST");
    expect(init.body).toBe(form);
    expect(init.headers).toEqual({ "X-Budget-Client": "1" });
  });
  it("sends X-Budget-Client on every write (POST, PUT, PATCH, DELETE, upload) but a GET does not need it", async () => {
    const fetch = vi.fn(() => reply(200, {}));
    vi.stubGlobal("fetch", fetch);
    await send("POST", "a", { x: 1 });
    await send("PUT", "a", { x: 1 });
    await send("PATCH", "a", { x: 1 });
    await send("DELETE", "a");
    await send("POST", "a");
    await upload("uploads", new FormData());
    for (const [, init] of fetch.mock.calls) expect(init.headers["X-Budget-Client"]).toBe("1");
    expect(fetch.mock.calls[0][1].headers["Content-Type"]).toBe("application/json");
    await get("a");
    expect(fetch.mock.calls.at(-1)[1].headers?.["X-Budget-Client"]).toBeUndefined();
  });
  it("throws when a success reply is not JSON, so a screen never renders from nothing", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response("<html>sign in</html>", { status: 200 }))));
    const err = await get("months").catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(200);
    expect(err.detail).toBe("the server's reply could not be read");
  });
  it("allows an empty 204 reply", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response(null, { status: 204 }))));
    await expect(send("DELETE", "things/1")).resolves.toBeNull();
  });
});
