// @vitest-environment jsdom
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  InsufficientSourcesNotice,
  VerifiedSourceCard,
  type VerifiedSource,
} from "./VerifiedSourceCard";

describe("VerifiedSourceCard component (Issue #104, #58, #94)", () => {
  afterEach(() => {
    cleanup();
  });
  const sampleSource: VerifiedSource = {
    id: "src-1",
    title: "Introduction to Algorithms - MIT OCW",
    url: "https://ocw.mit.edu/courses/6-006",
    domain: "ocw.mit.edu",
    institution: "Massachusetts Institute of Technology (MIT)",
    license: "CC-BY-NC-SA-4.0",
    format: "video",
    duration_min: 50,
    verification_status: "verified",
    verified_at: "2026-11-01",
    score: 0.92,
    reason: "Directly matches learning outcome CLO 1.2",
    evidence_quote: "Algorithms break complex problems into atomic steps.",
  };

  it("shows the verified badge only for a verified source", () => {
    const { rerender } = render(<VerifiedSourceCard source={sampleSource} />);
    expect(
      screen.getByRole("button", { name: /tiêu chí thẩm định/ }),
    ).toBeTruthy();
    rerender(
      <VerifiedSourceCard
        source={{ ...sampleSource, verification_status: undefined }}
      />,
    );
    expect(
      screen.queryByRole("button", { name: /tiêu chí thẩm định/ }),
    ).toBeNull();
  });

  it("renders verified source card with all fields and safe external link", () => {
    render(<VerifiedSourceCard source={sampleSource} />);

    const link = screen.getByRole("link", {
      name: /Introduction to Algorithms - MIT OCW/i,
    });
    expect(link).toBeTruthy();
    expect(link.getAttribute("target")).toBe("_blank");
    expect(link.getAttribute("rel")).toBe("noopener noreferrer");

    expect(screen.getByText("ocw.mit.edu")).toBeTruthy();
    expect(
      screen.getByText(/Massachusetts Institute of Technology/),
    ).toBeTruthy();
    expect(screen.getByText(/CC-BY-NC-SA-4.0/)).toBeTruthy();
    expect(screen.getByText("Video")).toBeTruthy();
    expect(screen.getByText(/50 phút/)).toBeTruthy();
    expect(screen.getByText(/★ 92%/)).toBeTruthy();
    expect(
      screen.getByText(/Directly matches learning outcome CLO 1.2/),
    ).toBeTruthy();
    expect(
      screen.getByText(
        /"Algorithms break complex problems into atomic steps."/,
      ),
    ).toBeTruthy();
  });

  it("toggles the vetting criteria explanation tooltip when badge is clicked", () => {
    render(<VerifiedSourceCard source={sampleSource} />);

    const badgeBtn = screen.getByRole("button", {
      name: /Xem tiêu chí thẩm định nguồn đã xác minh/i,
    });
    expect(screen.queryByRole("tooltip")).toBeNull();

    // Click to open
    fireEvent.click(badgeBtn);
    expect(screen.getByRole("tooltip")).toBeTruthy();
    expect(screen.getByText(/Tiêu chí thẩm định nguồn uy tín/i)).toBeTruthy();

    // Press Escape to close
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("tooltip")).toBeNull();
  });

  it("triggers feedback callbacks for helpful / not helpful", () => {
    const feedbackSpy = vi.fn();
    render(
      <VerifiedSourceCard source={sampleSource} onFeedback={feedbackSpy} />,
    );

    fireEvent.click(screen.getByRole("button", { name: /Hữu ích/ }));
    expect(feedbackSpy).toHaveBeenCalledWith(true);

    fireEvent.click(screen.getByRole("button", { name: /Không hữu ích|Không phù hợp/ }));
    expect(feedbackSpy).toHaveBeenCalledWith(false);
  });

  it("never shows 'Đã xác minh' badge for an external source even if verification_status is set (Issue #159)", () => {
    const externalSource: VerifiedSource = {
      ...sampleSource,
      kind: "external",
      verification_status: "verified",
    };
    render(<VerifiedSourceCard source={externalSource} />);
    expect(screen.queryByRole("button", { name: /tiêu chí thẩm định/ })).toBeNull();
    expect(screen.queryByText(/✓ Đã xác minh/)).toBeNull();
    expect(screen.getByText(/Nguồn ngoài/)).toBeTruthy();
  });

  it("never shows 'Đã xác minh' badge for web kind sources", () => {
    const webSource: VerifiedSource = {
      ...sampleSource,
      kind: "web",
      verification_status: "verified",
    };
    render(<VerifiedSourceCard source={webSource} />);
    expect(screen.queryByRole("button", { name: /tiêu chí thẩm định/ })).toBeNull();
    expect(screen.queryByText(/✓ Đã xác minh/)).toBeNull();
    expect(screen.getByText(/Nguồn ngoài/)).toBeTruthy();
  });

  it("shows user material badge for user_material kind", () => {
    const userMaterial: VerifiedSource = {
      ...sampleSource,
      kind: "user_material",
    };
    render(<VerifiedSourceCard source={userMaterial} />);
    expect(screen.getByText(/Tài liệu của bạn/)).toBeTruthy();
  });

  it("triggers pin callback when pin button is clicked", () => {
    const pinSpy = vi.fn();
    render(<VerifiedSourceCard source={sampleSource} onPin={pinSpy} />);
    const pinBtn = screen.getByRole("button", { name: /Ghim/ });
    expect(pinBtn).toBeTruthy();
    fireEvent.click(pinBtn);
    expect(pinSpy).toHaveBeenCalledWith(true);
  });

  it("renders InsufficientSourcesNotice with exact spec text 'Chưa tìm được nguồn đủ tốt'", () => {
    const retrySpy = vi.fn();
    render(<InsufficientSourcesNotice onRetry={retrySpy} />);

    expect(screen.getByText("Chưa tìm được nguồn đủ tốt")).toBeTruthy();
    expect(screen.getByText(/Chưa có đủ tài liệu mở/)).toBeTruthy();
    expect(
      screen.getByText(/ngưỡng chất lượng thẩm định ≥ 0.65/i),
    ).toBeTruthy();

    const retryBtn = screen.getByRole("button", { name: "Tìm lại" });
    fireEvent.click(retryBtn);
    expect(retrySpy).toHaveBeenCalled();
  });
});

it("does not claim a seven-criterion breakdown when the API returns no scores", () => {
  render(
    <VerifiedSourceCard
      source={{
        id: "empty",
        title: "Source without breakdown",
        score: 0.8,
        breakdown: {},
      }}
    />,
  );
  expect(screen.getByText("★ 80%")).toBeTruthy();
  expect(screen.queryByText(/7 tiêu chí/)).toBeNull();
});
