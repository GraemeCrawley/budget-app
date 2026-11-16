import { describe, expect, it } from "vitest";
import { missingMonths, missingSpans, waitingAfter, wholeMonths } from "./missing.js";

const names = (months) => months.map((m) => ({ month: m.month, accounts: m.accounts.map((a) => a.name) }));

describe("missingMonths", () => {
  it("a gap in the middle of a month is given as its own days", () => {
    const accounts = [{ name: "Card", ranges: [["2026-01-01", "2026-03-09"], ["2026-03-20", "2026-04-30"]] }];
    expect(missingMonths(accounts, "2026-05-13")).toEqual([
      { month: "2026-03", accounts: [{ name: "Card", whole: false, gaps: [["2026-03-10", "2026-03-19"]] }] }]);
  });

  it("lists each finished month an account does not fully cover, oldest first", () => {
    const accounts = [
      { name: "Everyday", ranges: [["2026-01-01", "2026-02-28"]] },
      { name: "Card", ranges: [["2026-01-01", "2026-01-31"], ["2026-03-01", "2026-04-30"]] },
    ];
    expect(names(missingMonths(accounts, "2026-05-13"))).toEqual([
      { month: "2026-02", accounts: ["Card"] },
      { month: "2026-03", accounts: ["Everyday"] },
      { month: "2026-04", accounts: ["Everyday"] },
    ]);
    expect(missingMonths(accounts, "2026-05-13")[0].accounts[0]).toEqual(
      { name: "Card", whole: true, gaps: [["2026-02-01", "2026-02-28"]] });
  });

  it("never lists the month in progress, or months before an account's data starts", () => {
    const accounts = [{ name: "Card", ranges: [["2026-03-01", "2026-04-30"]] }];
    expect(missingMonths(accounts, "2026-05-13")).toEqual([]);
  });

  it("a month covered only in part is missing, and days before an account's first file are not missing", () => {
    const accounts = [
      { name: "Part", ranges: [["2026-03-01", "2026-04-11"]] },
      { name: "Cycle", ranges: [["2026-02-04", "2026-05-03"]] },
    ];
    expect(missingMonths(accounts, "2026-05-20")).toEqual([
      { month: "2026-04", accounts: [{ name: "Part", whole: false, gaps: [["2026-04-12", "2026-04-30"]] }] },
    ]);
  });

  it("an account with nothing yet, and a year end, are handled", () => {
    const accounts = [{ name: "New", ranges: [] }, { name: "Old", ranges: [["2025-11-01", "2025-11-30"]] }];
    expect(names(missingMonths(accounts, "2026-02-01"))).toEqual([
      { month: "2025-12", accounts: ["Old"] }, { month: "2026-01", accounts: ["Old"] }]);
  });
});

describe("missingSpans", () => {
  it("gives what an account lacks as spans that run across month ends", () => {
    const ranges = [["2026-04-03", "2026-08-03"], ["2026-09-03", "2026-11-03"]];
    expect(missingSpans(ranges, "2026-11-13")).toEqual([["2026-08-04", "2026-09-02"]]);
  });

  it("stops at the end of the last finished month, and is empty with no data", () => {
    expect(missingSpans([["2026-03-01", "2026-07-31"]], "2026-11-13")).toEqual([["2026-08-01", "2026-10-31"]]);
    expect(missingSpans([["2026-11-02", "2026-11-05"]], "2026-11-13")).toEqual([]);
    expect(missingSpans([], "2026-11-13")).toEqual([]);
  });
});

describe("wholeMonths", () => {
  it("names the months of a span made of whole months, and nothing otherwise", () => {
    expect(wholeMonths(["2025-12-01", "2026-01-31"])).toEqual(["2025-12", "2026-01"]);
    expect(wholeMonths(["2026-08-04", "2026-09-02"])).toBeNull();
    expect(wholeMonths(["2026-08-01", "2026-08-30"])).toBeNull();
  });
});

describe("a file that is not out yet", () => {
  const card = [["2026-09-15", "2026-10-14"]];

  it("is not missing while its statement is still open or only just closed", () => {
    expect(missingSpans(card, "2026-11-13")).toEqual([]);
    expect(missingMonths([{ name: "Card", ranges: card }], "2026-11-13")).toEqual([]);
    expect(waitingAfter(card, "2026-11-13")).toBe("2026-10-14");
  });

  it("is missing once it has had time to be published", () => {
    expect(missingSpans(card, "2026-11-25")).toEqual([["2026-10-15", "2026-10-31"]]);
    expect(waitingAfter(card, "2026-11-25")).toBeNull();
  });

  it("an earlier gap is still missing, and an account up to date is not waiting", () => {
    const gappy = [["2026-07-01", "2026-07-31"], ["2026-09-15", "2026-10-14"]];
    expect(missingSpans(gappy, "2026-11-13")).toEqual([["2026-08-01", "2026-09-14"]]);
    expect(waitingAfter([["2026-07-01", "2026-10-31"]], "2026-11-13")).toBeNull();
  });
});
