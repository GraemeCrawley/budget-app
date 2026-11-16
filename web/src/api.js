// Every request goes through here. Paths are relative ("months" -> "api/v1/months") so the
// client works under the /budget/ prefix. With VITE_MOCK set, mock.js answers instead of fetch.
export class ApiError extends Error {
  constructor(status, detail, body = null) {
    super(detail);
    this.name = "ApiError";
    this.status = status; // 0 when the request never reached the server
    this.detail = detail;
    this.body = body;
  }
}

async function request(method, path, body, headers) {
  let status;
  let parsed = null;
  try {
    if (import.meta.env.VITE_MOCK) {
      const { answer } = await import("./mock.js");
      ({ status, body: parsed } = await answer(method, path, body));
    } else {
      const res = await fetch(`api/v1/${path}`, { method, headers, body, credentials: "same-origin" });
      status = res.status;
      const text = await res.text();
      try {
        parsed = text === "" && status === 204 ? null : JSON.parse(text);
      } catch {
        // A success that isn't JSON (a login page, a proxy error) must not reach a screen as data.
        if (status < 400) throw new ApiError(status, "the server's reply could not be read");
        parsed = null;
      }
    }
  } catch (err) {
    if (err instanceof ApiError) throw err;
    throw new ApiError(0, "could not reach the server");
  }
  if (status >= 400) {
    const detail = parsed && typeof parsed.detail === "string" ? parsed.detail : `request failed (${status})`;
    throw new ApiError(status, detail, parsed);
  }
  return parsed;
}

// The server refuses a write that does not carry this header.
const WRITE = { "X-Budget-Client": "1" };

export function get(path) {
  return request("GET", path);
}

// The mock takes the body as an object; the server takes JSON.
export function send(method, path, body) {
  if (body === undefined || import.meta.env.VITE_MOCK) return request(method, path, body, WRITE);
  return request(method, path, JSON.stringify(body), { ...WRITE, "Content-Type": "application/json" });
}

// The browser sets the multipart boundary itself, so no Content-Type here.
export function upload(path, formData) {
  return request("POST", path, formData, WRITE);
}
